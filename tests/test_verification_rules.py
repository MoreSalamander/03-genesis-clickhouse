"""Verification states are rule-derived in code, never model-asserted (locked §2.3)."""
from app.config import VerificationPolicy
from app.agents.verification.statistical import StatisticalVerifier
from app.models.institutional import AnalyticalQuery, Hypothesis, VerificationState

POLICY = VerificationPolicy()
SPEC = {"metric_col": "metric", "group_col": "grp", "n_col": "n", "std_col": "std",
        "split_col": None}


def _query(rows, purpose="q", columns=None):
    q = AnalyticalQuery(hypothesis_id="h", domain="d", purpose=purpose,
                        sql="SELECT 1", columns=columns or ["grp", "metric", "n", "std"],
                        rows=rows, row_count=len(rows))
    return q


def _verify(queries):
    verifier = StatisticalVerifier(POLICY)
    hyp = Hypothesis(domain="financial_performance", statement="test hypothesis")
    for q in queries:
        q.hypothesis_id = hyp.id
    rows_of = {q.id: q.rows for q in queries}
    specs = {q.id: SPEC for q in queries}
    return verifier.verify_hypothesis(hyp, queries, rows_of, specs)


def test_verified_when_powered_and_clear_effect():
    rows = [["a", 1.10, 500, 0.05], ["b", 1.02, 400, 0.05]]
    finding = _verify([_query(rows)])
    assert finding.state == VerificationState.VERIFIED
    assert finding.stats["effect_over_noise"] > 1.0


def test_weak_when_underpowered():
    rows = [["a", 1.10, 8, 0.05], ["b", 1.02, 9, 0.05]]
    finding = _verify([_query(rows)])
    assert finding.state == VerificationState.WEAK
    assert "n_min" in finding.basis


def test_weak_when_effect_within_noise():
    rows = [["a", 1.001, 500, 0.9], ["b", 1.0, 400, 0.9]]
    finding = _verify([_query(rows)])
    assert finding.state == VerificationState.WEAK


def test_contested_when_directions_disagree():
    up = _query([["a", 2.0, 100, 0.1], ["b", 1.0, 100, 0.1]], purpose="slice-one")
    down = _query([["a", 1.0, 100, 0.1], ["b", 2.0, 100, 0.1]], purpose="slice-two")
    finding = _verify([up, down])
    assert finding.state == VerificationState.CONTESTED
    assert "preserved" in finding.basis


def test_insufficient_on_empty_results():
    finding = _verify([_query([])])
    assert finding.state == VerificationState.INSUFFICIENT


def test_insufficient_on_errored_query():
    q = _query([["a", 1.0, 10, 0.1]])
    q.error = "boom"
    finding = _verify([q])
    assert finding.state == VerificationState.INSUFFICIENT
