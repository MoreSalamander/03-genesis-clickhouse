"""Investigation dispatch: Temporal durable execution by default, with a
surfaced in-process fallback so a clean clone (no Docker, no keys) still runs
the entire loop in mock mode."""
from __future__ import annotations

from app.config import settings
from app import runtime_proof
from app.workflows.runtime import get_runtime


def run_investigation(inv_id: str) -> None:
    """In-process execution of the full pre-decision loop."""
    executive = get_runtime().executive
    try:
        executive.plan(inv_id)
        executive.analyze(inv_id)
        executive.verify(inv_id)
        executive.simulate(inv_id)
        executive.recommend(inv_id)
    except Exception as err:
        executive.incomplete(inv_id, f"in-process stage failed: {err}")


def run_decision(inv_id: str, decision: str, note: str) -> None:
    executive = get_runtime().executive
    try:
        outcome = executive.decide(inv_id, decision, note)
        if outcome == "DEEPER":
            run_investigation(inv_id)  # next round, same guidance-carrying document
    except Exception as err:
        executive.incomplete(inv_id, f"decision handling failed: {err}")


# ---------------------------------------------------------------------------
# Temporal dispatch (durable execution — preserved-stack responsibility).
# ---------------------------------------------------------------------------

def _workflow_id(inv_id: str) -> str:
    return f"inst-wf-{inv_id}"


def dispatch_investigation(inv_id: str) -> str:
    """Returns 'temporal' when the durable workflow started, else 'local'."""
    if settings.force_mock:
        runtime_proof.record("temporal", "MOCK",
                             "GENESIS_MOCK set — in-process execution by design")
        return "local"
    if not settings.temporal_address:
        # Not part of this deployment (e.g. Cloud Run). Attempting a dial would
        # report DEGRADED, which reads as a fault rather than an absent
        # substrate — so say what is actually true and run in-process.
        runtime_proof.record("temporal", "MOCK",
                             "no TEMPORAL_ADDRESS — in-process execution for this deployment")
        return "local"
    try:
        import asyncio

        from temporalio.client import Client

        async def go():
            client = await Client.connect(settings.temporal_address)
            await client.start_workflow(
                "InstitutionalInvestigationWorkflow", inv_id,
                id=_workflow_id(inv_id), task_queue=settings.temporal_task_queue,
            )

        asyncio.run(go())
        runtime_proof.record("temporal", "LIVE",
                             f"durable workflow accepted at {settings.temporal_address}")
        return "temporal"
    except Exception as err:
        print(f"[workflow] Temporal dispatch failed ({err}) — DEGRADED: in-process execution")
        runtime_proof.record("temporal", "DEGRADED",
                             f"dispatch failed ({err}) — ran in-process instead")
        return "local"


def dispatch_decision(inv_id: str, decision: str, note: str) -> str:
    """Signals the durable workflow's human boundary; 'local' on fallback."""
    if settings.force_mock:
        runtime_proof.record("temporal", "MOCK",
                             "GENESIS_MOCK set — in-process execution by design")
        return "local"
    if not settings.temporal_address:
        # Not part of this deployment (e.g. Cloud Run). Attempting a dial would
        # report DEGRADED, which reads as a fault rather than an absent
        # substrate — so say what is actually true and run in-process.
        runtime_proof.record("temporal", "MOCK",
                             "no TEMPORAL_ADDRESS — in-process execution for this deployment")
        return "local"
    try:
        import asyncio

        from temporalio.client import Client

        async def go():
            client = await Client.connect(settings.temporal_address)
            handle = client.get_workflow_handle(_workflow_id(inv_id))
            await handle.signal("studio_head_decision", args=[decision, note])

        asyncio.run(go())
        runtime_proof.record("temporal", "LIVE",
                             f"durable workflow accepted at {settings.temporal_address}")
        return "temporal"
    except Exception as err:
        print(f"[workflow] Temporal signal failed ({err}) — DEGRADED: in-process execution")
        runtime_proof.record("temporal", "DEGRADED",
                             f"signal failed ({err}) — handled in-process instead")
        return "local"
