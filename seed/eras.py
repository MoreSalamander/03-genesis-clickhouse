"""The ten industry eras, 1912–2026, as data.

Every fact stream reads its era's parameters from here: the overrun profile
(the century's U-shape — factory-era discipline is the minimum), nominal budget
bands, genre weights (westerns die ~1970, noir is a 40s–50s creature, the
musical booms with sound and busts by 1931), cost-center vocabulary (studio
overhead is a golden-age line; P&A explodes post-1975; covid_protocols exists
for three years), shoot-day norms, and which franchise economics an era breeds.

Boundaries are exact and contiguous: era 5 ends 1975-06-19 because the summer
blockbuster (seed/beats.py "Leviathan", released 1975-06-20) IS the boundary.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date


@dataclass(frozen=True)
class Era:
    era_id: int
    name: str
    start: date
    end: date
    summary: str
    overrun_mu: float                      # mean cost overrun (actual/planned − 1)
    overrun_sd: float
    budget_lo: float                       # typical feature band, NOMINAL dollars
    budget_hi: float
    spectacle_hi: float                    # tail max (epics/roadshows/tentpole events)
    spectacle_p: float                     # probability a feature draws from the tail
    shoot_days: tuple[int, int]            # planned shoot-day band for features
    genre_weights: dict[str, int]
    cost_shares: dict[str, float]          # financial_ledger cost centers, sums to ~1.0
    sequel_mode: str                       # cycle_type franchises born in this era use
    type_budget_factor: dict[str, tuple[float, float]] = field(default_factory=dict)
    # ^ nominal budget band for non-feature types, absolute dollars


ERAS: list[Era] = [
    Era(1, "silent", date(1912, 6, 8), date(1927, 9, 30),
        "Feature transition, serials and shorts, theatrical-only revenue; the 1918 "
        "influenza closes the theaters for two months.",
        overrun_mu=0.08, overrun_sd=0.06,
        budget_lo=10_000, budget_hi=100_000, spectacle_hi=1_500_000, spectacle_p=0.010,
        shoot_days=(18, 45),
        genre_weights={"western": 18, "comedy": 16, "drama": 20, "romance": 12,
                       "action": 10, "war": 6, "thriller": 5, "documentary": 4,
                       "horror": 3, "fantasy": 3, "animation": 2, "scifi": 1,
                       "musical": 0, "noir": 0},
        cost_shares={"above_the_line": 0.10, "production": 0.34, "sets_costumes": 0.20,
                     "post": 0.05, "sound": 0.01, "music": 0.02, "marketing": 0.05,
                     "distribution": 0.06, "studio_overhead": 0.17},
        sequel_mode="serial",
        type_budget_factor={"short": (2_000, 8_000), "serial": (30_000, 80_000)}),

    Era(2, "sound_depression", date(1927, 10, 1), date(1934, 6, 30),
        "Talkie conversion capex, the 1930 box-office peak, then the Depression "
        "crash and receivership — the studio nearly dies.",
        overrun_mu=0.10, overrun_sd=0.07,
        budget_lo=50_000, budget_hi=420_000, spectacle_hi=900_000, spectacle_p=0.008,
        shoot_days=(24, 40),
        genre_weights={"musical": 12, "drama": 18, "comedy": 14, "horror": 8,
                       "western": 10, "romance": 10, "thriller": 6, "action": 6,
                       "war": 4, "documentary": 3, "fantasy": 3, "animation": 3,
                       "noir": 2, "scifi": 1},
        cost_shares={"above_the_line": 0.12, "production": 0.30, "sets_costumes": 0.18,
                     "post": 0.06, "sound": 0.05, "music": 0.04, "marketing": 0.06,
                     "distribution": 0.05, "studio_overhead": 0.14},
        sequel_mode="monster_cycle",
        type_budget_factor={"short": (3_000, 10_000), "serial": (40_000, 90_000)}),

    Era(3, "golden_age", date(1934, 7, 1), date(1948, 5, 2),
        "The factory at full discipline: contract talent, standing sets, the lowest "
        "overruns of the century; WWII attendance peaks in 1946.",
        overrun_mu=0.035, overrun_sd=0.02,
        budget_lo=100_000, budget_hi=1_500_000, spectacle_hi=3_000_000, spectacle_p=0.010,
        shoot_days=(22, 48),
        genre_weights={"drama": 16, "western": 12, "musical": 12, "comedy": 12,
                       "war": 8, "romance": 9, "thriller": 7, "horror": 6,
                       "noir": 6, "action": 6, "animation": 4, "documentary": 3,
                       "fantasy": 2, "scifi": 1},
        cost_shares={"above_the_line": 0.16, "production": 0.26, "sets_costumes": 0.16,
                     "post": 0.06, "sound": 0.04, "music": 0.04, "marketing": 0.07,
                     "distribution": 0.05, "studio_overhead": 0.16},
        sequel_mode="monster_cycle",
        type_budget_factor={"short": (4_000, 12_000), "serial": (45_000, 100_000)}),

    Era(4, "decree_tv", date(1948, 5, 3), date(1962, 6, 30),
        "The decree strips the theaters; television empties the seats; output "
        "halves; widescreen spectacle fights back; in 1955 the library goes to TV.",
        overrun_mu=0.09, overrun_sd=0.05,
        budget_lo=400_000, budget_hi=3_000_000, spectacle_hi=13_500_000, spectacle_p=0.020,
        shoot_days=(30, 60),
        genre_weights={"western": 14, "drama": 15, "musical": 10, "comedy": 10,
                       "war": 8, "noir": 8, "thriller": 8, "scifi": 6,
                       "romance": 7, "horror": 5, "action": 6, "animation": 3,
                       "documentary": 2, "fantasy": 2},
        cost_shares={"above_the_line": 0.20, "production": 0.28, "sets_costumes": 0.14,
                     "post": 0.06, "sound": 0.03, "music": 0.03, "marketing": 0.09,
                     "distribution": 0.06, "studio_overhead": 0.11},
        sequel_mode="b_franchise",
        type_budget_factor={"short": (5_000, 15_000)}),

    Era(5, "conglomerate", date(1962, 7, 1), date(1975, 6, 19),
        "The studio system ends; conglomerates buy the lot; packaging drives "
        "overruns up; roadshow flops nearly sink the industry 1969–71; the first "
        "made-for-TV movies air in 1964.",
        overrun_mu=0.14, overrun_sd=0.09,
        budget_lo=1_000_000, budget_hi=5_000_000, spectacle_hi=20_000_000, spectacle_p=0.020,
        shoot_days=(35, 70),
        genre_weights={"drama": 16, "comedy": 10, "thriller": 10, "action": 10,
                       "war": 7, "western": 6, "musical": 6, "horror": 6,
                       "scifi": 6, "romance": 6, "documentary": 4, "animation": 3,
                       "fantasy": 3, "noir": 2},
        cost_shares={"above_the_line": 0.24, "production": 0.28, "sets_costumes": 0.10,
                     "post": 0.07, "sound": 0.03, "music": 0.03, "marketing": 0.12,
                     "distribution": 0.06, "contingency": 0.02, "studio_overhead": 0.05},
        sequel_mode="b_franchise",
        type_budget_factor={"tv_movie": (400_000, 900_000)}),

    Era(6, "blockbuster", date(1975, 6, 20), date(1985, 12, 31),
        "Leviathan opens wide in June 1975 and summer becomes the season; pay "
        "cable arrives 1977, the VCR 1980 — the studio sues, then profits.",
        overrun_mu=0.12, overrun_sd=0.08,
        budget_lo=3_000_000, budget_hi=18_000_000, spectacle_hi=36_000_000, spectacle_p=0.020,
        shoot_days=(45, 80),
        genre_weights={"action": 14, "comedy": 12, "drama": 12, "thriller": 11,
                       "scifi": 10, "horror": 10, "fantasy": 6, "romance": 6,
                       "animation": 4, "war": 4, "musical": 3, "western": 2,
                       "documentary": 3, "noir": 1},
        cost_shares={"above_the_line": 0.18, "production": 0.28, "vfx": 0.06,
                     "sets_costumes": 0.08, "post": 0.07, "sound": 0.03, "music": 0.03,
                     "p_and_a": 0.18, "distribution": 0.05, "contingency": 0.04},
        sequel_mode="numbered_sequel",
        type_budget_factor={"tv_movie": (900_000, 2_000_000)}),

    Era(7, "home_video", date(1986, 1, 1), date(1995, 12, 31),
        "Video revenue passes theatrical in 1986; sell-through pricing, multiplex "
        "boom, the sequel machine normalizes; the 1988 writers' strike stops work "
        "for 22 weeks.",
        overrun_mu=0.08, overrun_sd=0.04,
        budget_lo=8_000_000, budget_hi=34_000_000, spectacle_hi=60_000_000, spectacle_p=0.020,
        shoot_days=(45, 85),
        genre_weights={"action": 14, "comedy": 13, "drama": 12, "thriller": 11,
                       "scifi": 8, "horror": 8, "romance": 8, "fantasy": 6,
                       "animation": 6, "war": 4, "documentary": 4, "musical": 2,
                       "western": 2, "noir": 1},
        cost_shares={"above_the_line": 0.17, "production": 0.26, "vfx": 0.09,
                     "sets_costumes": 0.07, "post": 0.07, "sound": 0.03, "music": 0.03,
                     "p_and_a": 0.19, "distribution": 0.04, "contingency": 0.05},
        sequel_mode="numbered_sequel",
        type_budget_factor={"tv_movie": (2_000_000, 4_000_000)}),

    Era(8, "dvd_peak", date(1996, 1, 1), date(2007, 6, 30),
        "DVD arrives 1997 and mints money until the 2004 peak — the margin golden "
        "age; budgets and P&A explode; franchises become the tentpole strategy.",
        overrun_mu=0.09, overrun_sd=0.05,
        budget_lo=20_000_000, budget_hi=90_000_000, spectacle_hi=150_000_000, spectacle_p=0.030,
        shoot_days=(50, 90),
        genre_weights={"action": 13, "comedy": 11, "drama": 11, "fantasy": 10,
                       "scifi": 10, "animation": 9, "thriller": 9, "horror": 7,
                       "romance": 7, "war": 4, "documentary": 4, "musical": 2,
                       "western": 1, "noir": 1},
        cost_shares={"above_the_line": 0.16, "production": 0.24, "vfx": 0.13,
                     "sets_costumes": 0.06, "post": 0.07, "sound": 0.03, "music": 0.02,
                     "p_and_a": 0.21, "distribution": 0.03, "contingency": 0.05},
        sequel_mode="franchise_premium",
        type_budget_factor={"tv_movie": (3_000_000, 6_000_000)}),

    Era(9, "streaming_transition", date(2007, 7, 1), date(2019, 12, 31),
        "Streaming starts as found money — rich licensing — while DVD collapses; "
        "the slate consolidates into fewer, bigger franchises; in 2019 the studio "
        "pulls its library back for a platform of its own.",
        overrun_mu=0.11, overrun_sd=0.06,
        budget_lo=25_000_000, budget_hi=140_000_000, spectacle_hi=250_000_000, spectacle_p=0.030,
        shoot_days=(50, 95),
        genre_weights={"action": 13, "scifi": 11, "fantasy": 10, "drama": 11,
                       "animation": 9, "comedy": 9, "thriller": 9, "horror": 8,
                       "documentary": 6, "romance": 5, "war": 3, "musical": 3,
                       "western": 1, "noir": 1},
        cost_shares={"above_the_line": 0.14, "production": 0.23, "vfx": 0.17,
                     "sets_costumes": 0.05, "post": 0.07, "sound": 0.02, "music": 0.02,
                     "p_and_a": 0.22, "distribution": 0.03, "contingency": 0.05},
        sequel_mode="franchise_premium",
        type_budget_factor={"streaming_original": (15_000_000, 60_000_000)}),

    Era(10, "streaming_wars_covid", date(2020, 1, 1), date(2026, 8, 1),
        "COVID closes the theaters and halts production; Convergence+ launches "
        "2020-07 with the whole vault; PVOD breaks the window; the 2023 double "
        "strike stops everything again; 2024–26 is the profitability correction.",
        overrun_mu=0.13, overrun_sd=0.07,
        budget_lo=30_000_000, budget_hi=160_000_000, spectacle_hi=260_000_000, spectacle_p=0.025,
        shoot_days=(50, 95),
        genre_weights={"action": 13, "drama": 12, "scifi": 10, "fantasy": 9,
                       "horror": 9, "animation": 9, "comedy": 9, "thriller": 9,
                       "documentary": 6, "romance": 5, "musical": 3, "war": 3,
                       "western": 1, "noir": 1},
        cost_shares={"above_the_line": 0.13, "production": 0.22, "vfx": 0.16,
                     "sets_costumes": 0.05, "post": 0.06, "sound": 0.02, "music": 0.02,
                     "p_and_a": 0.20, "distribution": 0.03, "contingency": 0.05,
                     "covid_protocols": 0.06},
        sequel_mode="legacy_revival",
        type_budget_factor={"streaming_original": (20_000_000, 90_000_000)}),
]


def era_for(d: date) -> Era:
    for era in ERAS:
        if era.start <= d <= era.end:
            return era
    raise ValueError(f"{d} is outside the corpus (1912-06-08 .. 2026-08-01)")


def era_for_year(year: int) -> Era:
    """The era holding July 1 of the year (a year's 'home' era)."""
    return era_for(date(year, 7, 1) if year > 1912 else date(1912, 7, 1))


def rows() -> list[list]:
    """eras table rows: [era_id, name, start_date, end_date, summary]."""
    return [[e.era_id, e.name, e.start, e.end, e.summary] for e in ERAS]
