"""The filmography: ~4,600 projects, 1912–2026, beats pinned and slate filled.

Per year and type, the plan (seed/config.slate_plan) says how many pictures the
studio made; the pinned beats (seed/beats.py) take their year's slots first;
franchise machinery emits due entries next (with each cycle's engineered
economics); standalone titles fill the rest from era genre weights and budget
bands. budget_class is assigned LAST, as a percentile within a rolling decade
of same-type budgets — a 1939 tentpole cost $1.2M and is still a tentpole.

Every project carries private latents (keys starting "_") that the fact
expansions read — overrun, revenue multiple, opening boost, tail multiplier,
shoot days — and that never land in the projects table themselves.
"""
from __future__ import annotations

import math
from datetime import date, timedelta

from seed import beats as beats_mod
from seed import config, eras
from seed.beats import CYCLE_SHAPES, Beat

# release-month weights by seasonality regime (index 0 = January)
CLASSIC_MONTHS = [1.0, 1.0, 1.4, 1.4, 0.9, 0.6, 0.6, 0.7, 1.0, 1.2, 1.8, 2.0]
BLOCKBUSTER_MONTHS = [0.5, 0.6, 0.8, 0.9, 1.8, 2.2, 2.1, 1.4, 0.7, 0.9, 1.5, 1.7]

# greenlight-to-release gap (days) by era_id
GREENLIGHT_GAP = {1: (90, 200), 2: (90, 220), 3: (120, 260), 4: (200, 400),
                  5: (300, 600), 6: (350, 700), 7: (350, 700), 8: (450, 900),
                  9: (450, 900), 10: (450, 900)}
TYPE_GAP = {"short": (30, 90), "serial": (120, 240), "tv_movie": (120, 260),
            "streaming_original": (300, 600)}

SEQUEL_SUFFIXES = {
    "serial": ["Second Season", "Third Season", "Fourth Season"],
    "monster_cycle": ["Returns", "The Bride", "The Son", "The House", "The Ghost", "Meets the Professor"],
    "b_franchise": ["Go to Town", "On the Farm", "At the Fair", "Abroad", "In the Navy", "Strike Gold"],
    "numbered_sequel": ["II", "III", "IV"],
    "franchise_premium": ["The Reckoning", "Ascendant", "Crownfall", "Eternal"],
    "legacy_revival": ["Legacy", "Reborn", "Dominion"],
}


def _quarter(d: date) -> str:
    return f"Q{(d.month - 1) // 3 + 1}"


def _release_date(rng, year: int) -> date:
    if year == 2020:
        # the shutdown year has two real release seasons: the normal first
        # quarter, and the thin Q4 experiments into limited-capacity theaters
        month = rng.choices([1, 2, 3, 10, 11, 12], weights=[2.2, 2.2, 1.6, 0.5, 0.8, 0.9])[0]
        return date(2020, month, rng.randint(1, 28))
    regime = BLOCKBUSTER_MONTHS if date(year, 7, 1) >= config.REGIME_FLIP else CLASSIC_MONTHS
    months = range(1, 13) if year > 1912 else range(9, 13)   # founded June 1912
    month = rng.choices(months, weights=regime[months[0] - 1:])[0]
    return date(year, month, rng.randint(1, 28))


def _budget(rng, era: eras.Era, ptype: str) -> float:
    if ptype != "feature" and ptype in era.type_budget_factor:
        lo, hi = era.type_budget_factor[ptype]
        return round(math.exp(rng.uniform(math.log(lo), math.log(hi))), 2)
    if ptype == "feature" and rng.random() < era.spectacle_p:
        return round(rng.uniform(era.budget_hi, era.spectacle_hi), 2)
    lo, hi = era.budget_lo, era.budget_hi
    return round(math.exp(rng.uniform(math.log(lo), math.log(hi))), 2)


def _formats(rng, released: date, ptype: str) -> tuple[str, str, str]:
    y = released.year
    if released < date(1927, 10, 1):
        sound = "silent"
    elif y < 1930:
        sound = "silent" if rng.random() < 0.35 else "mono"
    elif y < 1958:
        sound = "mono"
    elif y < 1995:
        sound = "stereo" if rng.random() < min(0.9, 0.2 + (y - 1958) * 0.03) else "mono"
    else:
        sound = "digital"
    if y < 1935:
        color = "bw"
    elif y < 1955:
        color = "technicolor" if rng.random() < 0.05 + (y - 1935) * 0.02 else "bw"
    elif y < 1968:
        color = "technicolor" if rng.random() < 0.6 else "bw"
    else:
        color = "color" if rng.random() > 0.03 else "bw"
    if y < 1953 or ptype in ("tv_movie", "short", "serial"):
        aspect = "academy"
    else:
        aspect = rng.choices(["academy", "widescreen", "scope"],
                             weights=[max(0.05, 0.5 - (y - 1953) * 0.02), 0.35, 0.35])[0]
    return sound, color, aspect


def _base_rev_mult(rng, era: eras.Era, genre: str, released: date) -> float:
    window = _quarter(released)
    classic = date(released.year, 7, 1) < config.REGIME_FLIP
    seasonal = ({"Q1": 1.05, "Q2": 1.05, "Q3": 0.85, "Q4": 1.20} if classic
                else {"Q1": 0.85, "Q2": 1.20, "Q3": 1.10, "Q4": 1.10})[window]
    mult = 2.3 * config.GENRE_REV_MULT[genre] * seasonal * math.exp(rng.gauss(0.0, 0.55))
    return max(0.15, min(mult, 9.5))


class _Franchise:
    """A generated franchise: schedule of entry years plus its cycle economics."""

    def __init__(self, fid: str, name: str, cycle: str, genre: str, start_year: int, rng):
        shape = CYCLE_SHAPES[cycle]
        self.fid, self.name, self.cycle, self.genre = fid, name, cycle, genre
        self.entry1_mult: float | None = None
        self.entry1_budget: float | None = None
        self.month_home: int | None = None
        n = rng.randint(*shape["entries"])
        years, y = [], start_year
        for i in range(n):
            years.append(y)
            y += rng.randint(*shape["gap_years"])
        self.schedule = {yr: i + 1 for i, yr in enumerate(years) if yr <= config.HORIZON.year}
        self.emitted = 0

    def due(self, year: int) -> int | None:
        return self.schedule.get(year)


def build() -> tuple[list[dict], list[list]]:
    """Return (projects with latents, franchises table rows)."""
    plan = config.slate_plan()
    beats_by_key: dict[tuple[int, str], list[Beat]] = {}
    for b in beats_mod.BEATS:
        anchor = b.released or b.greenlit
        beats_by_key.setdefault((anchor.year, b.project_type), []).append(b)

    projects: list[dict] = []
    used_titles: set[str] = set(beats_mod.beat_titles())
    open_franchises: list[_Franchise] = []
    closed_franchises: list[_Franchise] = []
    gen_seq = 0

    def fresh_title(rng) -> str:
        for _ in range(200):
            a, b = rng.choice(config.TITLE_PARTS_A), rng.choice(config.TITLE_PARTS_B)
            pattern = rng.random()
            if pattern < 0.40:
                t = f"{a} {b}"
            elif pattern < 0.62:
                t = f"The {a} {b}"
            elif pattern < 0.82:
                t = f"{b} {rng.choice(config.TITLE_TAILS)}"
            else:
                t = f"The {b} {rng.choice(config.TITLE_TAILS)}"
            if t not in used_titles:
                used_titles.add(t)
                return t
        raise RuntimeError("title space exhausted — widen TITLE_PARTS")

    def add(year: int, ptype: str, *, rng, beat: Beat | None = None,
            franchise: _Franchise | None = None, entry: int = 0) -> dict:
        era = eras.era_for_year(year)
        if beat is not None:
            released = beat.released
            genre, budget, status = beat.genre, beat.budget, beat.status
            title = beat.title
            rev_mult = beat.rev_mult
            fid, fentry = beat.franchise_id, beat.entry
            shape = (CYCLE_SHAPES[next(f.cycle_type for f in beats_mod.FRANCHISES
                                       if f.franchise_id == fid)] if fid else None)
            opening = (shape["opening_boost"][min(fentry, len(shape["opening_boost"])) - 1]
                       if shape and fentry else 1.0)
            tail = (shape["tail_mult"] if shape and fentry and fentry > 1 else 1.0)
        else:
            genre = (franchise.genre if franchise
                     else rng.choices(list(era.genre_weights), weights=list(era.genre_weights.values()))[0])
            released = _release_date(rng, year)
            if franchise is not None and franchise.month_home and released.year >= 1975:
                released = date(released.year, franchise.month_home, rng.randint(1, 28))
            status = "released"
            shape = CYCLE_SHAPES[franchise.cycle] if franchise else None
            if franchise is None or entry == 1:
                budget = _budget(rng, era, ptype)
                rev_mult = _base_rev_mult(rng, era, genre, released)
            else:
                i = min(entry, len(shape["rev_curve"])) - 1
                budget = round((franchise.entry1_budget or _budget(rng, era, ptype))
                               * shape["budget_curve"][i] * rng.uniform(0.9, 1.1), 2)
                rev_mult = max(0.15, (franchise.entry1_mult or 2.3)
                               * shape["rev_curve"][i] * rng.uniform(0.85, 1.15))
            opening = shape["opening_boost"][min(entry, len(shape["opening_boost"])) - 1] \
                if shape and entry else 1.0
            tail = shape["tail_mult"] if shape and entry > 1 else 1.0
            if franchise is not None:
                title = (franchise.name if entry == 1 else
                         f"{franchise.name} {SEQUEL_SUFFIXES[franchise.cycle][min(entry - 2, len(SEQUEL_SUFFIXES[franchise.cycle]) - 1)]}"
                         if franchise.cycle == "numbered_sequel" else
                         f"{franchise.name}: {SEQUEL_SUFFIXES[franchise.cycle][min(entry - 2, len(SEQUEL_SUFFIXES[franchise.cycle]) - 1)]}")
                if title in used_titles:
                    title = f"{title} ({released.year})"
                used_titles.add(title)
            else:
                title = fresh_title(rng)
            fid = franchise.fid if franchise else ""
            fentry = entry

        gap = TYPE_GAP.get(ptype) or GREENLIGHT_GAP[era.era_id]
        if beat is not None and beat.greenlit is not None:
            greenlit = beat.greenlit
        else:
            anchor = released or date(year, 6, 15)
            greenlit = max(anchor - timedelta(days=rng.randint(*gap)), config.FOUNDED)
        if status == "released" and released is not None and released > config.HORIZON - timedelta(days=30):
            status, released = "in_production", None

        # the overrun latent belongs to the era the title is RECORDED in — a
        # title drawn in a boundary year must not carry the neighbor era's
        # discipline into its own era's bucket (that contamination flattened
        # the U-shape until this draw moved here)
        era_of_record = eras.era_for(released or greenlit)
        if beat is not None and beat.overrun is not None:
            overrun = beat.overrun
        else:
            overrun = max(-0.04, rng.gauss(era_of_record.overrun_mu, era_of_record.overrun_sd))
            # bigger productions run hotter in EVERY era — a cross-era truth the
            # era means modulate but never invert. Position within the era's own
            # budget band is what budget_class percentiles approximate.
            lo, hi = era_of_record.type_budget_factor.get(
                ptype, (era_of_record.budget_lo, era_of_record.spectacle_hi))
            if hi > lo:
                position = (math.log(max(budget, lo)) - math.log(lo)) / (math.log(hi) - math.log(lo))
                overrun += 0.055 * min(1.0, max(0.0, position))

        shoot_lo, shoot_hi = era.shoot_days
        planned = (beat.shoot_planned if beat is not None and beat.shoot_planned
                   else rng.randint(shoot_lo, shoot_hi))
        actual = (beat.shoot_actual if beat is not None and beat.shoot_actual
                  else max(int(planned * 0.95),
                           int(planned * (1 + max(0.0, overrun) * 0.8 + rng.gauss(0, 0.04)))))
        sound, color, aspect = _formats(rng, released or greenlit, ptype)
        if beat is not None:
            sound, color, aspect = (beat.sound_format or sound, beat.color_format or color,
                                    beat.aspect or aspect)
        division = {"feature": "features", "short": "shorts", "serial": "serials",
                    "tv_movie": "television", "streaming_original": "streaming"}[ptype]
        if ptype == "feature" and (released or greenlit).year >= 1991 and rng.random() < 0.18:
            division = "specialty"

        proj = {
            "project_id": "",                     # assigned chronologically at the end
            "title": title, "project_type": ptype, "division": division, "genre": genre,
            "era_id": era_of_record.era_id, "budget_class": "",
            "budget_usd": budget, "greenlit_at": greenlit, "released_at": released,
            "release_window": _quarter(released or greenlit),
            "is_sequel": 1 if fentry and fentry > 1 else 0,
            "franchise": (franchise.name if franchise else
                          next((f.name for f in beats_mod.FRANCHISES if f.franchise_id == fid), "")
                          if fid else ""),
            "franchise_id": fid, "entry_number": fentry,
            "sound_format": sound, "color_format": color, "aspect": aspect,
            "shoot_days_planned": planned, "shoot_days_actual": actual,
            "status": status,
            "_overrun": (beat.overrun if beat is not None and beat.overrun is not None else overrun),
            "_rev_mult": rev_mult, "_opening_boost": opening, "_tail_mult": tail,
            "_completion_base": config.GENRE_COMPLETION[genre] - (0.04 if fentry and fentry > 1 else 0.0),
        }
        projects.append(proj)
        if franchise is not None:
            if entry == 1:
                franchise.entry1_mult, franchise.entry1_budget = rev_mult, budget
                franchise.month_home = (released or greenlit).month
            franchise.emitted += 1
        return proj

    for year in sorted(plan):
        for ptype, n in plan[year].items():
            rng = stream = config.stream_rng("slate", ptype, year)
            slots = n
            for beat in beats_by_key.get((year, ptype), []):
                add(year, ptype, rng=stream, beat=beat)
                slots -= 1
            if ptype == "feature":
                # franchise entries due this year come before anything new
                for fr in list(open_franchises):
                    entry = fr.due(year)
                    if entry and entry > 1:
                        add(year, ptype, rng=stream, franchise=fr, entry=entry)
                        slots -= 1
                    if fr.schedule and max(fr.schedule) <= year:
                        open_franchises.remove(fr)
                        closed_franchises.append(fr)
                era = eras.era_for_year(year)
                start_p = {"serial": 0.01, "monster_cycle": 0.05, "b_franchise": 0.06,
                           "numbered_sequel": 0.09, "franchise_premium": 0.11,
                           "legacy_revival": 0.08}[era.sequel_mode]
                while slots > 0:
                    if rng.random() < start_p:
                        if (era.sequel_mode == "legacy_revival" and closed_franchises
                                and rng.random() < 0.5):
                            dormant = [f for f in closed_franchises
                                       if year - max(f.schedule) >= 15]
                            if dormant:
                                fr = rng.choice(dormant)
                                revival_entry = max(fr.schedule.values()) + 1
                                fr.cycle = "legacy_revival"
                                fr.schedule[year] = revival_entry
                                add(year, ptype, rng=stream, franchise=fr, entry=revival_entry)
                                slots -= 1
                                continue
                        gen_seq += 1
                        fr = _Franchise(f"fr-gen-{gen_seq:04d}", "", era.sequel_mode,
                                        rng.choices(list(era.genre_weights),
                                                    weights=list(era.genre_weights.values()))[0],
                                        year, rng)
                        fr.name = fresh_title(rng)
                        open_franchises.append(fr)
                        add(year, ptype, rng=stream, franchise=fr, entry=1)
                        slots -= 1
                    else:
                        add(year, ptype, rng=stream)
                        slots -= 1
            else:
                for _ in range(max(0, slots)):
                    add(year, ptype, rng=stream)

    # era-relative budget_class: percentile within a rolling decade of same-type budgets
    by_type: dict[str, list[dict]] = {}
    for p in projects:
        by_type.setdefault(p["project_type"], []).append(p)
    for ptype, group in by_type.items():
        for p in group:
            y = (p["released_at"] or p["greenlit_at"]).year
            window = [q["budget_usd"] for q in group
                      if abs((q["released_at"] or q["greenlit_at"]).year - y) <= 5]
            rank = sum(1 for b in window if b <= p["budget_usd"]) / max(1, len(window))
            p["budget_class"] = "indie" if rank < 0.40 else ("mid" if rank < 0.85 else "tentpole")

    # chronological ids by greenlight
    projects.sort(key=lambda p: (p["greenlit_at"], p["title"]))
    for i, p in enumerate(projects, start=1):
        p["project_id"] = f"prj-{i:05d}"

    # franchises table: pinned defs + generated
    franchise_rows: list[list] = []
    pinned_entries: dict[str, list[Beat]] = {}
    for b in beats_mod.BEATS:
        if b.franchise_id:
            pinned_entries.setdefault(b.franchise_id, []).append(b)
    for fdef in beats_mod.FRANCHISES:
        entries = pinned_entries.get(fdef.franchise_id, [])
        years = [e.released.year for e in entries if e.released]
        ended = max(years) if years and max(years) < 2015 else None
        franchise_rows.append([fdef.franchise_id, fdef.name, fdef.cycle_type,
                               min(years) if years else 0, ended, len(entries), fdef.notes])
    for fr in open_franchises + closed_franchises:
        if not fr.emitted:
            continue
        years = sorted(fr.schedule)
        ended = max(years) if fr in closed_franchises and max(years) < 2015 else None
        franchise_rows.append([fr.fid, fr.name, fr.cycle, min(years), ended, fr.emitted, ""])

    return projects, franchise_rows


PROJECT_COLUMNS = ["project_id", "title", "project_type", "division", "genre", "era_id",
                   "budget_class", "budget_usd", "greenlit_at", "released_at",
                   "release_window", "is_sequel", "franchise", "franchise_id",
                   "entry_number", "sound_format", "color_format", "aspect",
                   "shoot_days_planned", "shoot_days_actual", "status"]


def project_rows(projects: list[dict]) -> list[list]:
    return [[p[c] for c in PROJECT_COLUMNS] for p in projects]
