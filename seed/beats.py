"""Beat-for-beat landmarks: every real inflection gets a fictional twin.

The Studio Head chose beat-for-beat fidelity (2026-08-19): the corpus carries a
pinned filmography whose shape a film historian would recognize — the 1931
monster cycle that ends in a 1948 parody, the 1956 widescreen gamble, the 1963
runaway epic, the June 1975 wide-open summer that flips seasonality forever,
the 1980 auteur catastrophe, the 1993 VFX watershed, the 2020 platform launch —
with fictional titles and real-shaped economics. Everything here is pinned and
deterministic; the generic slate (seed/slate.py) fills the years around it.

CYCLE_SHAPES is the franchise machinery for GENERATED franchises; pinned beats
carry their own exact numbers and override any shape. The modern shapes are
engineered so the contested pair stays contested: sequels OPEN bigger
(opening_boost > 1 → the premium reading) while their tails die faster
(tail_mult < 1 → the fatigue reading). Both true, sliced differently — that
disagreement is the product's thesis and a test depends on it.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date


@dataclass(frozen=True)
class Beat:
    """A pinned project. Fields left None are drawn from era norms in slate.py."""
    title: str
    project_type: str
    genre: str
    released: date | None
    budget: float                 # NOMINAL dollars of its year
    rev_mult: float               # lifetime revenue target / budget (all channels)
    overrun: float | None = None  # actual/planned − 1; None → era draw
    shoot_planned: int | None = None
    shoot_actual: int | None = None
    greenlit: date | None = None
    franchise_id: str = ""
    entry: int = 0
    status: str = "released"
    sound_format: str | None = None
    color_format: str | None = None
    aspect: str | None = None
    note: str = ""


@dataclass(frozen=True)
class FranchiseDef:
    franchise_id: str
    name: str
    cycle_type: str
    genre: str
    notes: str = ""


# ---------------------------------------------------------------------------
# cycle machinery for GENERATED franchises (relative to entry 1 of the cycle)
# ---------------------------------------------------------------------------
CYCLE_SHAPES: dict[str, dict] = {
    # chapter-play seasons: steady, cheap, dependable
    "serial": {"rev_curve": [1.00, 0.95, 0.90, 0.85], "opening_boost": [1.0, 1.0, 1.0, 1.0],
               "tail_mult": 1.0, "budget_curve": [1.0, 1.0, 1.05, 1.05],
               "entries": (2, 4), "gap_years": (1, 1)},
    # the monster shape: the mate outgrosses the monster, the house parties decay,
    # the parody is the cycle's floor — and its cheapest, still-profitable entry
    "monster_cycle": {"rev_curve": [1.00, 1.18, 1.12, 0.72, 0.52, 0.40, 0.33],
                      "opening_boost": [1.0, 1.20, 1.15, 1.10, 1.05, 1.0, 1.0],
                      "tail_mult": 0.90, "budget_curve": [1.0, 1.10, 1.05, 0.85, 0.72, 0.62, 0.55],
                      "entries": (4, 7), "gap_years": (2, 4)},
    # the B-machine: tiny budgets, flat demand, the best per-dollar ROI in the vault
    "b_franchise": {"rev_curve": [1.00, 1.02, 0.98, 1.00, 0.95, 0.92, 0.88],
                    "opening_boost": [1.0, 1.0, 1.0, 1.0, 1.0, 1.0, 1.0],
                    "tail_mult": 1.0, "budget_curve": [1.0, 1.0, 1.0, 1.05, 1.05, 1.05, 1.1],
                    "entries": (4, 7), "gap_years": (1, 2)},
    # numbered sequels, 70s–80s: totals halve while budgets climb
    "numbered_sequel": {"rev_curve": [1.00, 0.55, 0.34, 0.22],
                        "opening_boost": [1.0, 1.25, 1.10, 1.00],
                        "tail_mult": 0.75, "budget_curve": [1.0, 1.20, 1.25, 1.20],
                        "entries": (2, 4), "gap_years": (2, 4)},
    # the franchise-premium era, mid-90s→2010s: sequels genuinely exceed
    "franchise_premium": {"rev_curve": [1.00, 1.25, 1.32, 1.12],
                          "opening_boost": [1.0, 1.35, 1.40, 1.30],
                          "tail_mult": 0.95, "budget_curve": [1.0, 1.30, 1.45, 1.50],
                          "entries": (2, 4), "gap_years": (2, 3)},
    # the modern shape: revivals still OPEN huge (premium) and die fast (fatigue)
    "legacy_revival": {"rev_curve": [1.00, 0.72, 0.50],
                       "opening_boost": [1.0, 1.32, 1.20],
                       "tail_mult": 0.70, "budget_curve": [1.0, 1.25, 1.30],
                       "entries": (2, 3), "gap_years": (2, 3)},
}

# ---------------------------------------------------------------------------
# pinned franchises
# ---------------------------------------------------------------------------
FRANCHISES: list[FranchiseDef] = [
    FranchiseDef("fr-verity", "The Perils of Verity", "serial", "action",
                 "The chapter-play that taught the studio serialized demand."),
    FranchiseDef("fr-monsters", "The Monster Cycle", "monster_cycle", "horror",
                 "1931–1948: the complete fatigue curve, parody included."),
    FranchiseDef("fr-kettleworth", "The Kettleworths", "b_franchise", "comedy",
                 "Six entries, tiny budgets — the best per-dollar ROI on the books."),
    FranchiseDef("fr-approach", "Final Approach", "numbered_sequel", "action",
                 "The disaster cycle: each landing softer than the last."),
    FranchiseDef("fr-leviathan", "Leviathan", "numbered_sequel", "thriller",
                 "The June 1975 wide release that invented the summer."),
    FranchiseDef("fr-starfall", "Starfall Legion", "franchise_premium", "scifi",
                 "The space saga: premium era, then a strike-delayed return."),
    FranchiseDef("fr-antediluvian", "Antediluvian", "franchise_premium", "scifi",
                 "The 1993 VFX watershed and its diminishing shores."),
    FranchiseDef("fr-chimera", "The Chimera Cycle", "franchise_premium", "fantasy",
                 "The trilogy where each December outgrossed the last."),
    FranchiseDef("fr-irontempest", "Iron Tempest", "legacy_revival", "action",
                 "A 90s original revived day-and-date in the PVOD window."),
    FranchiseDef("fr-nebula", "Nebula Frontier", "legacy_revival", "scifi",
                 "The modern franchise; its next entry is the standing greenlight question."),
]

# ---------------------------------------------------------------------------
# the pinned filmography (chronological)
# ---------------------------------------------------------------------------
BEATS: list[Beat] = [
    Beat("The Toll Road", "feature", "western", date(1913, 9, 19), 18_000, 2.6,
         overrun=0.06, shoot_planned=24, shoot_actual=26, greenlit=date(1913, 2, 10),
         note="The studio's first feature-length picture."),
    Beat("The Perils of Verity", "serial", "action", date(1915, 3, 6), 45_000, 2.8,
         franchise_id="fr-verity", entry=1, note="Chapter one of the chapter-plays."),
    Beat("The Perils of Verity: Second Season", "serial", "action", date(1916, 3, 4),
         46_000, 2.65, franchise_id="fr-verity", entry=2),
    Beat("The Perils of Verity: Third Season", "serial", "action", date(1917, 3, 3),
         48_000, 2.5, franchise_id="fr-verity", entry=3),
    Beat("Cathedral of the Sun", "feature", "drama", date(1923, 4, 14), 1_350_000, 3.2,
         overrun=0.22, shoot_planned=96, shoot_actual=117, greenlit=date(1921, 11, 2),
         note="The silent-era gamble that paid — the biggest thing the studio had built."),
    Beat("The Midnight Chorus", "feature", "musical", date(1927, 11, 23), 420_000, 3.8,
         overrun=0.15, shoot_planned=38, shoot_actual=44, sound_format="mono",
         note="The first talkie — lines around the block, stages rewired overnight."),
    Beat("Encore Tonight", "feature", "musical", date(1931, 3, 6), 380_000, 0.55,
         note="The musical glut: audiences fled the genre overnight."),

    # the monster cycle — the complete fatigue curve
    Beat("Nocturne", "feature", "horror", date(1931, 2, 13), 290_000, 4.10,
         franchise_id="fr-monsters", entry=1, note="The February gamble that built a genre."),
    Beat("The Galvanic Man", "feature", "horror", date(1931, 11, 21), 310_000, 4.35,
         franchise_id="fr-monsters", entry=2, note="Bigger than Nocturne — the cycle ignites."),
    Beat("Mate of the Galvanic Man", "feature", "horror", date(1935, 4, 20), 320_000, 4.60,
         franchise_id="fr-monsters", entry=3, note="The sequel that outgrossed everything before it."),
    Beat("Son of Nocturne", "feature", "horror", date(1939, 1, 13), 300_000, 3.00,
         franchise_id="fr-monsters", entry=4),
    Beat("House of Shadows", "feature", "horror", date(1944, 12, 1), 280_000, 2.10,
         franchise_id="fr-monsters", entry=5, note="Every monster in one house — the crowd thins."),
    Beat("Return of the Galvanic Man", "feature", "horror", date(1946, 6, 7), 260_000, 1.55,
         franchise_id="fr-monsters", entry=6),
    Beat("Loose & Fastwick Meet the Galvanic Man", "feature", "comedy", date(1948, 6, 15),
         240_000, 1.35, franchise_id="fr-monsters", entry=7,
         note="The parody that closed the cycle — cheap, profitable, and the end."),

    Beat("The Long Furrow", "feature", "drama", date(1936, 8, 21), 900_000, 2.7,
         overrun=0.008, shoot_planned=34, shoot_actual=34, greenlit=date(1936, 1, 6),
         note="Factory discipline: shot in 34 days, released in month eight, on budget."),
    Beat("Golden Boulevard", "feature", "noir", date(1947, 10, 3), 700_000, 2.4,
         note="The shadows the decade earned."),

    # the B-machine
    Beat("The Kettleworths", "feature", "comedy", date(1949, 4, 1), 320_000, 4.4,
         franchise_id="fr-kettleworth", entry=1, note="The B-unit's golden goose."),
    Beat("The Kettleworths Go to Town", "feature", "comedy", date(1950, 4, 7), 330_000, 4.6,
         franchise_id="fr-kettleworth", entry=2),
    Beat("The Kettleworths on the Farm", "feature", "comedy", date(1951, 5, 4), 335_000, 4.3,
         franchise_id="fr-kettleworth", entry=3),
    Beat("The Kettleworths at the Fair", "feature", "comedy", date(1953, 4, 10), 350_000, 4.1,
         franchise_id="fr-kettleworth", entry=4),
    Beat("The Kettleworths Abroad", "feature", "comedy", date(1954, 6, 11), 360_000, 3.9,
         franchise_id="fr-kettleworth", entry=5),
    Beat("The Kettleworths' Last Picnic", "feature", "comedy", date(1956, 5, 18), 380_000, 3.6,
         franchise_id="fr-kettleworth", entry=6),

    Beat("The Silver Meridian", "feature", "western", date(1953, 9, 25), 2_800_000, 3.1,
         aspect="scope", note="The widescreen counterpunch: television cannot do THIS."),
    Beat("The Deluge", "feature", "war", date(1956, 11, 9), 13_200_000, 2.9,
         overrun=0.195, shoot_planned=118, shoot_actual=141, greenlit=date(1954, 8, 16),
         aspect="scope", note="The biggest gamble since the receivership — and it held."),
    Beat("The Serpent Queen", "feature", "drama", date(1963, 6, 12), 14_000_000, 0.85,
         overrun=0.90, shoot_planned=90, shoot_actual=196, greenlit=date(1960, 9, 1),
         aspect="scope", note="The runaway epic that ended an era's appetite for epics."),
    Beat("Signal Fire", "tv_movie", "thriller", date(1964, 10, 7), 480_000, 1.6,
         note="The first picture made for the box in the parlor."),

    Beat("Final Approach", "feature", "action", date(1970, 12, 18), 4_200_000, 3.4,
         franchise_id="fr-approach", entry=1, note="The disaster formula, assembled."),
    Beat("Final Approach '73", "feature", "action", date(1973, 10, 12), 5_000_000, 2.2,
         franchise_id="fr-approach", entry=2),
    Beat("Final Approach: Overwater", "feature", "action", date(1975, 12, 19), 6_000_000, 1.5,
         franchise_id="fr-approach", entry=3),
    Beat("Final Approach: Concourse", "feature", "action", date(1978, 8, 4), 6_500_000, 0.95,
         franchise_id="fr-approach", entry=4, note="The landing nobody asked for."),

    # THE regime flip
    Beat("Leviathan", "feature", "thriller", date(1975, 6, 20), 4_000_000, 7.5,
         overrun=1.25, shoot_planned=55, shoot_actual=159, greenlit=date(1974, 3, 20),
         franchise_id="fr-leviathan", entry=1,
         note="Mechanical trouble, an overrun for the ages, a June wide release — "
              "and the summer belongs to the movies forever after."),
    Beat("Leviathan II", "feature", "thriller", date(1978, 6, 16), 9_000_000, 3.2,
         franchise_id="fr-leviathan", entry=2),
    Beat("Leviathan III", "feature", "thriller", date(1983, 7, 22), 14_000_000, 1.8,
         franchise_id="fr-leviathan", entry=3),
    Beat("Leviathan: Requiem", "feature", "thriller", date(1987, 7, 17), 18_000_000, 0.85,
         franchise_id="fr-leviathan", entry=4, note="The tail that finally stopped moving."),

    Beat("Starfall Legion", "feature", "scifi", date(1978, 5, 25), 11_000_000, 5.4,
         franchise_id="fr-starfall", entry=1, note="The saga the summer was waiting for."),
    Beat("Starfall Legion II: The Iron Tide", "feature", "scifi", date(1981, 5, 22),
         13_000_000, 5.8, franchise_id="fr-starfall", entry=2),
    Beat("Starfall Legion III: Homeworld", "feature", "scifi", date(1984, 5, 25),
         16_000_000, 4.9, franchise_id="fr-starfall", entry=3),
    Beat("Starfall: Dominion", "feature", "scifi", date(2024, 6, 14), 175_000_000, 2.2,
         greenlit=date(2021, 11, 8), franchise_id="fr-starfall", entry=4,
         note="Moved eight months by the double strike; the saga returns anyway."),

    Beat("The Meridian Gate", "feature", "western", date(1980, 11, 19), 36_000_000, 0.22,
         overrun=1.10, shoot_planned=70, shoot_actual=148, greenlit=date(1978, 6, 1),
         note="The auteur blank check, revoked in public."),
    Beat("Antediluvian", "feature", "scifi", date(1993, 6, 11), 63_000_000, 5.6,
         shoot_planned=70, shoot_actual=82, franchise_id="fr-antediluvian", entry=1,
         note="The VFX watershed: what the computers made walk."),
    Beat("Antediluvian: Lost Shores", "feature", "scifi", date(1997, 5, 23), 73_000_000, 4.1,
         franchise_id="fr-antediluvian", entry=2),
    Beat("Antediluvian III", "feature", "scifi", date(2001, 7, 18), 93_000_000, 3.0,
         franchise_id="fr-antediluvian", entry=3),

    Beat("The Chimera Cycle", "feature", "fantasy", date(1999, 12, 17), 110_000_000, 3.9,
         franchise_id="fr-chimera", entry=1),
    Beat("Chimera: The Sundering", "feature", "fantasy", date(2002, 12, 18), 115_000_000, 4.4,
         franchise_id="fr-chimera", entry=2),
    Beat("Chimera: Crownfall", "feature", "fantasy", date(2004, 12, 15), 125_000_000, 4.6,
         franchise_id="fr-chimera", entry=3, note="Each December outgrossed the last."),

    Beat("Iron Tempest", "feature", "action", date(1994, 7, 15), 42_000_000, 3.3,
         franchise_id="fr-irontempest", entry=1),
    Beat("Iron Tempest: Aftershock", "feature", "action", date(1997, 6, 27), 50_000_000, 2.1,
         franchise_id="fr-irontempest", entry=2),
    Beat("Iron Tempest: Legacy", "feature", "action", date(2021, 3, 19), 90_000_000, 1.6,
         greenlit=date(2019, 1, 14), franchise_id="fr-irontempest", entry=3,
         note="Day-and-date in the 17-day window: the revival that opened huge and vanished."),

    Beat("Nebula Frontier", "feature", "scifi", date(2016, 7, 8), 145_000_000, 2.8,
         franchise_id="fr-nebula", entry=1),
    Beat("Nebula Frontier: Ascension", "feature", "scifi", date(2019, 5, 24),
         165_000_000, 2.45, franchise_id="fr-nebula", entry=2,
         note="Opened a third bigger; the tail died a third faster. Both readings are true."),

    Beat("The Hollow Crossing", "feature", "action", date(2020, 12, 18), 110_000_000, 0.50,
         overrun=0.18, greenlit=date(2018, 9, 3),
         note="The Q4 2020 experiment: released into empty theaters to prove the window existed."),
    Beat("Winter Signal", "feature", "thriller", date(2020, 10, 9), 45_000_000, 0.62,
         overrun=0.15, greenlit=date(2019, 2, 11),
         note="October 2020, masks on: the year's other theatrical gamble."),

    Beat("Glasshouse", "streaming_original", "drama", date(2015, 11, 6), 22_000_000, 1.4,
         note="The first original made for someone else's platform."),
    Beat("Meridian Rising", "streaming_original", "scifi", date(2020, 7, 15), 85_000_000, 1.8,
         greenlit=date(2018, 10, 1),
         note="Convergence+ launches with the whole vault behind it and this out front."),

    Beat("Gilded Meridian", "feature", "fantasy", None, 160_000_000, 0.0,
         overrun=0.62, greenlit=date(2018, 3, 5), status="cancelled",
         note="The cautionary tale: written down, never released."),
]


def beat_titles() -> set[str]:
    return {b.title for b in BEATS}


def beats_for_year(year: int) -> list[Beat]:
    return [b for b in BEATS
            if (b.released and b.released.year == year)
            or (b.released is None and b.greenlit and b.greenlit.year == year)]
