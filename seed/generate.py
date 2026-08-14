"""Deterministic 10-year institutional corpus generator (locked §2.4).

Seeded RNG + engineered correlations so every analysis is reproducible and
demonstrably non-trivial:

  * cost overruns scale with budget class, are amplified by VFX-heavy genres,
    and are slightly tamed on sequels (experienced crews)
  * release-window seasonality lifts Q2/Q4 revenue, suppresses Q1
  * sequel economics are deliberately CONTESTED: sequels open ~38% higher
    (premium) but decay ~55% faster with lower completion (fatigue) — cohort
    slicing decides which story the numbers tell
  * platform mix drifts from theatrical toward svod/avod across the decade
  * schedule slips co-move with overruns; render hours spike pre-release for
    VFX genres

Writes via clickhouse-connect as the `genesis` WRITER user — the agents' path
is exclusively the official mcp-clickhouse server (read-only user).

Usage:  .venv/bin/python -m seed.generate            (defaults: localhost:8123)
        SEED_SCALE=2 .venv/bin/python -m seed.generate
"""
from __future__ import annotations

import math
import os
import random
import sys
import time
from datetime import date, datetime, timedelta

RNG_SEED = 42
TODAY = date(2026, 8, 1)          # corpus horizon is fixed — determinism over freshness
START_YEAR = 2016

GENRES = ["scifi", "fantasy", "action", "drama", "comedy", "horror",
          "thriller", "animation", "documentary", "romance"]
GENRE_WEIGHTS = [10, 8, 12, 16, 12, 8, 10, 8, 8, 8]
# engineered overrun modifiers (VFX-heavy genres run hot)
GENRE_OVERRUN = {"scifi": 0.07, "fantasy": 0.06, "animation": 0.05, "action": 0.04,
                 "thriller": 0.01, "drama": 0.0, "comedy": -0.01, "romance": -0.01,
                 "horror": -0.02, "documentary": -0.04}
CLASS_OVERRUN = {"indie": 0.05, "mid": 0.10, "tentpole": 0.19}
CLASS_BUDGET = {"indie": (2e6, 10e6), "mid": (10e6, 40e6), "tentpole": (40e6, 120e6)}
# revenue multiple of budget (mean), by class — indies punch above their weight
CLASS_REV_MULT = {"indie": 2.6, "mid": 2.2, "tentpole": 2.0}
GENRE_REV_MULT = {"scifi": 1.15, "fantasy": 1.1, "action": 1.1, "animation": 1.2,
                  "horror": 1.35, "comedy": 1.0, "thriller": 1.0, "drama": 0.85,
                  "documentary": 0.6, "romance": 0.9}
WINDOW_SEASONALITY = {"Q1": 0.92, "Q2": 1.15, "Q3": 1.00, "Q4": 1.22}
GENRE_COMPLETION = {"documentary": 0.78, "drama": 0.72, "romance": 0.70, "animation": 0.71,
                    "thriller": 0.69, "scifi": 0.68, "fantasy": 0.67, "comedy": 0.66,
                    "action": 0.64, "horror": 0.58}

TERRITORIES = ["NA", "UK", "FR", "DACH", "IBERIA", "ITALY-ADJ", "NORDICS", "CEE",
               "LATAM", "BRAZIL-ADJ", "APAC", "JP", "KR", "IN", "MENA", "ANZ"]
TERRITORY_WEIGHT = [0.30, 0.07, 0.05, 0.06, 0.03, 0.03, 0.03, 0.03,
                    0.07, 0.05, 0.09, 0.06, 0.04, 0.05, 0.02, 0.02]
DEPTS = ["production", "vfx", "post", "sound", "marketing", "distribution"]
COST_CENTERS = ["above_the_line", "production", "vfx", "post", "sound",
                "marketing", "distribution", "contingency"]
# how strongly each cost center participates in an overrun
CENTER_OVERRUN_WEIGHT = {"above_the_line": 0.2, "production": 1.2, "vfx": 1.8, "post": 1.0,
                         "sound": 0.5, "marketing": 0.4, "distribution": 0.3, "contingency": 2.2}

FRANCHISE_NAMES = ["Nebula Frontier", "Iron Tempest", "Midnight Harbor", "Starfall",
                   "The Last Cartographer", "Crimson Meridian", "Echo Protocol",
                   "Winterlight", "Paper Kingdoms", "Deep Signal"]
TITLE_PARTS_A = ["Silent", "Burning", "Hollow", "Golden", "Broken", "Electric", "Distant",
                 "Savage", "Quiet", "Neon", "Fading", "Iron", "Wild", "Lost", "Shattered"]
TITLE_PARTS_B = ["Horizon", "Garden", "Empire", "Voyage", "Reckoning", "Summer", "Machine",
                 "Covenant", "Orchard", "Signal", "Divide", "Harvest", "Passage", "Vigil", "Country"]


def _quarter(d: date) -> str:
    return f"Q{(d.month - 1) // 3 + 1}"


def build_projects(rng: random.Random) -> list[dict]:
    projects: list[dict] = []
    used_titles: set[str] = set()

    def add(title: str, year: int, genre: str, budget_class: str, is_sequel: int,
            franchise: str, status: str = "released") -> dict:
        lo, hi = CLASS_BUDGET[budget_class]
        budget = rng.uniform(lo, hi)
        greenlit = date(year, rng.randint(1, 12), rng.randint(1, 28))
        prod_days = rng.randint(380, 720) if budget_class != "indie" else rng.randint(240, 480)
        released = greenlit + timedelta(days=prod_days)
        if status != "released" or released > TODAY - timedelta(days=30):
            released_at, status = None, "in_production" if status != "cancelled" else "cancelled"
        else:
            released_at = released
        overrun = (CLASS_OVERRUN[budget_class] + GENRE_OVERRUN[genre]
                   + (-0.03 if is_sequel else 0.0) + rng.gauss(0, 0.05))
        overrun = max(-0.05, overrun)
        proj = {
            "project_id": f"prj-{len(projects) + 1:03d}",
            "title": title,
            "type": "feature" if rng.random() > 0.18 else "series",
            "genre": genre,
            "budget_class": budget_class,
            "budget_usd": round(budget, 2),
            "greenlit_at": greenlit,
            "released_at": released_at,
            "release_window": _quarter(released_at or released),
            "is_sequel": is_sequel,
            "franchise": franchise,
            "status": status,
            # engineered latents (never inserted — they shape the facts)
            "_overrun": overrun,
            "_prod_days": prod_days,
        }
        projects.append(proj)
        used_titles.add(title)
        return proj

    # 10 franchises: original + sequel (sequel 2-4 years later) — the CONTESTED corpus
    for i, name in enumerate(FRANCHISE_NAMES):
        year = START_YEAR + (i % 6)
        genre = rng.choice(["scifi", "fantasy", "action", "horror", "animation"])
        budget_class = rng.choice(["mid", "mid", "tentpole"])
        add(name, year, genre, budget_class, 0, name)
        add(f"{name} 2", year + rng.randint(2, 4), genre, budget_class, 1, name)

    # standalone slate through the decade
    while len(projects) < 58:
        year = rng.randint(START_YEAR, 2025)
        genre = rng.choices(GENRES, weights=GENRE_WEIGHTS)[0]
        budget_class = rng.choices(["indie", "mid", "tentpole"], weights=[4, 5, 2])[0]
        title = f"{rng.choice(TITLE_PARTS_A)} {rng.choice(TITLE_PARTS_B)}"
        if title in used_titles:
            continue
        add(title, year, genre, budget_class, 0, "")

    # a few currently-in-production projects (open cohort questions)
    for _ in range(3):
        year = rng.randint(2025, 2026)
        genre = rng.choices(GENRES, weights=GENRE_WEIGHTS)[0]
        title = f"{rng.choice(TITLE_PARTS_A)} {rng.choice(TITLE_PARTS_B)}"
        if title in used_titles:
            continue
        add(title, year, genre, rng.choice(["mid", "tentpole"]), 0, "", status="in_production")

    # one cancelled cautionary tale
    cancelled = add("Gilded Meridian", 2019, "fantasy", "tentpole", 0, "", status="cancelled")
    cancelled["_overrun"] = 0.62
    return projects


def platform_weights(year: int) -> dict[str, float]:
    """Theatrical→streaming drift across the decade (engineered correlation)."""
    svod = min(0.55, 0.22 + 0.045 * (year - START_YEAR))
    avod = min(0.20, 0.02 + 0.02 * max(0, year - 2019))
    est = 0.12
    theatrical = max(0.15, 1.0 - svod - avod - est)
    return {"theatrical": theatrical, "svod": svod, "avod": avod, "est": est}


def gen_audience(rng: random.Random, proj: dict, scale: float):
    """Daily rows per platform × territory from release to horizon.

    Two revenue regimes per title (engineered): an opening-driven pulse
    (theatrical/est — where the sequel premium lives) and persistent catalog
    value (svod/avod/tv licensing — where franchise fatigue shows up as a
    faster catalog half-life). The long tail is the bulk of the corpus.
    """
    released: date | None = proj["released_at"]
    if released is None:
        return
    horizon = min(TODAY, released + timedelta(days=3400))
    days = (horizon - released).days
    if days <= 0:
        return
    budget = proj["budget_usd"]
    mult = (CLASS_REV_MULT[proj["budget_class"]] * GENRE_REV_MULT[proj["genre"]]
            * WINDOW_SEASONALITY[proj["release_window"]] * rng.gauss(1.0, 0.18))
    mult = max(0.4, mult)
    total_rev_target = budget * mult
    # sequels: higher opening, faster decay everywhere — the contested pair
    opening_boost = 1.38 if proj["is_sequel"] else 1.0
    pulse_decay = (0.030 if proj["is_sequel"] else 0.019) * rng.uniform(0.85, 1.15)
    catalog_half_life = (750 if proj["is_sequel"] else 1150) * rng.uniform(0.85, 1.15)
    pulse_daily = total_rev_target * 0.55 * pulse_decay * opening_boost
    catalog_daily = total_rev_target * 0.45 / catalog_half_life
    completion_base = GENRE_COMPLETION[proj["genre"]] - (0.04 if proj["is_sequel"] else 0.0)
    weights = platform_weights(released.year)
    rev_per_view = {"theatrical": 9.2, "svod": 0.062, "avod": 0.021, "est": 3.4, "tv": 0.31}
    # platform availability windows (day offsets)
    opens = {"theatrical": 0, "est": 30, "svod": 60, "avod": 180, "tv": 365}
    catalog_share = {"svod": 0.52, "avod": 0.26, "tv": 0.22}
    n_terr = max(6, int(len(TERRITORIES) * min(1.0, scale / 2)))
    territories = list(zip(TERRITORIES[:n_terr], TERRITORY_WEIGHT[:n_terr]))
    t_norm = sum(w for _, w in territories)

    for day in range(days):
        d = released + timedelta(days=day)
        pulse = pulse_daily * math.exp(-pulse_decay * day)
        catalog = catalog_daily * math.exp(-day / catalog_half_life)
        # seasonality wobble + weekend lift
        wobble = 1.0 + 0.18 * math.sin(2 * math.pi * (d.timetuple().tm_yday / 365.0)) \
                 + (0.25 if d.weekday() >= 5 else 0.0)
        for platform, open_day in opens.items():
            if day < open_day:
                continue
            if platform == "theatrical":
                if day > 90:
                    continue
                p_rev = pulse * wobble * weights["theatrical"]
            elif platform == "est":
                p_rev = pulse * wobble * weights["est"]
                if p_rev < 2:
                    continue
            else:
                p_rev = catalog * wobble * catalog_share[platform] \
                        * (weights["svod"] + weights["avod"]) * 1.6
            if p_rev < 1:
                continue
            for territory, t_weight in territories:
                revenue = p_rev * (t_weight / t_norm) * rng.uniform(0.7, 1.3)
                if revenue < 0.25:
                    continue
                views = max(1, int(revenue / rev_per_view[platform]))
                completion = (0.97 if platform == "theatrical"
                              else completion_base - 0.02 * math.log1p(day / 365) + rng.gauss(0, 0.03))
                yield [proj["project_id"], proj["title"], d, platform, territory,
                       views, round(min(0.99, max(0.2, completion)), 3), round(revenue, 2)]


def gen_production(rng: random.Random, proj: dict):
    """Daily dept metrics through the production window; slips co-move with overrun."""
    start: date = proj["greenlit_at"]
    end = start + timedelta(days=proj["_prod_days"])
    if proj["status"] == "cancelled":
        end = start + timedelta(days=int(proj["_prod_days"] * 0.6))
    end = min(end, TODAY)
    overrun = proj["_overrun"]
    vfx_heavy = proj["genre"] in ("scifi", "fantasy", "animation", "action")
    total_days = max(1, (end - start).days)
    slip_budget = max(0.0, overrun) * 90  # engineered: total slip days track the overrun
    day = 0
    d = start
    while d < end:
        progress = day / total_days
        for dept in DEPTS:
            burn = proj["budget_usd"] / total_days / len(DEPTS)
            burn *= 1.0 + overrun * CENTER_OVERRUN_WEIGHT.get(dept, 1.0) * progress
            yield [proj["project_id"], datetime(d.year, d.month, d.day, 18), dept,
                   "daily_burn", "usd", round(burn * rng.uniform(0.8, 1.2), 2)]
            crew = 12 + 60 * math.sin(math.pi * min(1.0, progress * 1.1)) * (1 + max(0.0, overrun) * 0.5)
            yield [proj["project_id"], datetime(d.year, d.month, d.day, 9), dept,
                   "crew_hours", "hours", round(crew * 8 * rng.uniform(0.85, 1.15), 1)]
        if vfx_heavy and progress > 0.5:
            hours = 800 * progress * (1 + max(0.0, overrun)) * rng.uniform(0.7, 1.4)
            yield [proj["project_id"], datetime(d.year, d.month, d.day, 22), "vfx",
                   "render_farm", "gpu_hours", round(hours, 1)]
        if rng.random() < min(0.25, slip_budget / total_days * 3):
            yield [proj["project_id"], datetime(d.year, d.month, d.day, 12), "production",
                   "schedule_slip", "days", round(rng.uniform(0.5, 3.0), 1)]
        d += timedelta(days=1)
        day += 1


def gen_financial(rng: random.Random, proj: dict):
    """Monthly planned-vs-actual per cost center; actuals carry the overrun."""
    start: date = proj["greenlit_at"]
    months = max(3, proj["_prod_days"] // 30)
    if proj["status"] == "cancelled":
        months = int(months * 0.6)
    overrun = proj["_overrun"]
    center_share = {"above_the_line": 0.16, "production": 0.30, "vfx": 0.18, "post": 0.10,
                    "sound": 0.04, "marketing": 0.14, "distribution": 0.05, "contingency": 0.03}
    for m in range(months):
        d = start + timedelta(days=30 * m)
        if d > TODAY:
            break
        # marketing burst in the last quarter before release
        phase = m / months
        for center in COST_CENTERS:
            share = center_share[center]
            if center == "marketing":
                share *= 0.3 if phase < 0.7 else 2.6
            planned = proj["budget_usd"] * share / months
            actual = planned * (1 + overrun * CENTER_OVERRUN_WEIGHT[center] * phase
                                + rng.gauss(0, 0.06))
            yield [proj["project_id"], d, center, "spend",
                   round(planned, 2), round(max(0.0, actual), 2)]


def gen_distribution(rng: random.Random, proj: dict):
    released: date | None = proj["released_at"]
    greenlit: date = proj["greenlit_at"]
    yield [proj["project_id"], greenlit, "deal", "all", "GLOBAL",
           round(proj["budget_usd"] * rng.uniform(0.1, 0.35), 2)]
    if released is None:
        return
    for territory in TERRITORIES[:10]:
        yield [proj["project_id"], released + timedelta(days=rng.randint(0, 21)),
               "theatrical_open", "theatrical", territory, 0.0]
    for platform, lag in (("est", 30), ("svod", 60), ("avod", 180)):
        yield [proj["project_id"], released + timedelta(days=lag), "window_open",
               platform, "GLOBAL", 0.0]
    if proj["budget_class"] == "indie" and rng.random() < 0.5:
        yield [proj["project_id"], released - timedelta(days=rng.randint(30, 120)),
               "festival", "theatrical", rng.choice(["NA", "FR", "DACH"]), 0.0]


def main() -> int:
    scale = float(os.getenv("SEED_SCALE", "2"))
    sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    from app.config import settings

    import clickhouse_connect

    client = clickhouse_connect.get_client(
        host=settings.clickhouse_host, port=settings.clickhouse_http_port,
        username=settings.clickhouse_writer_user, password=settings.clickhouse_writer_password,
        database=settings.clickhouse_database,
    )
    print(f"[seed] connected to ClickHouse {settings.clickhouse_host}:{settings.clickhouse_http_port} "
          f"db={settings.clickhouse_database} scale={scale}")

    existing = client.query("SELECT count() FROM projects").result_rows[0][0]
    if existing:
        print(f"[seed] projects already seeded ({existing} rows) — wiping for a clean deterministic corpus")
        for table in ("projects", "production_events", "financial_ledger",
                      "audience_performance", "distribution_events"):
            client.command(f"TRUNCATE TABLE {table}")

    rng = random.Random(RNG_SEED)
    projects = build_projects(rng)
    dims = [[p["project_id"], p["title"], p["type"], p["genre"], p["budget_class"],
             p["budget_usd"], p["greenlit_at"], p["released_at"], p["release_window"],
             p["is_sequel"], p["franchise"], p["status"]] for p in projects]
    client.insert("projects", dims, column_names=[
        "project_id", "title", "type", "genre", "budget_class", "budget_usd",
        "greenlit_at", "released_at", "release_window", "is_sequel", "franchise", "status"])
    print(f"[seed] projects: {len(dims)} "
          f"(released={sum(1 for p in projects if p['released_at'])}, "
          f"sequels={sum(p['is_sequel'] for p in projects)})")

    # one seed batch legitimately spans the whole decade (~130 monthly partitions)
    insert_settings = {"max_partitions_per_insert_block": 500}

    def flush(table: str, cols: list[str], gen, batch_size: int = 400_000) -> int:
        batch, total, t0 = [], 0, time.time()
        for row in gen:
            batch.append(row)
            if len(batch) >= batch_size:
                client.insert(table, batch, column_names=cols, settings=insert_settings)
                total += len(batch)
                batch = []
                print(f"[seed]   {table}: {total:,} rows ({time.time() - t0:.0f}s)")
        if batch:
            client.insert(table, batch, column_names=cols, settings=insert_settings)
            total += len(batch)
        print(f"[seed] {table}: {total:,} rows in {time.time() - t0:.0f}s")
        return total

    grand = 0
    grand += flush("audience_performance",
                   ["project_id", "title", "at", "platform", "territory", "views", "completion", "revenue"],
                   (row for p in projects for row in gen_audience(rng, p, scale)))
    grand += flush("production_events",
                   ["project_id", "at", "dept", "event_type", "metric", "value"],
                   (row for p in projects for row in gen_production(rng, p)))
    grand += flush("financial_ledger",
                   ["project_id", "at", "cost_center", "category", "planned", "actual"],
                   (row for p in projects for row in gen_financial(rng, p)))
    grand += flush("distribution_events",
                   ["project_id", "at", "event_type", "platform", "territory", "value"],
                   (row for p in projects for row in gen_distribution(rng, p)))
    print(f"[seed] TOTAL fact rows: {grand:,}")
    for table in ("projects", "production_events", "financial_ledger",
                  "audience_performance", "distribution_events", "financial_monthly", "audience_monthly"):
        n = client.query(f"SELECT count() FROM {table}").result_rows[0][0]
        print(f"[seed]   verify {table}: {n:,}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
