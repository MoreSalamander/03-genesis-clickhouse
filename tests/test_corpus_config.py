"""The century-corpus config layer, provable without any infrastructure.

These assertions are the contract the fact expansions build on: contiguous
eras, a complete deflator, a slate that lands in the approved band, shocks
inside the corpus, and beat/cycle machinery that encodes the engineered truths
(the monster fatigue curve, the factory-era overrun minimum, the modern
contested pair). If one of these fails, nothing downstream is worth seeding.
"""
from datetime import date, timedelta

from seed import beats, config, cpi, eras, shocks


def test_eras_are_contiguous_and_span_the_corpus():
    assert len(eras.ERAS) == 10
    assert eras.ERAS[0].start == date(1912, 6, 8)
    assert eras.ERAS[-1].end == config.HORIZON
    for prev, nxt in zip(eras.ERAS, eras.ERAS[1:]):
        assert nxt.start == prev.end + timedelta(days=1), (prev.name, nxt.name)
    # the blockbuster era begins the day the summer was invented
    assert eras.era_for(date(1975, 6, 20)).name == "blockbuster"
    assert eras.era_for(date(1975, 6, 19)).name == "conglomerate"


def test_overrun_profile_is_the_u_shape():
    by_name = {e.name: e for e in eras.ERAS}
    golden = by_name["golden_age"].overrun_mu
    assert golden == min(e.overrun_mu for e in eras.ERAS), "factory era must be the minimum"
    assert by_name["conglomerate"].overrun_mu >= golden + 0.06
    assert by_name["streaming_wars_covid"].overrun_mu >= golden + 0.06


def test_era_parameter_hygiene():
    for era in eras.ERAS:
        assert set(era.genre_weights) <= set(config.GENRES), era.name
        assert sum(era.genre_weights.values()) > 0, era.name
        assert abs(sum(era.cost_shares.values()) - 1.0) < 0.02, era.name
        assert set(era.cost_shares) <= set(config.CENTER_OVERRUN_WEIGHT), era.name
        assert era.budget_lo < era.budget_hi < era.spectacle_hi, era.name
        assert era.shoot_days[0] < era.shoot_days[1], era.name
        assert era.sequel_mode in beats.CYCLE_SHAPES, era.name
    # noir is a 40s–50s creature; westerns are dead weight by the streaming era
    assert eras.era_for_year(1940).genre_weights["noir"] >= 6
    assert eras.era_for_year(2015).genre_weights["western"] <= 1
    # studio overhead is a studio-system line, P&A a modern one
    assert "studio_overhead" in eras.era_for_year(1940).cost_shares
    assert "p_and_a" in eras.era_for_year(2010).cost_shares
    assert "covid_protocols" in eras.era_for_year(2022).cost_shares


def test_cpi_covers_every_year_and_lands_near_33x():
    for year in range(config.START_YEAR, config.HORIZON.year + 1):
        assert year in cpi.CPI, year
    assert 30.0 <= cpi.mult_to_2026(1912) <= 38.0
    assert cpi.mult_to_2026(2026) == 1.0
    # deflations are real (1921, the Depression, 1949, 2009) but never violent
    years = sorted(cpi.CPI)
    for a, b in zip(years, years[1:]):
        change = cpi.CPI[b] / cpi.CPI[a]
        assert 0.75 <= change <= 1.25, (a, b, change)


def test_slate_plan_is_deterministic_and_in_the_approved_band():
    total = config.slate_total()
    assert total == config.slate_total(), "slate_plan must be deterministic"
    assert 4_500 <= total <= 5_500, total
    plan = config.slate_plan()
    by_type: dict[str, int] = {}
    for counts in plan.values():
        for ptype, n in counts.items():
            by_type[ptype] = by_type.get(ptype, 0) + n
    assert 2_900 <= by_type["feature"] <= 3_600, by_type
    assert 600 <= by_type["short"] <= 900, by_type
    assert 60 <= by_type["serial"] <= 100, by_type
    assert 240 <= by_type["tv_movie"] <= 360, by_type
    assert 80 <= by_type["streaming_original"] <= 140, by_type
    # era gates: no tv movies before 1964, no streaming originals before 2015
    assert all("tv_movie" not in plan[y] for y in range(1912, 1964))
    assert all("streaming_original" not in plan[y] for y in range(1912, 2015))
    # the output collapse is visible: the golden-age era out-produces the modern one ~3×
    golden = sum(plan[y]["feature"] for y in range(1934, 1949)) / 15
    modern = sum(plan[y]["feature"] for y in range(2006, 2020)) / 14
    assert golden >= 2.5 * modern, (golden, modern)


def test_shock_calendar_is_inside_the_corpus_and_bites():
    for s in shocks.SHOCKS:
        assert config.FOUNDED <= s.start <= s.end <= config.HORIZON, s.shock_id
    assert shocks.halted(date(2023, 8, 1)), "the 2023 double strike halts production"
    assert shocks.halted(date(2020, 5, 1)), "COVID halts production"
    assert not shocks.halted(date(2019, 5, 1))
    assert shocks.attendance_mult(date(2020, 6, 1)) <= 0.2, "the COVID cliff"
    assert shocks.attendance_mult(date(1944, 6, 1)) > 1.0, "the wartime boom"
    assert shocks.cost_mult(date(1943, 6, 1)) < 1.0, "wartime set-cost caps"


def test_beats_are_unique_titled_and_era_placed():
    titles = [b.title for b in beats.BEATS]
    assert len(titles) == len(set(titles)), "beat titles must be unique"
    for b in beats.BEATS:
        anchor = b.released or b.greenlit
        assert anchor is not None, b.title
        eras.era_for(anchor)  # raises if outside the corpus
        assert b.project_type in config.TYPE_BANDS, b.title
        assert b.genre in config.GENRES, b.title


def test_monster_cycle_encodes_the_complete_fatigue_curve():
    cycle = sorted((b for b in beats.BEATS if b.franchise_id == "fr-monsters"),
                   key=lambda b: b.entry)
    assert len(cycle) == 7
    mults = [b.rev_mult for b in cycle]
    assert mults[1] > mults[0] and mults[2] > mults[0], "early sequels outgross the original"
    assert mults[3] < mults[2] and mults[4] < mults[3] and mults[5] < mults[4], "late entries decay"
    assert mults[6] == min(mults), "the parody is the floor"
    assert cycle[-1].released.year == 1948, "the parody closes the cycle in 1948"


def test_leviathan_is_pinned_exactly():
    lev = next(b for b in beats.BEATS if b.title == "Leviathan")
    assert lev.released == date(1975, 6, 20) == config.REGIME_FLIP
    assert lev.shoot_planned == 55 and lev.shoot_actual == 159
    assert lev.budget == 4_000_000 and abs(lev.overrun - 1.25) < 1e-9
    assert round(lev.budget * (1 + lev.overrun) / 1e6, 1) == 9.0, "the $4M→$9M overrun"


def test_modern_cycle_shapes_keep_the_contested_pair_contested():
    for mode in ("franchise_premium", "legacy_revival"):
        shape = beats.CYCLE_SHAPES[mode]
        assert all(b > 1.0 for b in shape["opening_boost"][1:]), \
            f"{mode}: sequels must OPEN bigger (the premium reading)"
    assert beats.CYCLE_SHAPES["legacy_revival"]["tail_mult"] < 1.0, \
        "revival tails must die faster (the fatigue reading)"
    assert beats.CYCLE_SHAPES["numbered_sequel"]["tail_mult"] < 1.0
    # curves must cover the largest entry count their cycle can generate
    for name, shape in beats.CYCLE_SHAPES.items():
        _, hi = shape["entries"]
        assert len(shape["rev_curve"]) >= hi, name
        assert len(shape["opening_boost"]) >= hi, name
        assert len(shape["budget_curve"]) >= hi, name


def test_pinned_franchises_resolve():
    ids = {f.franchise_id for f in beats.FRANCHISES}
    for b in beats.BEATS:
        if b.franchise_id:
            assert b.franchise_id in ids, b.title
    for f in beats.FRANCHISES:
        assert f.cycle_type in beats.CYCLE_SHAPES, f.franchise_id
