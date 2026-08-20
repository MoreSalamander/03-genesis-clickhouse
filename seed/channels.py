"""Per-title channel parameters — the Python half of the audience expansion.

For every released project this module decides which revenue channels the title
plays in (era-gated), when each opens and closes, its cadence, its base
per-period revenue (normalized so the decay series sums to the title's channel
share), and the engineered sequel economics (opening boost on the pulse, tail
multiplier on the catalog decay). ClickHouse expands these ~40k parameter rows
into ~70M fact rows (seed/expand.py).

Three curve tables carry the macro century so the era truths hold regardless of
title mix: `year_curve` (channel demand by year — the video gold rush, the DVD
peak, the COVID cliff live here), `price_curve` (nominal unit prices — a 1912
ticket costs $0.07, a 2026 ticket $12.50), and `territories` (six groups,
prefix-normalized weights, vault-rollout activation dates).
"""
from __future__ import annotations

import math
from datetime import date, timedelta

from seed import config
from seed.config import stream_rng

HORIZON = config.HORIZON
VAULT = config.CONVERGENCE_PLUS_LAUNCH

# lifetime revenue share by channel, per release era (features)
FEATURE_MIX: dict[int, dict[str, float]] = {
    1: {"theatrical": .92, "theatrical_reissue": .05, "tv_licensing": .02,
        "streaming_licensed": .02, "streaming_own": .01},
    2: {"theatrical": .88, "theatrical_reissue": .06, "tv_licensing": .04, "home_video": .01,
        "streaming_licensed": .02, "streaming_own": .01},
    3: {"theatrical": .80, "theatrical_reissue": .08, "tv_licensing": .07, "syndication": .02,
        "home_video": .02, "streaming_licensed": .02, "streaming_own": .01},
    4: {"theatrical": .78, "theatrical_reissue": .04, "tv_licensing": .10, "syndication": .04,
        "home_video": .02, "streaming_licensed": .02, "streaming_own": .02},
    5: {"theatrical": .70, "tv_licensing": .12, "syndication": .08, "pay_cable": .04,
        "home_video": .03, "streaming_licensed": .02, "streaming_own": .03},
    6: {"theatrical": .55, "pay_cable": .08, "home_video": .18, "tv_licensing": .08,
        "syndication": .04, "streaming_licensed": .02, "streaming_own": .06},
    7: {"theatrical": .38, "home_video": .40, "pay_cable": .07, "tv_licensing": .06,
        "ppv_vod": .02, "streaming_licensed": .04, "streaming_own": .03},
    8: {"theatrical": .35, "home_video": .42, "pay_cable": .06, "tv_licensing": .04,
        "est": .03, "ppv_vod": .01, "streaming_licensed": .05, "streaming_own": .04},
    9: {"theatrical": .42, "home_video": .18, "est": .06, "ppv_vod": .03, "pay_cable": .04,
        "streaming_licensed": .18, "streaming_own": .09},
    10: {"theatrical": .40, "pvod": .09, "est": .04, "ppv_vod": .03, "pay_cable": .02,
         "streaming_own": .42},
}
TYPE_MIX: dict[str, dict[str, float]] = {
    "short": {"theatrical": .95, "tv_licensing": .05},
    "serial": {"theatrical": .95, "tv_licensing": .05},
    "tv_movie": {"tv_licensing": .75, "syndication": .20, "streaming_own": .05},
}

CADENCE = {"theatrical": 7, "theatrical_reissue": 7, "pvod": 7,
           "tv_licensing": 91, "syndication": 91, "pay_cable": 91,
           "home_video": 30, "ppv_vod": 30, "est": 30,
           "streaming_licensed": 1, "streaming_own": 1}
PLATFORM = {"theatrical": "first_run", "theatrical_reissue": "reissue",
            "tv_licensing": "broadcast", "syndication": "basic_cable",
            "pay_cable": "premium_cable", "home_video": "vhs", "ppv_vod": "ppv",
            "est": "est_store", "pvod": "pvod",
            "streaming_licensed": "partner_svod", "streaming_own": "convergence_plus"}
# quarterly licensing happens in waves, not every quarter
PARTICIPATION = {"tv_licensing": 34, "syndication": 28, "pay_cable": 45}

TERRITORY_ACTIVATION = {  # Convergence+ rollout; every other channel is active from day one
    "domestic": date(1912, 6, 8), "uk_ireland": date(2021, 3, 1), "europe": date(2021, 9, 1),
    "latam": date(2022, 1, 15), "asia_pacific": date(2022, 6, 1), "row": date(2022, 9, 1),
}
TERRITORY_WEIGHTS = {"domestic": .42, "uk_ireland": .10, "europe": .18,
                     "latam": .09, "asia_pacific": .14, "row": .07}


def _terr_count(era_id: int, channel: str) -> int:
    if channel in ("streaming_own", "streaming_licensed"):
        return config.PARTNER_DAILY_TERRITORIES
    if channel in ("tv_licensing", "syndication", "pay_cable", "ppv_vod", "est", "pvod"):
        return 2
    if channel == "home_video":
        return 4
    return 2 if era_id <= 2 else (3 if era_id <= 4 else (4 if era_id <= 7 else 6))


def _weeks_theatrical(era_id: int) -> int:
    return {1: 8, 2: 8, 3: 10, 4: 12, 5: 14, 6: 16, 7: 14, 8: 12, 9: 10, 10: 8}[era_id]


def _interp(points: list[tuple[int, float]]) -> dict[int, float]:
    """Linear interpolation of (year, value) anchors across 1912–2026."""
    out: dict[int, float] = {}
    for (y0, v0), (y1, v1) in zip(points, points[1:]):
        for y in range(y0, y1 + 1):
            out[y] = v0 + (v1 - v0) * (y - y0) / max(1, y1 - y0)
    return out


# demand curves: the macro century per channel (1.0 = reference demand)
YEAR_CURVES: dict[str, dict[int, float]] = {
    # secular demand only — the 1918/Depression/WWII/COVID dents come from the
    # shock calendar at row level (seed/expand.py), so they are NOT in this curve
    "theatrical": _interp([(1912, .35), (1920, .6), (1930, 1.0), (1933, .95), (1937, .95),
                           (1941, .95), (1946, 1.05), (1950, .95), (1953, .88), (1958, .62),
                           (1963, .55), (1969, .55), (1972, .52), (1977, .66), (1982, .70),
                           (1989, .74), (1995, .80), (2002, .90), (2009, .84), (2015, .80),
                           (2019, .78), (2020, .75), (2021, .72), (2022, .65), (2024, .66),
                           (2026, .70)]),
    "theatrical_reissue": _interp([(1912, 1.0), (1954, 1.0), (1958, .5), (1970, .25),
                                   (1990, .12), (2026, .10)]),
    "tv_licensing": _interp([(1955, .6), (1960, 1.0), (1966, 1.3), (1975, 1.15), (1985, .95),
                             (1995, .8), (2005, .6), (2015, .5), (2026, .42)]),
    "syndication": _interp([(1970, .7), (1980, 1.0), (1995, .95), (2010, .7), (2026, .5)]),
    "pay_cable": _interp([(1977, .5), (1983, 1.0), (1995, 1.1), (2010, .9), (2019, .7), (2026, .5)]),
    "home_video": _interp([(1980, .15), (1983, .52), (1986, 1.05), (1990, 1.3), (1996, 1.35),
                           (1998, 1.5), (2001, 1.7), (2003, 2.3), (2004, 2.6), (2005, 2.0),
                           (2007, 1.45), (2009, 1.1), (2012, .5)]),
    "ppv_vod": _interp([(1992, .5), (2000, 1.0), (2012, 1.0), (2026, .8)]),
    "est": _interp([(2006, .6), (2012, 1.0), (2020, 1.1), (2026, .9)]),
    "pvod": _interp([(2020, 1.4), (2022, 1.0), (2026, .85)]),
    "streaming_licensed": _interp([(2008, .3), (2012, .8), (2015, 1.1), (2018, 1.25),
                                   (2019, 1.2), (2020, .15), (2023, .2), (2024, .6), (2026, .8)]),
    "streaming_own": _interp([(2020, .8), (2022, 1.1), (2024, 1.2), (2026, 1.25)]),
}

# nominal unit prices (revenue per view); 0 = licensing line, views recorded as 0
PRICE_CURVES: dict[str, dict[int, float]] = {
    "theatrical": _interp([(1912, .07), (1920, .15), (1930, .23), (1940, .24), (1948, .40),
                           (1956, .50), (1963, .85), (1971, 1.65), (1978, 2.34), (1985, 3.55),
                           (1992, 4.15), (2000, 5.39), (2008, 7.18), (2016, 8.65),
                           (2020, 9.16), (2023, 10.53), (2026, 12.50)]),
    "theatrical_reissue": _interp([(1912, .05), (1948, .30), (1975, 1.2), (2026, 9.0)]),
    "home_video": _interp([(1980, 55.0), (1988, 30.0), (1997, 22.0), (2004, 16.0), (2012, 12.0)]),
    "ppv_vod": _interp([(1992, 4.0), (2026, 6.5)]),
    "est": _interp([(2006, 12.0), (2026, 14.0)]),
    "pvod": _interp([(2020, 19.99), (2026, 24.0)]),
    "streaming_licensed": _interp([(2008, .02), (2026, .025)]),
    "streaming_own": _interp([(2020, .033), (2026, .038)]),
    "tv_licensing": _interp([(1955, 0.0), (2026, 0.0)]),
    "syndication": _interp([(1970, 0.0), (2026, 0.0)]),
    "pay_cable": _interp([(1977, 0.0), (2026, 0.0)]),
}

# vault catalog: any title on Convergence+ earns a floor by age tier ($/day/territory-pool)
def _vault_floor(release_year: int) -> float:
    if release_year >= 2015:
        return 14.0
    if release_year >= 2000:
        return 6.0
    if release_year >= 1970:
        return 2.4
    return 0.9


def _licensed_floor(release_year: int) -> float:
    if release_year >= 2010:
        return 4.0
    if release_year >= 1990:
        return 1.6
    if release_year >= 1960:
        return 0.7
    return 0.35


def _geo_sum(decay: float, periods: int) -> float:
    if decay <= 0:
        return float(periods)
    return (1 - math.exp(-decay * (periods + 1))) / (1 - math.exp(-decay))


def params_for(p: dict) -> list[list]:
    """Parameter rows for one released project.

    Row: [project_id, title, channel, platform, open_d, close_d, cadence,
          max_periods, base, decay, opening_boost, boost_periods,
          completion_base, participation, terr_count, floor]
    """
    released: date | None = p["released_at"]
    if released is None:
        return []
    era_id = p["era_id"]
    rev_target = p["budget_usd"] * p["_rev_mult"]
    mix = TYPE_MIX.get(p["project_type"])
    if mix is None:
        mix = FEATURE_MIX[era_id]
    if p["project_type"] == "streaming_original":
        mix = {"streaming_licensed": 1.0} if released < VAULT else {"streaming_own": 1.0}
    rng = stream_rng("channels", p["project_id"])
    rows: list[list] = []

    for channel, share in mix.items():
        birth, death = config.CHANNEL_GATES[channel]
        share_rev = rev_target * share
        boost, boost_periods = 1.0, 0
        completion = 0.0
        participation = PARTICIPATION.get(channel, 100)
        terr = _terr_count(era_id, channel)

        if channel == "theatrical":
            open_d = released
            weeks = _weeks_theatrical(era_id)
            close_d = released + timedelta(days=weeks * 7)
            decay = 0.45 if released >= config.REGIME_FLIP else 0.25
            boost, boost_periods = p["_opening_boost"], 2
            periods = weeks
        elif channel == "theatrical_reissue":
            if released.year >= 1958:
                continue
            open_d = released + timedelta(days=rng.randint(6 * 365, 16 * 365))
            close_d = open_d + timedelta(days=35)
            decay, periods = 0.3, 5
        elif channel == "tv_licensing":
            open_d = max(birth, released + timedelta(days=3 * 365))
            close_d = HORIZON
            decay = 0.02
            periods = (close_d - open_d).days // 91
        elif channel == "syndication":
            open_d = max(birth, released + timedelta(days=6 * 365))
            close_d = HORIZON
            decay = 0.03
            periods = (close_d - open_d).days // 91
        elif channel == "pay_cable":
            open_d = max(birth, released + timedelta(days=270))
            close_d = min(HORIZON, open_d + timedelta(days=12 * 365))
            decay = 0.10
            periods = (close_d - open_d).days // 91
        elif channel == "home_video":
            open_d = max(birth, released + timedelta(days=180))
            close_d = death
            if open_d >= close_d:
                continue
            decay = 0.045
            periods = (close_d - open_d).days // 30
        elif channel == "ppv_vod":
            open_d = max(birth, released + timedelta(days=120))
            close_d = min(HORIZON, open_d + timedelta(days=8 * 365))
            decay, periods = 0.08, (close_d - open_d).days // 30
        elif channel == "est":
            open_d = max(birth, released + timedelta(days=90))
            close_d = HORIZON
            decay = 0.05
            periods = (close_d - open_d).days // 30
        elif channel == "pvod":
            open_d = released + timedelta(days=17)
            close_d = open_d + timedelta(days=56)
            decay, periods = 0.35, 8
            boost, boost_periods = p["_opening_boost"], 2
        elif channel == "streaming_licensed":
            completion = p["_completion_base"]
            # licensing returns in the 2024–26 profitability correction, thinner
            if released < date(2024, 1, 1):
                ret_open, ret_close = max(date(2024, 1, 1), released + timedelta(days=365)), HORIZON
                ret_periods = (ret_close - ret_open).days
                if ret_periods > 0:
                    ret_base = (share_rev * 0.30) / max(1.0, _geo_sum(0.0008, ret_periods))
                    rows.append([p["project_id"], p["title"], channel, PLATFORM[channel],
                                 ret_open, ret_close, 1, int(ret_periods),
                                 round(ret_base, 6), 0.0008, 1.0, 0,
                                 round(completion, 4), 100, terr, 0.03])
            open_d = max(birth, released + timedelta(days=2 * 365), date(2015, 1, 1))
            close_d = date(2019, 12, 31)   # the 2019 pull-back
            if open_d >= close_d:
                continue
            decay = 0.0015
            periods = (close_d - open_d).days
        elif channel == "streaming_own":
            open_d = max(VAULT, released + timedelta(days=45))
            close_d = HORIZON
            if open_d >= close_d:
                continue
            decay = 0.003 if released >= date(2019, 1, 1) else 0.0004
            periods = (close_d - open_d).days
            completion = p["_completion_base"]
        else:
            continue

        if periods <= 0:
            continue
        # sequels: catalog decays faster (the fatigue reading)
        if p["is_sequel"] and channel not in ("theatrical", "pvod", "theatrical_reissue"):
            decay = decay / max(0.2, p["_tail_mult"])
        base = share_rev / max(1.0, _geo_sum(decay, periods))
        if channel == "streaming_own":
            base = max(base, _vault_floor(released.year) * config.SEED_SCALE)
        elif channel == "streaming_licensed":
            base = max(base, _licensed_floor(released.year) * config.SEED_SCALE)
        floor = 0.03 if CADENCE[channel] == 1 else 0.5
        rows.append([p["project_id"], p["title"], channel, PLATFORM[channel],
                     open_d, min(close_d, HORIZON), CADENCE[channel], int(periods),
                     round(base, 6), round(decay, 6), round(boost, 4), boost_periods,
                     round(completion, 4), participation, terr, floor])
    return rows


def all_params(projects: list[dict]) -> list[list]:
    rows: list[list] = []
    for p in projects:
        rows.extend(params_for(p))
    return rows


PARAM_COLUMNS = ["project_id", "title", "channel", "platform", "open_d", "close_d",
                 "cadence", "max_periods", "base", "decay", "opening_boost",
                 "boost_periods", "completion_base", "participation", "terr_count", "floor"]


def year_curve_rows() -> list[list]:
    rows = []
    for channel, curve in YEAR_CURVES.items():
        for year in range(config.START_YEAR, HORIZON.year + 1):
            rows.append([channel, year, round(curve.get(year, list(curve.values())[-1] if max(curve) < year else 1.0), 4)])
    return rows


def price_curve_rows() -> list[list]:
    rows = []
    for channel, curve in PRICE_CURVES.items():
        last = None
        for year in range(config.START_YEAR, HORIZON.year + 1):
            if year in curve:
                last = curve[year]
            rows.append([channel, year, round(last if last is not None else 0.0, 4)])
    return rows


def territory_rows() -> list[list]:
    """[idx, name, active_from, w2, w3, w4, w6] — prefix-normalized weights."""
    names = config.TERRITORY_GROUPS
    weights = [TERRITORY_WEIGHTS[n] for n in names]
    rows = []
    for i, name in enumerate(names):
        norm = {}
        for k in (2, 3, 4, 6):
            prefix = weights[:k]
            norm[k] = weights[i] / sum(prefix) if i < k else 0.0
        rows.append([i, name, TERRITORY_ACTIVATION[name],
                     round(norm[2], 5), round(norm[3], 5), round(norm[4], 5), round(norm[6], 5)])
    return rows


# ── distribution events (small, built in Python) ─────────────────────────────

EVENT_FOR_CHANNEL = {"theatrical_reissue": "reissue", "tv_licensing": "tv_license_deal",
                     "syndication": "window_open", "pay_cable": "window_open",
                     "home_video": "video_release", "ppv_vod": "window_open",
                     "est": "window_open", "pvod": "window_open",
                     "streaming_licensed": "window_open", "streaming_own": "platform_launch"}


def distribution_rows(projects: list[dict]) -> list[list]:
    """deal / theatrical_open / window events / reissues / festivals / strike delays."""
    from seed import shocks as shocks_mod

    rows: list[list] = []
    for p in projects:
        rng = stream_rng("distribution", p["project_id"])
        rows.append([p["project_id"], p["greenlit_at"], "deal", "all", "domestic",
                     round(p["budget_usd"] * rng.uniform(0.1, 0.35), 2)])
        released = p["released_at"]
        if released is None:
            continue
        n_terr = _terr_count(p["era_id"], "theatrical")
        for name in config.TERRITORY_GROUPS[:n_terr]:
            rows.append([p["project_id"],
                         released + timedelta(days=rng.randint(0, 21)),
                         "theatrical_open", "first_run", name, 0.0])
        for row in params_for(p):
            channel, platform, open_d = row[2], row[3], row[4]
            if channel == "theatrical":
                continue
            event = EVENT_FOR_CHANNEL.get(channel, "window_open")
            rows.append([p["project_id"], open_d, event, platform, "domestic", 0.0])
        if p["division"] == "specialty" or (p["budget_class"] == "indie" and rng.random() < 0.4):
            rows.append([p["project_id"], released - timedelta(days=rng.randint(30, 120)),
                         "festival", "first_run",
                         rng.choice(["domestic", "europe", "uk_ireland"]), 0.0])
        # a halt window that swallowed 45+ days of the production shows as a delay
        for s in shocks_mod.SHOCKS:
            if not s.production_halt:
                continue
            overlap = (min(released, s.end) - max(p["greenlit_at"], s.start)).days
            if overlap >= 45:
                rows.append([p["project_id"], s.end, "strike_delay", "all", "domestic",
                             float(overlap)])
    return rows
