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
            "UNION ALL SELECT 'ops_events', count() FROM genesis_institutional.ops_events "
            "UNION ALL SELECT 'eras', count() FROM genesis_institutional.eras "
            "UNION ALL SELECT 'years', toUInt64(max(toYear(released_at)) - 1912 + 1) "
            "FROM genesis_institutional.projects WHERE released_at IS NOT NULL"
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


# the wall plots REAL dollars — the corpus's own rule: cross-era money deflates
CENTURY_SQL = (
    "SELECT toYear(a.month) AS y, "
    "multiIf(a.channel IN ('theatrical', 'theatrical_reissue'), 'theatrical', "
    "        a.channel IN ('tv_licensing', 'syndication', 'pay_cable'), 'television', "
    "        a.channel IN ('home_video', 'ppv_vod', 'est', 'pvod'), 'home_video', "
    "        a.channel = 'streaming_licensed', 'licensed_streaming', "
    "        'convergence_plus') AS channel_group, "
    "round(sum(a.revenue * c.mult_to_2026) / 1e6, 1) AS revenue_2026_m "
    "FROM genesis_institutional.audience_monthly a "
    "JOIN genesis_institutional.cpi_annual c ON c.year = toYear(a.month) "
    "GROUP BY y, channel_group ORDER BY y, channel_group"
)


@router.get("/century")
def century() -> dict:
    """The whole corpus as one picture: yearly revenue by channel group, plus
    the era boundaries and shock windows that explain its shape."""
    runtime = get_runtime()
    try:
        series = runtime.clickhouse.run_query(CENTURY_SQL, tag="century")
        eras = runtime.clickhouse.run_query(
            "SELECT era_id, name, toYear(start_date) AS from_year, toYear(end_date) AS to_year "
            "FROM genesis_institutional.eras ORDER BY era_id")
        shocks = runtime.clickhouse.run_query(
            "SELECT name, toYear(start_date) AS from_year, toYear(end_date) AS to_year, "
            "attendance_mult FROM genesis_institutional.shock_calendar "
            "WHERE attendance_mult != 1 ORDER BY start_date")
        return {"series": series.as_dicts(), "eras": eras.as_dicts(),
                "shocks": shocks.as_dicts(), "mode": "live"}
    except Exception as err:
        return {"series": [], "eras": [], "shocks": [], "mode": "mock",
                "note": str(err)[:200]}


@router.get("/showcase")
def showcase() -> list[dict]:
    """The deep-dive capabilities, run live through the read-only MCP path.

    Seven queries, each exercising a named ClickHouse feature the ordinary
    loop never touches (windows, windowFunnel, quantiles, arrays, ASOF,
    argMax, dictGet), each with its timing — the SQL itself is the exhibit.
    """
    from app.showcase import SHOWCASE

    runtime = get_runtime()
    out = []
    for key, item in SHOWCASE.items():
        try:
            result = runtime.clickhouse.run_query(item["sql"], tag=f"sc-{key}")
            out.append({"key": key, "feature": item["feature"], "story": item["story"],
                        "sql": item["sql"].strip(), "columns": result.columns,
                        "rows": result.rows[:20], "row_count": result.row_count,
                        "elapsed_ms": round(result.elapsed_ms, 1), "error": None})
        except Exception as err:            # one broken exhibit must not hide the rest
            out.append({"key": key, "feature": item["feature"], "story": item["story"],
                        "sql": item["sql"].strip(), "columns": [], "rows": [],
                        "row_count": 0, "elapsed_ms": 0.0, "error": str(err)[:300]})
    return out


@router.get("/investigations/{inv_id}/costs")
def investigation_costs(inv_id: str) -> dict:
    """What each of this investigation's queries actually cost ClickHouse —
    read from system.query_log by tag. Empty until the log flushes (~8s) or in
    mock mode: costs are a live-only proof, never fabricated."""
    runtime = get_runtime()
    inv = runtime.working.get(inv_id)
    if inv is None:
        raise HTTPException(404, "investigation not found")
    return runtime.clickhouse.costs_for([q.id for q in inv.queries])


@router.get("/showcase/costs")
def showcase_costs() -> dict:
    from app.showcase import SHOWCASE

    return get_runtime().clickhouse.costs_for([f"sc-{k}" for k in SHOWCASE])


@router.get("/sufficiency")
def sufficiency() -> dict:
    """What the corpus can answer, before any cognition is spent: per-channel
    coverage spans and title counts. INSUFFICIENT should be knowable for free."""
    runtime = get_runtime()
    try:
        spans = runtime.clickhouse.run_query(
            "SELECT channel, toYear(min(at)) AS from_year, toYear(max(at)) AS to_year, "
            "uniqExact(project_id) AS titles, countIf(isNotNull(completion)) > 0 AS has_completion "
            "FROM genesis_institutional.audience_performance "
            "GROUP BY channel ORDER BY from_year, channel LIMIT 200", tag="sufficiency")
        corpus = runtime.clickhouse.run_query(
            "SELECT toYear(min(greenlit_at)) AS founded, toYear(max(greenlit_at)) AS latest, "
            "uniqExact(project_id) AS titles FROM genesis_institutional.projects")
        return {"channels": spans.as_dicts(), "corpus": corpus.as_dicts()[0], "mode": "live"}
    except Exception as err:
        return {"channels": [], "corpus": {}, "mode": "mock", "note": str(err)[:200]}


@router.post("/requery/{query_id}", status_code=200)
def requery(query_id: str) -> dict:
    """The reproducibility receipt: re-run a stored query's exact SQL through
    the same read-only MCP path, right now, and compare the shape."""
    runtime = get_runtime()
    for inv in runtime.working.all():
        for query in inv.queries:
            if query.id == query_id and query.sql:
                result = runtime.clickhouse.run_query(query.sql, tag=f"rq-{query_id}")
                return {"query_id": query_id,
                        "original_rows": query.row_count, "fresh_rows": result.row_count,
                        "reproduced": result.row_count == query.row_count,
                        "elapsed_ms": round(result.elapsed_ms, 1),
                        "rows": result.rows[:5]}
    raise HTTPException(404, "query not found")


@router.get("/events")
def events(limit: int = 150) -> list[dict]:
    return get_runtime().bus.tail(limit)


@router.get("/memory/episodic")
def episodic(limit: int = 50) -> list[dict]:
    return get_runtime().episodic.list(limit)
