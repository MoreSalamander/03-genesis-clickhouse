"""Century-corpus knobs — every dial in one place.

Convergence Studios, founded 1912-06-08: a composite mirror of the two oldest
Hollywood majors (both founded 1912). The corpus spans 1912 → 2026-08-01 across
ten industry eras (seed/eras.py), a real CPI deflator (seed/cpi.py), a real
shock calendar (seed/shocks.py), and ~25 beat-for-beat landmark analogues
(seed/beats.py). Titles are fictional; the economics are not.

Determinism: every stream draws from its OWN seeded RNG (stream_rng), so adding
or reordering generators never shifts another stream's numbers — the fragility
of the old single sequence-coupled random.Random(42) is gone. In-ClickHouse
noise is cityHash64-derived (seed/expand.py), stable on the pinned 24.8 image.
"""
from __future__ import annotations

import os
import random
from datetime import date

SEED_VERSION = "genesis-v2"
RNG_SEED = 42

FOUNDED = date(1912, 6, 8)
START_YEAR = 1912
HORIZON = date(2026, 8, 1)        # corpus horizon is fixed — determinism over freshness

# ---------------------------------------------------------------------------
# volume dials (the row budget lives or dies on the streaming-daily grain)
# ---------------------------------------------------------------------------
# The whole vault lands on Convergence+ at launch (2020-07) — the fictional
# differentiator, and the dominant row term (~52M daily rows).
VAULT_AT_LAUNCH = True
# Territory groups reporting daily streaming rows once fully rolled out.
PARTNER_DAILY_TERRITORIES = 6
# Third per-day production metric (render/crew/burn all on) — ~5M rows.
PROD_THIRD_METRIC = True
# SEED_SCALE multiplies streaming library density (NEW semantic — the old knob
# only shrank territories). 1.0 = the ~96M budget; 0.3 ≈ lean ~35M.
SEED_SCALE = float(os.getenv("SEED_SCALE", "1.0"))


def stream_rng(*key: object) -> random.Random:
    """One independent, order-insensitive RNG per generation stream."""
    return random.Random(f"{SEED_VERSION}|{RNG_SEED}|" + "|".join(map(str, key)))


# ---------------------------------------------------------------------------
# territory groups (coarse on purpose; foreign detail grows by era)
# ---------------------------------------------------------------------------
TERRITORY_GROUPS = ["domestic", "uk_ireland", "europe", "latam", "asia_pacific", "row"]
# base mix of the FOREIGN share across groups (domestic handled separately)
FOREIGN_MIX = {"uk_ireland": 0.22, "europe": 0.34, "latam": 0.14, "asia_pacific": 0.22, "row": 0.08}


def domestic_share(year: int) -> float:
    """Domestic/foreign revenue split drifts 65/35 (1912) → 35/65 (2020s)."""
    lo, hi = 1912, 2020
    t = min(1.0, max(0.0, (year - lo) / (hi - lo)))
    return 0.65 - 0.30 * t


# ---------------------------------------------------------------------------
# genres — century vocabulary (westerns die ~1970; musicals boom and bust;
# noir is a 40s-50s creature; per-era weights live in seed/eras.py)
# ---------------------------------------------------------------------------
GENRES = ["western", "musical", "war", "noir",
          "scifi", "fantasy", "action", "drama", "comedy", "horror",
          "thriller", "animation", "documentary", "romance"]

# engineered overrun modifiers (VFX-heavy genres run hot; docs run cold)
GENRE_OVERRUN = {"scifi": 0.07, "fantasy": 0.06, "animation": 0.05, "action": 0.04,
                 "war": 0.05, "musical": 0.03, "western": 0.01, "noir": 0.0,
                 "thriller": 0.01, "drama": 0.0, "comedy": -0.01, "romance": -0.01,
                 "horror": -0.02, "documentary": -0.04}
# revenue multiple modifiers by genre (horror punches above its weight in every era)
GENRE_REV_MULT = {"scifi": 1.15, "fantasy": 1.1, "action": 1.1, "animation": 1.2,
                  "horror": 1.35, "comedy": 1.0, "thriller": 1.0, "drama": 0.85,
                  "documentary": 0.6, "romance": 0.9,
                  "western": 1.05, "musical": 1.1, "war": 1.05, "noir": 0.9}
# streaming completion base (streaming channels only; everything else is NULL)
GENRE_COMPLETION = {"documentary": 0.78, "drama": 0.72, "romance": 0.70, "animation": 0.71,
                    "thriller": 0.69, "scifi": 0.68, "fantasy": 0.67, "comedy": 0.66,
                    "action": 0.64, "horror": 0.58,
                    "western": 0.66, "musical": 0.65, "war": 0.67, "noir": 0.70}

# ---------------------------------------------------------------------------
# departments and cost centers (era-gated vocabulary; shares in seed/eras.py)
# ---------------------------------------------------------------------------
DEPTS = ["production", "camera", "art", "post", "sound", "marketing", "distribution", "vfx"]
# how strongly each cost center participates in an overrun
CENTER_OVERRUN_WEIGHT = {"above_the_line": 0.2, "production": 1.2, "sets_costumes": 1.0,
                         "vfx": 1.8, "post": 1.0, "sound": 0.5, "music": 0.4,
                         "marketing": 0.4, "p_and_a": 0.4, "distribution": 0.3,
                         "studio_overhead": 0.1, "contingency": 2.2, "covid_protocols": 1.5}

# ---------------------------------------------------------------------------
# channels — birth/death gates (None = still alive at the horizon)
# ---------------------------------------------------------------------------
CHANNEL_GATES: dict[str, tuple[date, date | None]] = {
    "theatrical":         (date(1912, 6, 8), None),
    "theatrical_reissue": (date(1920, 1, 1), None),          # meaningful pre-1955, rare after
    "tv_licensing":       (date(1955, 3, 1), None),          # the library goes to television
    "syndication":        (date(1970, 9, 1), None),
    "pay_cable":          (date(1977, 6, 1), None),
    "home_video":         (date(1980, 3, 1), date(2012, 12, 31)),
    "ppv_vod":            (date(1992, 1, 1), None),
    "est":                (date(2006, 4, 1), None),
    "pvod":               (date(2020, 4, 10), None),
    "streaming_licensed": (date(2008, 6, 1), None),
    "streaming_own":      (date(2020, 7, 15), None),         # Convergence+ launch day
}

CONVERGENCE_PLUS_LAUNCH = date(2020, 7, 15)
DVD_INTRO_YEAR = 1997
DVD_PEAK_YEAR = 2004
VIDEO_CROSSOVER_YEAR = 1986   # first year home_video revenue exceeds theatrical
STREAMING_ORIGINALS_START = 2015

# seasonality regime flip: the 1975 summer blockbuster (seed/beats.py "Leviathan")
REGIME_FLIP = date(1975, 6, 20)


def summer_share(year: int) -> float:
    """Engineered share of first-run theatrical revenue landing Jun–Aug."""
    return 0.40 if date(year, 6, 20) >= REGIME_FLIP and year >= 1975 else 0.18


# ---------------------------------------------------------------------------
# the slate plan — per-year, per-type output counts (deterministic)
# ---------------------------------------------------------------------------
# (start_year, end_year, features_lo, features_hi)
FEATURE_BANDS = [
    (1912, 1912, 5, 5), (1913, 1913, 12, 12), (1914, 1914, 20, 20), (1915, 1915, 30, 30),
    (1916, 1927, 48, 68),
    (1928, 1933, 38, 50),
    (1934, 1948, 48, 62),
    (1949, 1955, 26, 36),
    (1956, 1965, 16, 26),
    (1966, 1975, 13, 21),
    (1976, 1990, 13, 19),
    (1991, 2005, 16, 23),
    (2006, 2019, 15, 21),
    (2020, 2021, 8, 12),
    (2022, 2026, 12, 16),
]
SHORT_BANDS = [(1912, 1929, 24, 34), (1930, 1948, 10, 16), (1949, 1956, 3, 7)]
SERIAL_BANDS = [(1914, 1946, 2, 3)]           # chapter-play seasons, one entry per season
TV_MOVIE_BANDS = [(1964, 1995, 6, 10), (1996, 2005, 3, 5)]
STREAMING_ORIGINAL_BANDS = [(2015, 2019, 5, 8), (2020, 2026, 8, 13)]

TYPE_BANDS = {
    "feature": FEATURE_BANDS,
    "short": SHORT_BANDS,
    "serial": SERIAL_BANDS,
    "tv_movie": TV_MOVIE_BANDS,
    "streaming_original": STREAMING_ORIGINAL_BANDS,
}


def slate_plan() -> dict[int, dict[str, int]]:
    """Deterministic per-year output: {year: {project_type: count}}.

    The 2026 slate stops at the horizon (Aug 1), so its count is pro-rated.
    """
    plan: dict[int, dict[str, int]] = {y: {} for y in range(START_YEAR, HORIZON.year + 1)}
    for ptype, bands in TYPE_BANDS.items():
        for (lo_y, hi_y, lo_n, hi_n) in bands:
            for year in range(lo_y, hi_y + 1):
                if year > HORIZON.year:
                    continue
                rng = stream_rng("slate-count", ptype, year)
                n = rng.randint(lo_n, hi_n)
                if year == HORIZON.year:
                    n = max(1, int(n * (HORIZON.timetuple().tm_yday / 365.0)))
                plan[year][ptype] = n
    return plan


def slate_total() -> int:
    return sum(n for counts in slate_plan().values() for n in counts.values())


# ---------------------------------------------------------------------------
# title fabric (fictional; beats pin their own exact titles)
# ---------------------------------------------------------------------------
TITLE_PARTS_A = ["Silent", "Burning", "Hollow", "Golden", "Broken", "Electric", "Distant",
                 "Savage", "Quiet", "Neon", "Fading", "Iron", "Wild", "Lost", "Shattered",
                 "Gilded", "Crimson", "Velvet", "Midnight", "Scarlet", "Radiant", "Forgotten",
                 "Restless", "Painted", "Hidden", "Roaring", "Gentle", "Reckless", "Marble",
                 "Copper", "Ashen", "Emerald", "Thundering", "Wandering", "Last", "First",
                 "Stolen", "Borrowed", "Endless", "Nameless"]
TITLE_PARTS_B = ["Horizon", "Garden", "Empire", "Voyage", "Reckoning", "Summer", "Machine",
                 "Covenant", "Orchard", "Signal", "Divide", "Harvest", "Passage", "Vigil",
                 "Country", "Boulevard", "Cavalcade", "Serenade", "Frontier", "Ballroom",
                 "Prairie", "Cathedral", "Carnival", "Meridian", "Lantern", "Compass",
                 "Waltz", "Parade", "Junction", "Crossing", "Fortune", "Bargain", "Gamble",
                 "Sentinel", "Harbor", "Canyon", "Regiment", "Overture", "Masquerade",
                 "Testament", "Furlough", "Armistice", "Dispatch", "Payroll", "Matinee",
                 "Intermission", "Premiere", "Encore"]
TITLE_TAILS = ["of the West", "of Yesterday", "at Dawn", "of the Deep", "in Winter",
               "of the Republic", "on the River", "of the Century", "at Midnight",
               "of the Valley", "in the Sky", "of Fortune", "on the Wire",
               "of the Ninth", "beyond the Ridge", "under Glass", "of the Coast",
               "in Exile", "of the Silver Coast", "after the War", "at the Fairgrounds",
               "of Two Cities", "on the Frontier", "of the Interior"]
