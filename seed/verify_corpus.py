"""The corpus acceptance gate: era recoverability, contested pair, volumes.

Seven engineered truths must be recoverable from the seeded data by plain SQL —
they are the acceptance bar for the century corpus, and fixture recording
(seed/record_fixtures.py) must not run until this passes:

  1. the seasonality regime flip (summer weak before 1975-06-20, dominant after)
  2. the overrun U-shape (golden-age factory discipline is the century minimum)
  3. the monster-cycle fatigue curve (early sequels outgross; parody is the floor)
  4. home video passing theatrical (~1986, sustained)
  5. the DVD revenue peak (2004) and collapse
  6. the COVID cliff (theatrical) and production halt (telemetry goes dark)
  7. the modern contested pair (sequels OPEN bigger AND their tails die faster —
     both well-powered, directions disagreeing; the product thesis lives here)

Thresholds carry margin but the ORDERINGS are strict — if one flips, the
corpus is wrong, not the probe. Also prints per-table fingerprints
(sum(cityHash64(all columns))): seed twice, compare, and determinism is proven.

    .venv/bin/python -m seed.verify_corpus
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

FACT_TABLES = ("projects", "eras", "cpi_annual", "franchises", "shock_calendar",
               "production_events", "financial_ledger", "audience_performance",
               "distribution_events")

CHECKS: list[tuple[str, str, str]] = []          # (name, sql, expression-on-row)


def check(name: str, sql: str, ok) -> tuple:
    return (name, sql, ok)


PROBES = [
    check(
        "1 seasonality regime flip",
        """SELECT round(sumIf(s, era='pre'), 3), round(sumIf(s, era='post'), 3) FROM (
             SELECT if(p.released_at < '1975-06-20', 'pre', 'post') AS era,
                    sumIf(a.revenue, toMonth(a.at) IN (6, 7, 8)) / sum(a.revenue) AS s
             FROM genesis_institutional.audience_performance a
             JOIN genesis_institutional.projects p ON a.project_id = p.project_id
             WHERE a.channel = 'theatrical' AND a.at < p.released_at + 90
             GROUP BY era)""",
        lambda r: r[0] < 0.20 and r[1] >= 0.35),
    check(
        "2 overrun U-shape (golden-age minimum)",
        """SELECT argMin(name, r), maxIf(r, era_id = 5) - minIf(r, era_id = 3),
                  maxIf(r, era_id = 10) - minIf(r, era_id = 3) FROM (
             SELECT e.era_id AS era_id, e.name AS name,
                    sum(f.actual) / sum(f.planned) AS r
             FROM genesis_institutional.financial_ledger f
             JOIN genesis_institutional.projects p ON f.project_id = p.project_id
             JOIN genesis_institutional.eras e ON p.era_id = e.era_id
             GROUP BY e.era_id, e.name)""",
        lambda r: r[0] == "golden_age" and r[1] >= 0.025 and r[2] >= 0.05),
    check(
        "3 monster-cycle fatigue curve",
        """SELECT groupArray(m) FROM (
             SELECT p.entry_number AS e, sum(a.revenue) / max(p.budget_usd) AS m
             FROM genesis_institutional.audience_performance a
             JOIN genesis_institutional.projects p ON a.project_id = p.project_id
             WHERE p.franchise_id = 'fr-monsters'
             GROUP BY e ORDER BY e)""",
        lambda r: (len(r[0]) == 7 and r[0][1] > r[0][0] and r[0][2] > r[0][0]
                   and r[0][3] < r[0][2] and r[0][4] < r[0][3] and r[0][5] < r[0][4]
                   and r[0][6] == min(r[0]))),
    check(
        "4 home video passes theatrical (sustained, mid-80s)",
        """SELECT min(y) FROM (
             SELECT y, v > t AS lead,
                    min(v > t) OVER (ORDER BY y ROWS BETWEEN CURRENT ROW AND 2 FOLLOWING) AS sustained
             FROM (SELECT toYear(at) AS y,
                          sumIf(revenue, channel = 'home_video') AS v,
                          sumIf(revenue, channel IN ('theatrical', 'theatrical_reissue')) AS t
                   FROM genesis_institutional.audience_performance
                   WHERE toYear(at) BETWEEN 1980 AND 1998 GROUP BY y))
           WHERE sustained = 1""",
        lambda r: 1984 <= r[0] <= 1988),
    check(
        "5 DVD peak 2004±1 then collapse",
        """SELECT argMax(y, v), maxIf(v, y = 2004) / maxIf(v, y = 2012) FROM (
             SELECT toYear(at) AS y, sum(revenue) AS v
             FROM genesis_institutional.audience_performance
             WHERE channel = 'home_video' GROUP BY y)""",
        lambda r: 2003 <= r[0] <= 2005 and r[1] >= 2.5),
    check(
        "6 COVID cliff + production halt",
        """SELECT
             (SELECT sumIf(revenue, toYear(at) = 2020) / sumIf(revenue, toYear(at) = 2019)
              FROM genesis_institutional.audience_performance WHERE channel = 'theatrical'),
             (SELECT countIf(at BETWEEN '2020-04-01' AND '2020-08-31')
                     / countIf(at BETWEEN '2019-04-01' AND '2019-08-31')
              FROM genesis_institutional.production_events)""",
        lambda r: 0.02 <= r[0] <= 0.25 and r[1] <= 0.15),
    check(
        "7 contested pair: premium (+) vs fatigue (−), both powered",
        """SELECT
             maxIf(o, s = 1) - maxIf(o, s = 0),
             maxIf(t, s = 1) - maxIf(t, s = 0),
             minIf(n, s = 1), minIf(n, s = 0)
           FROM (
             SELECT p.is_sequel AS s,
                    avg(x.opening / p.budget_usd) AS o, avg(x.tail) AS t, count() AS n
             FROM (
               SELECT a.project_id,
                      sumIf(a.revenue, a.channel IN ('theatrical', 'pvod')
                            AND a.at < p2.released_at + 30) AS opening,
                      sumIf(a.revenue, a.at >= p2.released_at + 365) / sum(a.revenue) AS tail
               FROM genesis_institutional.audience_performance a
               JOIN genesis_institutional.projects p2 ON a.project_id = p2.project_id
               WHERE p2.released_at >= '1995-01-01' AND p2.released_at < '2023-08-01'
                 AND p2.project_type = 'feature' AND p2.franchise_id != ''
               GROUP BY a.project_id) x
             JOIN genesis_institutional.projects p ON x.project_id = p.project_id
             GROUP BY s)""",
        lambda r: r[0] > 0.05 and r[1] < -0.03 and r[2] >= 30 and r[3] >= 30),
    check(
        "volume: totals in band",
        """SELECT
             (SELECT count() FROM genesis_institutional.audience_performance)
             + (SELECT count() FROM genesis_institutional.production_events)
             + (SELECT count() FROM genesis_institutional.financial_ledger)
             + (SELECT count() FROM genesis_institutional.distribution_events),
             (SELECT count() FROM genesis_institutional.projects)""",
        lambda r: 80_000_000 <= r[0] <= 120_000_000 and 4_500 <= r[1] <= 5_500),
    check(
        "10 class-overrun gradient holds across eras (cross-era truth)",
        """SELECT countIf(tent > ind), count() FROM (
             SELECT p.era_id,
                    sumIf(f.actual, p.budget_class = 'tentpole')
                      / nullIf(sumIf(f.planned, p.budget_class = 'tentpole'), 0) AS tent,
                    sumIf(f.actual, p.budget_class = 'indie')
                      / nullIf(sumIf(f.planned, p.budget_class = 'indie'), 0) AS ind
             FROM genesis_institutional.financial_ledger f
             JOIN genesis_institutional.projects p ON f.project_id = p.project_id
             WHERE p.project_type = 'feature'
             GROUP BY p.era_id
             HAVING tent IS NOT NULL AND ind IS NOT NULL)""",
        lambda r: r[0] >= 6),
    check(
        "scenario cohort: ≥3 titles per window (deflated modern band)",
        """SELECT min(n) FROM (
             SELECT p.release_window, uniqExact(p.project_id) AS n
             FROM genesis_institutional.projects p
             JOIN genesis_institutional.cpi_annual c ON c.year = toYear(p.released_at)
             WHERE p.released_at >= '1985-01-01' AND p.project_type = 'feature'
               AND p.budget_usd * c.mult_to_2026 BETWEEN 20000000 AND 250000000
             GROUP BY p.release_window)""",
        lambda r: r[0] >= 3),
]


def main() -> int:
    from app.config import settings
    import clickhouse_connect

    client = clickhouse_connect.get_client(
        host=settings.clickhouse_host, port=settings.clickhouse_http_port,
        username=settings.clickhouse_writer_user, password=settings.clickhouse_writer_password,
        database=settings.clickhouse_database,
    )
    failed = 0
    for name, sql, ok in PROBES:
        row = client.query(sql).result_rows[0]
        verdict = ok(row)
        print(f"[verify] {'PASS' if verdict else 'FAIL'}  {name}  → {row}")
        failed += 0 if verdict else 1

    print("[verify] fingerprints (seed twice and compare to prove determinism):")
    for table in FACT_TABLES:
        cols = client.query(
            f"SELECT name, type FROM system.columns WHERE database = 'genesis_institutional' "
            f"AND table = '{table}' ORDER BY position").result_rows
        # cityHash64 can't take NULLs — stringify nullable columns instead
        parts = [f"coalesce(toString({name}), '<null>')" if typ.startswith("Nullable") else name
                 for name, typ in cols]
        fp, n = client.query(
            f"SELECT sum(cityHash64(tuple({', '.join(parts)}))), count() "
            f"FROM genesis_institutional.{table}").result_rows[0]
        print(f"[verify]   {table}: rows={n:,} fp={fp}")

    if failed:
        print(f"[verify] {failed} probe(s) FAILED — do not record fixtures from this corpus")
        return 1
    print("[verify] all probes passed — the century is recoverable by SQL")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
