"""HTTP interface for the analytical workbench (frontend/) and the eventual
Genesis OS Institutional Intelligence Contract adapter. The standalone owns
this API; the federation consumes it — never the reverse.
"""
from __future__ import annotations

from fastapi import APIRouter, BackgroundTasks, HTTPException
from pydantic import BaseModel, Field

from app.models.institutional import Investigation, InvestigationStatus
from app.workflows.run_investigation import (
    dispatch_decision,
    dispatch_investigation,
    run_decision,
    run_investigation,
)
from app.workflows.runtime import get_runtime
from app import runtime_proof

router = APIRouter(prefix="/api")

VALID_DECISIONS = {"approved", "rejected", "deeper"}


class InvestigationRequest(BaseModel):
    question: str = Field(min_length=5, max_length=400,
                          default="Should we greenlight 'Nebula Frontier 2' at $45M for a Q2 release?")


class DecisionRequest(BaseModel):
    decision: str
    note: str = Field(default="", max_length=500)


def _summary(inv: Investigation) -> dict:
    return {
        "id": inv.id,
        "question": inv.question,
        "status": inv.status.value,
        "round": inv.round,
        "queries": len(inv.queries),
        "coverage": inv.coverage(),
        "confidence": inv.recommendation.confidence if inv.recommendation else None,
        "action": inv.recommendation.action if inv.recommendation else None,
        "escalated": inv.escalated,
        "created_at": inv.created_at,
        "updated_at": inv.updated_at,
    }


@router.get("/status")
def status() -> dict:
    runtime = get_runtime()
    return {
        "system": "Genesis OS — Institutional Intelligence",
        "banner": runtime.settings.banner(),
        "clickhouse_live": runtime.settings.clickhouse_live,
        "gemini_live": runtime.settings.gemini_live,
        "investigations": len(runtime.working.all()),
        "runtime_proof": _runtime_proof(runtime.settings),
    }


def _runtime_proof(settings) -> dict:
    """Substrate states for the console's runtime-proof footer.

    These are configuration-derived starting points; app.runtime_proof
    overrides any of them the moment the substrate is actually exercised, so a
    chip only reads LIVE on evidence.
    """
    return runtime_proof.snapshot({
        "gemini": (("LIVE", f"credential present — narration via {settings.gemini_model}")
                   if settings.gemini_live
                   else ("MOCK", "no GOOGLE_API_KEY — deterministic mock narration")),
        # As with Grafana in 02: clickhouse_live only asserts a URL string is
        # set. Only a returned MCP call (recorded in the client) upgrades this
        # to LIVE, so a deployment pointed at an unreachable MCP endpoint cannot
        # advertise the partner integration it is judged on.
        "clickhouse": (("IDLE", f"MCP configured at {settings.clickhouse_mcp_url} — no query run yet")
                       if settings.clickhouse_live
                       else ("MOCK", "no ClickHouse MCP URL — seeded fixture corpus")),
        # An unset address means Temporal is not part of this deployment, not
        # that it broke — dialling it would report DEGRADED and read as a fault.
        "temporal": (("IDLE", f"configured at {settings.temporal_address} — "
                              "no workflow dispatched yet this session")
                     if settings.temporal_address
                     else ("MOCK", "no TEMPORAL_ADDRESS — in-process execution for this deployment")),
        "datahub": ("IDLE", f"configured at {settings.datahub_gms_url} — nothing promoted yet"),
    })


@router.get("/corpus")
def corpus() -> dict:
    """Corpus overview for the console's context strip."""
    runtime = get_runtime()
    try:
        totals = runtime.clickhouse.run_query(
            "SELECT 'projects' AS t, count() AS n FROM genesis_institutional.projects "
            "UNION ALL SELECT 'audience_performance', count() FROM genesis_institutional.audience_performance "
            "UNION ALL SELECT 'production_events', count() FROM genesis_institutional.production_events "
            "UNION ALL SELECT 'financial_ledger', count() FROM genesis_institutional.financial_ledger "
            "UNION ALL SELECT 'ops_events', count() FROM genesis_institutional.ops_events"
        )
        return {"tables": totals.as_dicts(), "mode": "live"}
    except Exception as err:
        return {"tables": [], "mode": "mock", "note": str(err)[:200]}


@router.post("/investigations", status_code=202)
def create_investigation(body: InvestigationRequest, background: BackgroundTasks) -> dict:
    from app.memory.ephemeral import INVESTIGATION_LATCH, LATCH_TTL_S

    runtime = get_runtime()
    # Latch FIRST — a blocked attempt must never persist a phantom investigation.
    inv = Investigation(question=body.question)
    holder = runtime.ephemeral.acquire_latch(INVESTIGATION_LATCH, inv.id, LATCH_TTL_S)
    if holder is not None:
        raise HTTPException(
            409, f"an investigation is already active ({holder}) — one analytical context at a time"
        )
    runtime.working.put(inv)
    execution = dispatch_investigation(inv.id)
    if execution == "local":
        background.add_task(run_investigation, inv.id)
    return {"id": inv.id, "status": inv.status.value, "execution": execution}


@router.get("/investigations")
def list_investigations() -> list[dict]:
    return [_summary(i) for i in get_runtime().working.all()]


@router.get("/investigations/{inv_id}")
def get_investigation(inv_id: str) -> dict:
    inv = get_runtime().working.get(inv_id)
    if inv is None:
        raise HTTPException(404, "investigation not found")
    return inv.model_dump(mode="json")


@router.post("/investigations/{inv_id}/decision", status_code=202)
def decide(inv_id: str, body: DecisionRequest, background: BackgroundTasks) -> dict:
    runtime = get_runtime()
    inv = runtime.working.get(inv_id)
    if inv is None:
        raise HTTPException(404, "investigation not found")
    if body.decision not in VALID_DECISIONS:
        raise HTTPException(400, f"decision must be one of {sorted(VALID_DECISIONS)}")
    if inv.status != InvestigationStatus.RECOMMENDED:
        raise HTTPException(400, f"no recommendation awaiting a decision (status {inv.status.value})")
    execution = dispatch_decision(inv.id, body.decision, body.note)
    if execution == "local":
        background.add_task(run_decision, inv.id, body.decision, body.note)
    return {"id": inv.id, "decision": body.decision, "status": "processing", "execution": execution}


@router.get("/events")
def events(limit: int = 150) -> list[dict]:
    return get_runtime().bus.tail(limit)


@router.get("/memory/episodic")
def episodic(limit: int = 50) -> list[dict]:
    return get_runtime().episodic.list(limit)
