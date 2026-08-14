"""Temporal workflow — the locked analytical loop as durable execution.

Deterministic orchestration only (activities are referenced by name). The
Studio Head's authorization is a workflow SIGNAL, and *request deeper analysis*
is a first-class decision (locked §2.6/§2.9): a "deeper" signal loops the
workflow back to planning with the Studio Head's guidance, bounded by the
executive's round budget — all of it durable across worker crashes.
"""
from __future__ import annotations

from datetime import timedelta

from temporalio import workflow
from temporalio.common import RetryPolicy
from temporalio.exceptions import ActivityError

_RETRY = RetryPolicy(initial_interval=timedelta(seconds=3), maximum_attempts=3)
_OPTS = {"start_to_close_timeout": timedelta(minutes=4), "retry_policy": _RETRY}
_ANALYZE_OPTS = {"start_to_close_timeout": timedelta(minutes=10), "retry_policy": _RETRY}
DECISION_WINDOW = timedelta(hours=24)
MAX_ROUNDS = 3


@workflow.defn(name="InstitutionalInvestigationWorkflow")
class InstitutionalInvestigationWorkflow:
    def __init__(self) -> None:
        self._decision: str | None = None
        self._note: str = ""

    @workflow.signal(name="studio_head_decision")
    def studio_head_decision(self, decision: str, note: str = "") -> None:
        if self._decision is None and decision in ("approved", "rejected", "deeper"):
            self._decision = decision
            self._note = note

    @workflow.query(name="decision")
    def decision(self) -> str | None:
        return self._decision

    @workflow.run
    async def run(self, inv_id: str) -> str:
        for _round in range(MAX_ROUNDS):
            try:
                await workflow.execute_activity("inst.plan", inv_id, **_OPTS)
                await workflow.execute_activity("inst.analyze", inv_id, **_ANALYZE_OPTS)
                await workflow.execute_activity("inst.verify", inv_id, **_OPTS)
                await workflow.execute_activity("inst.simulate", inv_id, **_ANALYZE_OPTS)
                await workflow.execute_activity("inst.recommend", inv_id, **_OPTS)
            except ActivityError as err:
                # exhausted retries → honest INCOMPLETE; numbers are never fabricated
                return await workflow.execute_activity(
                    "inst.incomplete",
                    args=[inv_id, f"Durable stage failed after retries: {err.__cause__ or err}"],
                    **_OPTS,
                )

            # Human boundary: durable pause until the Studio Head decides.
            self._decision, self._note = None, ""
            try:
                await workflow.wait_condition(lambda: self._decision is not None,
                                              timeout=DECISION_WINDOW)
            except TimeoutError:
                return await workflow.execute_activity("inst.escalate_timeout", inv_id, **_OPTS)

            outcome = await workflow.execute_activity(
                "inst.decide", args=[inv_id, self._decision, self._note], **_OPTS)
            if outcome != "DEEPER":
                return outcome
            # deeper analysis requested → loop back to planning with guidance
        return await workflow.execute_activity(
            "inst.incomplete", args=[inv_id, "deeper-analysis round budget exhausted"], **_OPTS)
