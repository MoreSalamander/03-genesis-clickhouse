"""Domain model for Institutional Intelligence investigations (locked §2.3, §2.6).

The analytical lineage is explicit and auditable:
question → hypotheses → executed SQL (AnalyticalQuery = evidence) → rule-derived
findings → competing interpretations → optional simulation → recommendation →
Studio Head decision → promotion. Verification states are computed in code from
the numbers ClickHouse returned — never asserted by the model.
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Optional

from pydantic import BaseModel, Field, PrivateAttr


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _id(prefix: str) -> str:
    return f"{prefix}-{uuid.uuid4().hex[:8]}"


class InvestigationStatus(str, Enum):
    PLANNING = "PLANNING"
    ANALYZING = "ANALYZING"
    VERIFYING = "VERIFYING"
    SIMULATING = "SIMULATING"
    RECOMMENDED = "RECOMMENDED"          # awaiting Studio Head authorization
    APPROVED = "APPROVED"
    REJECTED = "REJECTED"
    PROMOTED = "PROMOTED"                # approved + knowledge promoted to DataHub
    INCOMPLETE = "INCOMPLETE"            # substrate failure — numbers are never fabricated


class VerificationState(str, Enum):
    VERIFIED = "VERIFIED"          # n >= policy, effect > noise, stable across splits
    WEAK = "WEAK"                  # signal present but under-powered
    CONTESTED = "CONTESTED"        # two analyses disagree — preserved, never resolved
    INSUFFICIENT = "INSUFFICIENT"  # the corpus cannot answer; said plainly


class Hypothesis(BaseModel):
    id: str = Field(default_factory=lambda: _id("hyp"))
    domain: str                      # production_economics | audience_distribution | financial_performance | operational_history | strategic_pattern
    statement: str
    rationale: str = ""
    query_intents: list[str] = Field(default_factory=list)


class AnalyticalQuery(BaseModel):
    """One executed SQL step — the atomic unit of analytical evidence."""

    id: str = Field(default_factory=lambda: _id("qry"))
    hypothesis_id: str = ""
    domain: str = ""
    purpose: str = ""
    sql: str = ""
    columns: list[str] = Field(default_factory=list)
    rows: list[list[Any]] = Field(default_factory=list)   # capped sample; full set → MinIO
    row_count: int = 0
    elapsed_ms: float = 0.0
    repairs: int = 0                                       # bounded SQL-repair attempts used
    error: Optional[str] = None
    computed_stats: dict[str, float] = Field(default_factory=dict)
    snapshot_object: Optional[str] = None                  # MinIO object key of the full result
    at: datetime = Field(default_factory=_now)
    # transient full result set (stats + MinIO snapshot); never serialized
    _full_rows: list = PrivateAttr(default_factory=list)


class Finding(BaseModel):
    id: str = Field(default_factory=lambda: _id("fnd"))
    hypothesis_id: str = ""
    domain: str = ""
    statement: str
    state: VerificationState
    basis: str = ""                                        # how the rules derived the state
    stats: dict[str, float] = Field(default_factory=dict)
    evidence_query_ids: list[str] = Field(default_factory=list)


class Interpretation(BaseModel):
    """A competing reading of the evidence. CONTESTED findings keep >= 2 of these."""

    id: str = Field(default_factory=lambda: _id("int"))
    label: str
    narrative: str
    stance: str = ""                                       # e.g. "sequel premium" vs "franchise fatigue"
    cited_query_ids: list[str] = Field(default_factory=list)
    cited_finding_ids: list[str] = Field(default_factory=list)


class SimulationResult(BaseModel):
    id: str = Field(default_factory=lambda: _id("sim"))
    scenario: str
    params: dict[str, Any] = Field(default_factory=dict)
    baseline: dict[str, float] = Field(default_factory=dict)
    projected: dict[str, float] = Field(default_factory=dict)
    delta: dict[str, float] = Field(default_factory=dict)
    n_runs: int = 0
    seed: int = 0
    narrative: str = ""
    evidence_query_ids: list[str] = Field(default_factory=list)


class Recommendation(BaseModel):
    id: str = Field(default_factory=lambda: _id("rec"))
    action: str
    rationale: str
    confidence: float                                       # function of verification coverage
    coverage: dict[str, int] = Field(default_factory=dict)  # counts per verification state
    finding_ids: list[str] = Field(default_factory=list)
    caveats: list[str] = Field(default_factory=list)
    at: datetime = Field(default_factory=_now)


class Decision(BaseModel):
    decision: str                                           # approved | rejected | deeper
    note: str = ""
    by: str = "studio-head"
    at: datetime = Field(default_factory=_now)


class Promotion(BaseModel):
    datahub_urns: list[str] = Field(default_factory=list)
    at: datetime = Field(default_factory=_now)


class Investigation(BaseModel):
    id: str = Field(default_factory=lambda: _id("inv"))
    question: str
    status: InvestigationStatus = InvestigationStatus.PLANNING
    round: int = 1                                          # increments on "request deeper analysis"
    deeper_guidance: list[str] = Field(default_factory=list)
    scope: dict[str, Any] = Field(default_factory=dict)     # DataHub context + project dims
    hypotheses: list[Hypothesis] = Field(default_factory=list)
    queries: list[AnalyticalQuery] = Field(default_factory=list)
    findings: list[Finding] = Field(default_factory=list)
    interpretations: list[Interpretation] = Field(default_factory=list)
    simulation: Optional[SimulationResult] = None
    recommendation: Optional[Recommendation] = None
    decisions: list[Decision] = Field(default_factory=list)
    promotion: Optional[Promotion] = None
    escalated: bool = False
    incomplete_reason: Optional[str] = None
    created_at: datetime = Field(default_factory=_now)
    updated_at: datetime = Field(default_factory=_now)

    def touch(self) -> None:
        self.updated_at = _now()

    def query_by_id(self, qid: str) -> Optional[AnalyticalQuery]:
        return next((q for q in self.queries if q.id == qid), None)

    def coverage(self) -> dict[str, int]:
        counts = {state.value: 0 for state in VerificationState}
        for finding in self.findings:
            counts[finding.state.value] += 1
        return counts
