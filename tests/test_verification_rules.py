"""The recalibrated verification rules, case by case (century-corpus edition).

Every case encodes one rule the Studio Head can be told in a sentence:
VERIFIED needs power on the compared unit, a scale-free effect, and agreement
across at least three eras; REGIME is a truth with a boundary; WEAK is a signal
that couldn't prove one of those; CONTESTED is a preserved disagreement;
INSUFFICIENT is the corpus saying "I can't answer that".
"""
from app.agents.verification.statistical import StatisticalVerifier
from app.config import VerificationPolicy
from app.models.institutional import AnalyticalQuery, Hypothesis, VerificationState

POLICY = VerificationPolicy()
SPEC = {"metric_col": "metric", "group_col": "grp", "n_col": "n_titles",
        "std_col": "std", "split_col": "era"}


def _query(rows, purpose="q", columns=None):
    return AnalyticalQuery(hypothesis_id="h", domain="d", purpose=purpose,
                           sql="SELECT 1",
                           columns=columns or ["grp", "metric", "n_titles", "std", "era"],
                           rows=rows, row_count=len(rows))


def _verify(queries, spec=SPEC):
    verifier = StatisticalVerifier(POLICY)
    hyp = Hypothesis(domain="d", statement="s")
    return verifier.verify_hypothesis(
        hyp, queries, {q.id: q.rows for q in queries}, {q.id: dict(spec) for q in queries})


def _era_rows(eras, a=1.10, b=1.02, n=60, flip=()):
    rows = []
    for era in eras:
        hi, lo = (b, a) if era in flip else (a, b)
        rows.append(["tentpole", hi, n, 0.05, era])
        rows.append(["indie", lo, n, 0.05, era])
    return rows


def test_verified_needs_power_signal_and_three_agreeing_eras():
    finding = _verify([_query(_era_rows(["silent", "golden_age", "dvd_peak", "streaming"]))])
    assert finding.state == VerificationState.VERIFIED
    assert "institutional truth" in finding.basis
    assert finding.stats["n_eras_agree"] == 4.0
    assert finding.stats["effect_over_noise"] > POLICY.effect_over_noise
    assert finding.stats["threshold"] == POLICY.effect_over_noise


def test_regime_when_an_era_disagrees():
    finding = _verify([_query(_era_rows(
        ["silent", "golden_age", "dvd_peak", "streaming"], flip=("silent",)))])
    assert finding.state == VerificationState.REGIME
    assert finding.era_range and "silent" not in finding.era_range
    assert "true within" in finding.basis


def test_regime_when_data_spans_too_few_eras():
    # a streaming-era question IS era-bounded: 2 agreeing eras < min_stable_eras
    finding = _verify([_query(_era_rows(["streaming_transition", "streaming_wars_covid"]))])
    assert finding.state == VerificationState.REGIME
    assert finding.era_range == "streaming_transition → streaming_wars_covid"
    assert "spans only 2 era(s)" in finding.basis


def test_weak_when_no_era_split_in_result():
    rows = [["a", 1.10, 500, 0.05], ["b", 1.02, 400, 0.05]]
    finding = _verify([_query(rows, columns=["grp", "metric", "n_titles", "std"])],
                      spec={"metric_col": "metric", "group_col": "grp",
                            "n_col": "n_titles", "std_col": "std", "split_col": None})
    assert finding.state == VerificationState.WEAK
    assert "era stability unproven" in finding.basis


def test_weak_when_underpowered_on_titles():
    finding = _verify([_query(_era_rows(["golden_age", "dvd_peak", "streaming"], n=8))])
    assert finding.state == VerificationState.WEAK
    assert "titles_min" in finding.basis


def test_weak_when_effect_within_dispersion():
    finding = _verify([_query(_era_rows(["golden_age", "dvd_peak", "streaming"],
                                        a=1.001, b=1.0))])
    # |0.001| / 0.05 = 0.02 << 0.35 — n cannot buy this back
    assert finding.state == VerificationState.WEAK
    assert "effect size" in finding.basis


def test_row_grain_power_fallback_is_annotated():
    # no titles column: power falls back to row-grain n, annotated — the
    # scale-free effect and the era gate still hold the line
    rows = []
    for era in ("golden_age", "dvd_peak", "streaming"):
        rows.append(["a", 1.10, 100000, 0.05, era])
        rows.append(["b", 1.02, 90000, 0.05, era])
    finding = _verify([_query(rows, columns=["grp", "metric", "n", "std", "era"])],
                      spec={"metric_col": "metric", "group_col": "grp",
                            "n_col": "n", "std_col": "std", "split_col": "era"})
    assert finding.state == VerificationState.VERIFIED
    assert "power unit approximate" in finding.basis


def test_contested_when_directions_disagree():
    up = _query(_era_rows(["golden_age", "dvd_peak", "streaming"], a=2.0, b=1.0),
                purpose="slice-one")
    down = _query(_era_rows(["golden_age", "dvd_peak", "streaming"], a=1.0, b=2.0),
                  purpose="slice-two")
    finding = _verify([up, down])
    assert finding.state == VerificationState.CONTESTED
    assert "preserved" in finding.basis


def test_insufficient_on_empty_results():
    assert _verify([_query([])]).state == VerificationState.INSUFFICIENT


def test_insufficient_on_errored_query():
    q = _query(_era_rows(["golden_age"]))
    q.error = "boom"
    assert _verify([q]).state == VerificationState.INSUFFICIENT


def test_effect_size_is_scale_free():
    """The recalibration's core promise: multiplying n by 1000 must not move
    effect_over_noise — only a larger or tighter effect can."""
    small = _verify([_query(_era_rows(["golden_age", "dvd_peak", "streaming"], n=60))])
    huge = _verify([_query(_era_rows(["golden_age", "dvd_peak", "streaming"], n=60000))])
    assert small.stats["effect_over_noise"] == huge.stats["effect_over_noise"]
