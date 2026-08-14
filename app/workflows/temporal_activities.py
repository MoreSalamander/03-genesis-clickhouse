"""Temporal activities — each locked loop stage as a durable, retryable unit.

Every activity loads the investigation from PostgreSQL, runs exactly one stage
through the executive, and checkpoints back — a crashed worker resumes from the
last completed stage, never from scratch.
"""
from __future__ import annotations

from temporalio import activity


def _executive():
    from app.workflows.runtime import get_runtime

    return get_runtime().executive


@activity.defn(name="inst.plan")
def plan_activity(inv_id: str) -> str:
    return _executive().plan(inv_id)


@activity.defn(name="inst.analyze")
def analyze_activity(inv_id: str) -> str:
    return _executive().analyze(inv_id)


@activity.defn(name="inst.verify")
def verify_activity(inv_id: str) -> str:
    return _executive().verify(inv_id)


@activity.defn(name="inst.simulate")
def simulate_activity(inv_id: str) -> str:
    return _executive().simulate(inv_id)


@activity.defn(name="inst.recommend")
def recommend_activity(inv_id: str) -> str:
    return _executive().recommend(inv_id)


@activity.defn(name="inst.decide")
def decide_activity(inv_id: str, decision: str, note: str) -> str:
    return _executive().decide(inv_id, decision, note)


@activity.defn(name="inst.incomplete")
def incomplete_activity(inv_id: str, reason: str) -> str:
    return _executive().incomplete(inv_id, reason)


@activity.defn(name="inst.escalate_timeout")
def escalate_timeout_activity(inv_id: str) -> str:
    from app.workflows.runtime import get_runtime

    rt = get_runtime()
    inv = rt.working.get(inv_id)
    if inv is None:
        return "UNKNOWN"
    inv.escalated = True
    inv.touch()
    rt.working.put(inv)
    rt.bus.emit("authorization.decided", investigation_id=inv.id,
                decision="escalated_timeout",
                note="decision window elapsed without a Studio Head decision")
    from app.memory.ephemeral import INVESTIGATION_LATCH

    rt.ephemeral.release_latch(INVESTIGATION_LATCH)
    return inv.status.value


ALL_ACTIVITIES = [plan_activity, analyze_activity, verify_activity, simulate_activity,
                  recommend_activity, decide_activity, incomplete_activity,
                  escalate_timeout_activity]
