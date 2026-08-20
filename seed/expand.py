"""In-ClickHouse fact expansion — the fast half of the hybrid seeder.

Python computes ~40k parameter rows (seed/channels.py); this module turns them
into tens of millions of audience_performance rows with INSERT…SELECT over
CROSS JOIN numbers(), entirely server-side, at millions of rows per second.
Every per-row wobble is cityHash64-derived from stable keys, so a reseed is
bit-identical on the pinned ClickHouse image — no Python loop ever touches a
fact row.

Scratch tables live in their own `genesis_seed` database (dropped at the end of
a seed) so `list_tables` on the real database — the agents' schema grounding —
never sees them. Statements chunk by channel group and, for the daily streaming
channels, by calendar year: each statement touches ≤115 yearly partitions and
bounds its own memory.
"""
from __future__ import annotations

import time

from seed import channels, config, shocks

SCRATCH = "genesis_seed"


def _attendance_shock_expr() -> str:
    """multiIf over the shock calendar for theatrical demand.

    Generated from seed/shocks.py — the same windows the seeded shock_calendar
    table carries, so a JOIN against that table explains every dent this
    expression makes. Applies only to theatrical channels; windows with
    attendance_mult = 1 are omitted (they don't overlap the rest).
    """
    arms = []
    for s in shocks.SHOCKS:
        if s.attendance_mult != 1.0:
            arms.append(f"x.at >= '{s.start}' AND x.at <= '{s.end}', {s.attendance_mult}")
    return ("multiIf(x.channel NOT IN ('theatrical', 'theatrical_reissue'), 1.0, "
            + ", ".join(arms) + ", 1.0)")

INSERT_SETTINGS = {
    "max_partitions_per_insert_block": 200,
    "max_insert_threads": 4,
    "max_memory_usage": 6_000_000_000,
}

SCRATCH_DDL = [
    f"CREATE DATABASE IF NOT EXISTS {SCRATCH}",
    f"""CREATE TABLE IF NOT EXISTS {SCRATCH}.params (
        project_id String, title String, channel LowCardinality(String),
        platform LowCardinality(String), open_d Date32, close_d Date32,
        cadence UInt16, max_periods UInt32, base Float64, decay Float64,
        opening_boost Float64, boost_periods UInt8, completion_base Float32,
        participation UInt8, terr_count UInt8, floor Float64
    ) ENGINE = MergeTree ORDER BY (channel, project_id)""",
    f"""CREATE TABLE IF NOT EXISTS {SCRATCH}.territories (
        idx UInt8, name LowCardinality(String), active_from Date32,
        w2 Float64, w3 Float64, w4 Float64, w6 Float64
    ) ENGINE = MergeTree ORDER BY idx""",
    f"""CREATE TABLE IF NOT EXISTS {SCRATCH}.year_curve (
        channel LowCardinality(String), year UInt16, mult Float64
    ) ENGINE = MergeTree ORDER BY (channel, year)""",
    f"""CREATE TABLE IF NOT EXISTS {SCRATCH}.price_curve (
        channel LowCardinality(String), year UInt16, unit_price Float64
    ) ENGINE = MergeTree ORDER BY (channel, year)""",
]

AUDIENCE_SQL = """
INSERT INTO genesis_institutional.audience_performance
    (project_id, title, at, channel, platform, territory, views, completion, revenue)
SELECT
    x.project_id, x.title, x.at, x.channel,
    multiIf(x.channel = 'home_video' AND toYear(x.at) < 1998, 'vhs',
            x.channel = 'home_video' AND toYear(x.at) >= 2007
                AND cityHash64(x.project_id, x.territory, toString(x.at), 'plat') % 100 < 15, 'bluray',
            x.channel = 'home_video', 'dvd',
            x.platform) AS platform,
    x.territory,
    if(pc.unit_price <= 0, 0,
       toUInt64(greatest(1, round(x.rev0 * yc.mult * {shock_expr} / pc.unit_price)))) AS views,
    if(x.completion_base <= 0, NULL,
       toFloat32(least(0.99, greatest(0.2,
           x.completion_base - 0.02 * log1p(x.n / 365.0)
           + (toInt64(cityHash64(x.project_id, x.territory, toString(x.at), 'cmp') % 121) - 60) / 1000.0)))
      ) AS completion,
    round(x.rev0 * yc.mult * {shock_expr}, 2) AS revenue
FROM (
    SELECT p.project_id, p.title, p.channel, p.platform, p.completion_base,
           t.name AS territory, n.number AS n,
           addDays(p.open_d, toInt32(n.number * p.cadence)) AS at,
           p.base
             * exp(-p.decay * n.number)
             * if(n.number < p.boost_periods, p.opening_boost, 1.0)
             * multiIf(p.terr_count = 2, t.w2, p.terr_count = 3, t.w3,
                       p.terr_count = 4, t.w4, t.w6)
             * (0.80 + (cityHash64(p.project_id, p.channel, t.name, toString(n.number)) % 4001) / 10000.0)
             AS rev0,
           p.floor AS floor
    FROM {scratch}.params AS p
    CROSS JOIN {scratch}.territories AS t
    CROSS JOIN numbers({max_n}) AS n
    WHERE {channel_filter}
      AND n.number <= p.max_periods
      AND t.idx < p.terr_count
      AND addDays(p.open_d, toInt32(n.number * p.cadence)) <= p.close_d
      AND (p.channel != 'streaming_own'
           OR t.active_from <= addDays(p.open_d, toInt32(n.number * p.cadence)))
      AND cityHash64(p.project_id, p.channel, toString(n.number), 'part') % 100 < p.participation
) AS x
INNER JOIN {scratch}.year_curve  AS yc ON yc.channel = x.channel AND yc.year = toYear(x.at)
INNER JOIN {scratch}.price_curve AS pc ON pc.channel = x.channel AND pc.year = toYear(x.at)
WHERE x.rev0 * yc.mult * {shock_expr} >= x.floor{year_filter}
"""

DAILY_CHANNELS = ("streaming_own", "streaming_licensed")


def prepare_scratch(client, projects: list[dict]) -> None:
    for stmt in SCRATCH_DDL:
        client.command(stmt)
    for table in ("params", "territories", "year_curve", "price_curve"):
        client.command(f"TRUNCATE TABLE {SCRATCH}.{table}")
    params = channels.all_params(projects)
    client.insert(f"{SCRATCH}.params", params, column_names=channels.PARAM_COLUMNS)
    client.insert(f"{SCRATCH}.territories", channels.territory_rows(),
                  column_names=["idx", "name", "active_from", "w2", "w3", "w4", "w6"])
    client.insert(f"{SCRATCH}.year_curve", channels.year_curve_rows(),
                  column_names=["channel", "year", "mult"])
    client.insert(f"{SCRATCH}.price_curve", channels.price_curve_rows(),
                  column_names=["channel", "year", "unit_price"])
    print(f"[seed] scratch: {len(params):,} channel-param rows for "
          f"{len({r[0] for r in params}):,} titles")


def _run(client, label: str, sql: str) -> int:
    before = client.query(
        "SELECT count() FROM genesis_institutional.audience_performance").result_rows[0][0]
    t0 = time.time()
    client.command(sql, settings=INSERT_SETTINGS)
    after = client.query(
        "SELECT count() FROM genesis_institutional.audience_performance").result_rows[0][0]
    print(f"[seed]   audience/{label}: +{after - before:,} rows ({time.time() - t0:.0f}s)")
    return after - before


def expand_audience(client) -> int:
    """All audience channels: periodic channels in one pass, daily ones per year."""
    total = 0
    periodic = ", ".join(f"'{c}'" for c in channels.CADENCE if c not in DAILY_CHANNELS)
    shock = _attendance_shock_expr()
    total += _run(client, "periodic", AUDIENCE_SQL.format(
        scratch=SCRATCH, max_n=620, shock_expr=shock,
        channel_filter=f"p.channel IN ({periodic})", year_filter=""))
    daily = ", ".join(f"'{c}'" for c in DAILY_CHANNELS)
    for year in range(2015, config.HORIZON.year + 1):
        total += _run(client, f"daily-{year}", AUDIENCE_SQL.format(
            scratch=SCRATCH, max_n=2300, shock_expr=shock,
            channel_filter=f"p.channel IN ({daily})",
            year_filter=f" AND toYear(x.at) = {year}"))
    return total


def detach_mv(client, name: str) -> None:
    try:
        client.command(f"DETACH TABLE genesis_institutional.{name}")
    except Exception:
        pass                       # already detached


def attach_mv(client, name: str) -> None:
    try:
        client.command(f"ATTACH TABLE genesis_institutional.{name}")
    except Exception:
        pass                       # already attached


def backfill_audience_monthly(client) -> None:
    t0 = time.time()
    client.command("""
        INSERT INTO genesis_institutional.audience_monthly
        SELECT project_id, at - toIntervalDay(toDayOfMonth(at) - 1) AS month, channel,
               sum(views) AS views, sum(revenue) AS revenue,
               sum(assumeNotNull(completion)) AS completion_sum,
               countIf(isNotNull(completion)) AS completion_n
        FROM genesis_institutional.audience_performance
        GROUP BY project_id, month, channel
    """, settings=INSERT_SETTINGS)
    n = client.query("SELECT count() FROM genesis_institutional.audience_monthly").result_rows[0][0]
    print(f"[seed] audience_monthly backfill: {n:,} rows ({time.time() - t0:.0f}s)")


def drop_scratch(client) -> None:
    client.command(f"DROP DATABASE IF EXISTS {SCRATCH}")


# ── production / financial / distribution ────────────────────────────────────

PROD_DDL = [
    f"""CREATE TABLE IF NOT EXISTS {SCRATCH}.proj_params (
        project_id String, era_id UInt8, budget Float64, overrun Float64,
        window_start Date32, window_days UInt16, shoot_frac_start Float32,
        shoot_frac_end Float32, months UInt16, vfx_heavy UInt8,
        rows_per_day UInt8, slip_permille UInt16
    ) ENGINE = MergeTree ORDER BY project_id""",
    f"""CREATE TABLE IF NOT EXISTS {SCRATCH}.cost_shares (
        era_id UInt8, cost_center LowCardinality(String), share Float64,
        overrun_weight Float64
    ) ENGINE = MergeTree ORDER BY (era_id, cost_center)""",
    f"""CREATE TABLE IF NOT EXISTS {SCRATCH}.era_depts (
        era_id UInt8, dept LowCardinality(String)
    ) ENGINE = MergeTree ORDER BY (era_id, dept)""",
]


def _halt_expr(day_expr: str) -> str:
    """Production stops inside halt windows — generated from the shock calendar."""
    from seed import shocks as shocks_mod
    windows = [s for s in shocks_mod.SHOCKS if s.production_halt]
    cond = " OR ".join(f"({day_expr} >= '{s.start}' AND {day_expr} <= '{s.end}')"
                       for s in windows)
    return f"({cond})"


def _cost_shock_expr(day_expr: str) -> str:
    """Disruption-class cost pressure (strikes, pandemic protocols) on ACTUALS.

    Deflation-class shocks (Depression, wartime caps, receivership austerity)
    moved the price level of plans and actuals alike, so they cancel out of the
    overrun ratio and are deliberately omitted here — otherwise the Depression
    reads as discipline when it was chaos in cheaper dollars.
    """
    from seed import shocks as shocks_mod
    disruption = {"strike", "pandemic"}
    arms = [f"{day_expr} >= '{s.start}' AND {day_expr} <= '{s.end}', {s.cost_mult}"
            for s in shocks_mod.SHOCKS if s.cost_mult != 1.0 and s.kind in disruption]
    return "multiIf(" + ", ".join(arms) + ", 1.0)"


def build_prod_params(projects: list[dict]) -> list[list]:
    """One row per project: the production window and its telemetry density."""
    rows = []
    for p in projects:
        window_days = min(900, max(30, ((p["released_at"] or config.HORIZON)
                                        - p["greenlit_at"]).days))
        if p["status"] == "cancelled":
            window_days = int(window_days * 0.6)
        # the shoot occupies a mid-window slice: prep before, post after
        shoot_days = max(5, p["shoot_days_actual"])
        prep_frac = {1: .15, 2: .15, 3: .20, 4: .25, 5: .30, 6: .30, 7: .30,
                     8: .35, 9: .35, 10: .35}[p["era_id"]]
        fs = prep_frac
        fe = min(0.98, prep_frac + shoot_days / window_days)
        rows_per_day = 6 if p["era_id"] <= 3 else (10 if p["era_id"] <= 7 else
                                                   (20 if config.PROD_THIRD_METRIC else 14))
        slip_permille = min(250, int(max(0.0, p["_overrun"]) * 900))
        vfx = 1 if (p["era_id"] >= 6 and p["genre"] in
                    ("scifi", "fantasy", "animation", "action")) else 0
        months = min(40, max(3, window_days // 30))
        rows.append([p["project_id"], p["era_id"], p["budget_usd"], p["_overrun"],
                     p["greenlit_at"], window_days, round(fs, 4), round(fe, 4),
                     months, vfx, rows_per_day, slip_permille])
    return rows


PROD_PARAM_COLUMNS = ["project_id", "era_id", "budget", "overrun", "window_start",
                      "window_days", "shoot_frac_start", "shoot_frac_end", "months",
                      "vfx_heavy", "rows_per_day", "slip_permille"]


def cost_share_rows() -> list[list]:
    from seed import eras as eras_mod
    rows = []
    for era in eras_mod.ERAS:
        for center, share in era.cost_shares.items():
            rows.append([era.era_id, center, share,
                         config.CENTER_OVERRUN_WEIGHT.get(center, 1.0)])
    return rows


def era_dept_rows() -> list[list]:
    from seed import eras as eras_mod
    rows = []
    for era in eras_mod.ERAS:
        depts = (["production", "camera", "art"] if era.era_id <= 3 else
                 ["production", "camera", "art", "sound", "marketing"] if era.era_id <= 7 else
                 ["production", "camera", "art", "sound", "marketing", "post", "vfx"])
        for d in depts:
            rows.append([era.era_id, d])
    return rows


PRODUCTION_SQL = """
INSERT INTO genesis_institutional.production_events
    (project_id, at, dept, event_type, metric, value)
SELECT
    x.project_id,
    toDateTime64(toString(x.d) || ' 18:00:00', 0) AS at,
    x.dept,
    x.event_type,
    if(x.event_type = 'daily_burn', 'usd', 'hours') AS metric,
    round(x.value, 2) AS value
FROM (
    SELECT pp.project_id, dd.dept,
        addDays(pp.window_start, toInt32(n.number)) AS d,
        arrayJoin(['daily_burn', 'crew_hours']) AS event_type,
        if(event_type = 'daily_burn',
           (pp.budget / pp.window_days / pp.rows_per_day)
             * (1.0 + pp.overrun * 1.2 * (n.number / pp.window_days))
             * (0.8 + (cityHash64(pp.project_id, dd.dept, toString(n.number), 'burn') % 4001) / 10000.0)
             * {cost_shock},
           (12 + 60 * sin(pi() * least(1.0, (n.number / pp.window_days) * 1.1))
              * (1 + greatest(0.0, pp.overrun) * 0.5)) * 8
             * (0.85 + (cityHash64(pp.project_id, dd.dept, toString(n.number), 'crew') % 3001) / 10000.0)
        ) AS value
    FROM {scratch}.proj_params AS pp
    INNER JOIN {scratch}.era_depts AS dd ON dd.era_id = pp.era_id
    CROSS JOIN numbers(920) AS n
    WHERE n.number < pp.window_days
      AND NOT {halted}
) AS x
WHERE x.value > 0
"""

RENDER_SQL = """
INSERT INTO genesis_institutional.production_events
    (project_id, at, dept, event_type, metric, value)
SELECT pp.project_id,
    toDateTime64(toString(addDays(pp.window_start, toInt32(n.number))) || ' 22:00:00', 0),
    'vfx', 'render_farm', 'gpu_hours',
    round(800 * (n.number / pp.window_days) * (1 + greatest(0.0, pp.overrun))
          * (0.7 + (cityHash64(pp.project_id, toString(n.number), 'gpu') % 7001) / 10000.0), 1)
FROM {scratch}.proj_params AS pp
CROSS JOIN numbers(920) AS n
WHERE pp.vfx_heavy = 1 AND n.number < pp.window_days
  AND n.number / pp.window_days > 0.5
  AND NOT {halted}
"""

SLIP_SQL = """
INSERT INTO genesis_institutional.production_events
    (project_id, at, dept, event_type, metric, value)
SELECT pp.project_id,
    toDateTime64(toString(addDays(pp.window_start, toInt32(n.number))) || ' 12:00:00', 0),
    'production', 'schedule_slip', 'days',
    round(0.5 + (cityHash64(pp.project_id, toString(n.number), 'slipv') % 2501) / 1000.0, 1)
FROM {scratch}.proj_params AS pp
CROSS JOIN numbers(920) AS n
WHERE n.number < pp.window_days
  AND n.number / pp.window_days >= pp.shoot_frac_start
  AND n.number / pp.window_days < pp.shoot_frac_end
  AND cityHash64(pp.project_id, toString(n.number), 'slip') % 1000 < pp.slip_permille
  AND NOT {halted}
"""

PAUSE_SQL = """
INSERT INTO genesis_institutional.production_events
    (project_id, at, dept, event_type, metric, value)
SELECT pp.project_id,
    toDateTime64(toString(addDays(pp.window_start, toInt32(n.number))) || ' 09:00:00', 0),
    'production', 'strike_pause', 'days', 7.0
FROM {scratch}.proj_params AS pp
CROSS JOIN numbers(920) AS n
WHERE n.number < pp.window_days
  AND n.number % 7 = 0
  AND n.number / pp.window_days >= pp.shoot_frac_start
  AND n.number / pp.window_days < pp.shoot_frac_end
  AND {halted}
"""

FINANCIAL_SQL = """
INSERT INTO genesis_institutional.financial_ledger
    (project_id, at, cost_center, category, planned, actual)
SELECT
    pp.project_id,
    addDays(pp.window_start, toInt32(m.number * 30)) AS at,
    cs.cost_center, 'spend',
    round(pp.budget * cs.share
          * if(cs.cost_center IN ('marketing', 'p_and_a'),
               if(m.number / pp.months < 0.7, 0.3, 2.6), 1.0) / pp.months, 2) AS planned,
    round(greatest(0.0,
        planned * (1.0 + pp.overrun * cs.overrun_weight * (m.number / pp.months)
                   + ((cityHash64(pp.project_id, cs.cost_center, toString(m.number)) % 1201) - 600) / 10000.0)
        * {cost_shock}), 2) AS actual
FROM {scratch}.proj_params AS pp
INNER JOIN {scratch}.cost_shares AS cs ON cs.era_id = pp.era_id
CROSS JOIN numbers(40) AS m
WHERE m.number < pp.months
  AND NOT (cs.cost_center = 'covid_protocols'
           AND (addDays(pp.window_start, toInt32(m.number * 30)) < '2020-03-01'
                OR addDays(pp.window_start, toInt32(m.number * 30)) > '2022-12-31'))
"""


def expand_production(client, count_fn) -> None:
    halted = _halt_expr("addDays(pp.window_start, toInt32(n.number))")
    cost_shock = _cost_shock_expr("addDays(pp.window_start, toInt32(n.number))")
    before = count_fn("production_events")
    t0 = time.time()
    client.command(PRODUCTION_SQL.format(scratch=SCRATCH, halted=halted,
                                         cost_shock=cost_shock),
                   settings=INSERT_SETTINGS)
    client.command(RENDER_SQL.format(scratch=SCRATCH, halted=halted), settings=INSERT_SETTINGS)
    client.command(SLIP_SQL.format(scratch=SCRATCH, halted=halted), settings=INSERT_SETTINGS)
    client.command(PAUSE_SQL.format(scratch=SCRATCH, halted=halted), settings=INSERT_SETTINGS)
    print(f"[seed] production_events: +{count_fn('production_events') - before:,} rows "
          f"({time.time() - t0:.0f}s)")


def expand_financial(client, count_fn) -> None:
    cost_shock = _cost_shock_expr("addDays(pp.window_start, toInt32(m.number * 30))")
    before = count_fn("financial_ledger")
    t0 = time.time()
    detach_mv(client, "financial_monthly_mv")
    try:
        client.command(FINANCIAL_SQL.format(scratch=SCRATCH, cost_shock=cost_shock),
                       settings=INSERT_SETTINGS)
    finally:
        attach_mv(client, "financial_monthly_mv")
    client.command("""
        INSERT INTO genesis_institutional.financial_monthly
        SELECT project_id, at - toIntervalDay(toDayOfMonth(at) - 1) AS month, cost_center,
               sum(planned) AS planned, sum(actual) AS actual
        FROM genesis_institutional.financial_ledger
        GROUP BY project_id, month, cost_center
    """, settings=INSERT_SETTINGS)
    print(f"[seed] financial_ledger: +{count_fn('financial_ledger') - before:,} rows "
          f"({time.time() - t0:.0f}s)")


def prepare_prod_scratch(client, projects: list[dict]) -> None:
    for stmt in PROD_DDL:
        client.command(stmt)
    for table in ("proj_params", "cost_shares", "era_depts"):
        client.command(f"TRUNCATE TABLE {SCRATCH}.{table}")
    client.insert(f"{SCRATCH}.proj_params", build_prod_params(projects),
                  column_names=PROD_PARAM_COLUMNS)
    client.insert(f"{SCRATCH}.cost_shares", cost_share_rows(),
                  column_names=["era_id", "cost_center", "share", "overrun_weight"])
    client.insert(f"{SCRATCH}.era_depts", era_dept_rows(),
                  column_names=["era_id", "dept"])
