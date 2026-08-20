"""Full investigation loop, hermetic (mock cognition + recorded fixtures):
question → plan → SQL evidence → rule-derived findings → interpretations →
simulation → recommendation → decision → promotion path."""
import os

os.environ["GENESIS_MOCK"] = "1"

import pytest

from app.config import Settings
from app.models.institutional import Investigation, InvestigationStatus, VerificationState


@pytest.fixture()
def runtime(tmp_path):
    import app.workflows.runtime as rt_mod

    settings = Settings(data_dir=tmp_path, force_mock=True)
    rt = rt_mod.InstitutionalRuntime(settings)
    rt_mod._runtime = rt
    yield rt
    rt_mod._runtime = None


QUESTION = "Should we greenlight 'Nebula Frontier 2' at $45M for a Q2 release?"


def _run(rt) -> Investigation:
    from app.workflows.run_investigation import run_investigation

    inv = Investigation(question=QUESTION)
    rt.working.put(inv)
    run_investigation(inv.id)
    return rt.working.get(inv.id)


def test_loop_reaches_recommendation(runtime):
    inv = _run(runtime)
    assert inv.status == InvestigationStatus.RECOMMENDED
    assert inv.hypotheses and inv.queries and inv.findings
    assert inv.recommendation is not None
    assert 0.2 <= inv.recommendation.confidence <= 0.95


def test_every_query_is_auditable_evidence(runtime):
    inv = _run(runtime)
    for query in inv.queries:
        assert query.sql.upper().startswith(("SELECT", "WITH"))
        assert query.error is None
        assert query.row_count > 0


def test_contested_finding_preserved_with_two_stances(runtime):
    inv = _run(runtime)
    states = {f.state for f in inv.findings}
    assert VerificationState.CONTESTED in states
    contested = next(f for f in inv.findings if f.state == VerificationState.CONTESTED)
    citing = [i for i in inv.interpretations if contested.id in i.cited_finding_ids]
    assert len({i.stance for i in citing}) >= 2, "both readings must reach the Studio Head"


def test_confidence_is_computed_from_coverage(runtime):
    inv = _run(runtime)
    cov = inv.recommendation.coverage
    total = sum(cov.values())
    expected = 0.30 + 0.60 * cov["VERIFIED"] / total + 0.40 * cov["REGIME"] / total \
        + 0.10 * cov["WEAK"] / total - 0.05 * cov["INSUFFICIENT"] / total
    assert abs(inv.recommendation.confidence - round(min(0.95, max(0.20, expected)), 2)) < 1e-9


def test_simulation_is_seeded_and_reproducible(runtime):
    inv = _run(runtime)
    assert inv.simulation is not None
    assert inv.simulation.seed == 7 and inv.simulation.n_runs == 2000
    assert inv.simulation.delta["p50"] == inv.simulation.projected["p50"] - inv.simulation.baseline["p50"]


def test_approval_promotes_and_completes(runtime):
    from app.workflows.run_investigation import run_decision

    inv = _run(runtime)
    run_decision(inv.id, "approved", "")
    final = runtime.working.get(inv.id)
    assert final.status == InvestigationStatus.PROMOTED
    events = {e["event"] for e in runtime.bus.tail(200)}
    assert {"investigation.started", "analysis.executed", "recommendation.created",
            "authorization.decided", "investigation.completed"} <= events


def test_deeper_analysis_loops_back_with_guidance(runtime):
    from app.workflows.run_investigation import run_decision

    inv = _run(runtime)
    run_decision(inv.id, "deeper", "focus on sequel completion rates")
    final = runtime.working.get(inv.id)
    assert final.round == 2
    assert "focus on sequel completion rates" in final.deeper_guidance
    assert final.status == InvestigationStatus.RECOMMENDED  # second round completed


def test_latch_released_after_completion(runtime):
    from app.memory.ephemeral import INVESTIGATION_LATCH, LATCH_TTL_S
    from app.workflows.run_investigation import run_decision

    inv = _run(runtime)
    run_decision(inv.id, "rejected", "not now")
    assert runtime.ephemeral.acquire_latch(INVESTIGATION_LATCH, "probe", LATCH_TTL_S) is None
    runtime.ephemeral.release_latch(INVESTIGATION_LATCH)


def test_century_state_mix_on_the_canonical_run(runtime):
    """The recalibrated rules must produce the full vocabulary on the mock
    investigation: institutional truth (VERIFIED, cross-era), an era-bounded
    REGIME carrying its range, and the preserved CONTESTED pair."""
    inv = _run(runtime)
    states = {f.state for f in inv.findings}
    assert VerificationState.VERIFIED in states
    assert VerificationState.REGIME in states
    assert VerificationState.CONTESTED in states
    regime = next(f for f in inv.findings if f.state == VerificationState.REGIME)
    assert regime.era_range, "a REGIME finding must carry its era range"
    verified = [f for f in inv.findings if f.state == VerificationState.VERIFIED]
    assert any(f.stats.get("n_eras_agree", 0) >= 3 for f in verified), \
        "at least one VERIFIED finding must rest on 3+ agreeing eras"
