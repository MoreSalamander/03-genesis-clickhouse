"""Institutional Intelligence Executive — owns the analytical objective
(locked §2.3) and drives the locked loop (§2.6):

  question → scope → plan → iterative SQL → statistical verification →
  competing interpretations → findings → simulation → recommendation →
  Studio Head decision → promotion.

Each stage is a method the Temporal activities call by investigation id; state
lives in the durable working memory between stages, so a worker restart resumes
exactly where the loop stopped.
"""
from __future__ import annotations

import re

from app.agents.query.engineer import snapshot_document, stats_payload
from app.memory.ephemeral import INVESTIGATION_LATCH
from app.models.institutional import (
    Decision,
    Finding,
    Hypothesis,
    Interpretation,
    Investigation,
    InvestigationStatus,
    Promotion,
    Recommendation,
    VerificationState,
)

MAX_ROUNDS = 3

_STATE_EVENT = {
    VerificationState.VERIFIED: "finding.verified",
    VerificationState.WEAK: "finding.weak",
    VerificationState.CONTESTED: "finding.contested",
    VerificationState.REGIME: "finding.regime",
    VerificationState.INSUFFICIENT: "finding.insufficient",
}


class InstitutionalExecutive:
    def __init__(self, runtime):
        self.rt = runtime

    # -- helpers ------------------------------------------------------------
    def _get(self, inv_id: str) -> Investigation:
        inv = self.rt.working.get(inv_id)
        if inv is None:
            raise RuntimeError(f"unknown investigation {inv_id}")
        return inv

    def _save(self, inv: Investigation) -> None:
        inv.touch()
        self.rt.working.put(inv)

    # -- stage: plan --------------------------------------------------------
    def plan(self, inv_id: str) -> str:
        inv = self._get(inv_id)
        inv.status = InvestigationStatus.PLANNING
        self._save(inv)
        if inv.round == 1:
            self.rt.bus.emit("investigation.started", investigation_id=inv.id,
                             question=inv.question, round=inv.round)
        inv.scope = {
            "datahub": self.rt.datahub.scope_for(inv.question),
            "corpus": self._corpus_summary(),
            "deeper_guidance": inv.deeper_guidance,
        }
        payload = {"question": inv.question, "schemas": self.rt.engineer.schema_context(),
                   "scope": inv.scope}
        if inv.deeper_guidance:
            payload["studio_head_guidance"] = inv.deeper_guidance
        planned = self.rt.cognition.generate_json("analytical_plan", payload)
        hypotheses = []
        intents_by_hyp: dict[str, list[dict]] = {}
        for h in planned.get("hypotheses", [])[:6]:
            hyp = Hypothesis(domain=str(h.get("domain", "strategic_pattern")),
                             statement=str(h.get("statement", "")).strip(),
                             rationale=str(h.get("rationale", "")).strip())
            hyp_intents = []
            for intent in h.get("intents", [])[:2]:
                hyp_intents.append({"purpose": str(intent.get("purpose", "")),
                                    "verification": intent.get("verification", {}) or {}})
            hyp.query_intents = [i["purpose"] for i in hyp_intents]
            hypotheses.append(hyp)
            intents_by_hyp[hyp.id] = hyp_intents
        inv.hypotheses = hypotheses
        # intents must survive the activity boundary — persisted inside scope
        inv.scope["intents"] = intents_by_hyp
        inv.status = InvestigationStatus.ANALYZING
        self._save(inv)
        return inv.status.value

    def _corpus_summary(self) -> dict:
        try:
            # 114 years of nominal dollars sum to nonsense — deflate to 2026
            result = self.rt.clickhouse.run_query(
                "SELECT status, count() AS n, "
                "round(sum(p.budget_usd * c.mult_to_2026)/1e9, 2) AS total_budget_2026_b "
                "FROM genesis_institutional.projects p "
                "JOIN genesis_institutional.cpi_annual c ON c.year = toYear(p.greenlit_at) "
                "GROUP BY status ORDER BY n DESC"
            )
            return {"projects_by_status": result.as_dicts(),
                    "corpus": "Convergence Studios, founded 1912 — 114 years, ten eras"}
        except Exception as err:
            return {"projects_by_status": [], "note": f"scope query unavailable: {err}"}

    # -- stage: analyze -----------------------------------------------------
    def analyze(self, inv_id: str) -> str:
        inv = self._get(inv_id)
        intents_by_hyp: dict = inv.scope.get("intents", {})
        for hyp in inv.hypotheses:
            for intent in intents_by_hyp.get(hyp.id, []):
                query = self.rt.engineer.execute_intent(hyp.id, hyp.domain, intent)
                query.snapshot_object = self.rt.objects.put_result(
                    inv.id, query.id, snapshot_document(query))
                inv.queries.append(query)
                self.rt.bus.emit("analysis.executed", investigation_id=inv.id,
                                 query_id=query.id, hypothesis_id=hyp.id, purpose=query.purpose,
                                 rows=query.row_count, elapsed_ms=query.elapsed_ms,
                                 repairs=query.repairs, error=query.error)
                self._save(inv)  # evidence lands durably as it is produced
        inv.status = InvestigationStatus.VERIFYING
        self._save(inv)
        return inv.status.value

    # -- stage: verify (statistics + analyst panel) -------------------------
    def verify(self, inv_id: str) -> str:
        inv = self._get(inv_id)
        intents_by_hyp: dict = inv.scope.get("intents", {})
        specs: dict[str, dict] = {}
        for hyp in inv.hypotheses:
            hyp_queries = [q for q in inv.queries if q.hypothesis_id == hyp.id]
            intents = intents_by_hyp.get(hyp.id, [])
            for query in hyp_queries:
                matched = next((i.get("verification", {}) for i in intents
                                if i.get("purpose") == query.purpose), {})
                specs[query.id] = matched
            rows_of = {q.id: q.rows for q in hyp_queries}
            finding = self.rt.verifier.verify_hypothesis(hyp, hyp_queries, rows_of, specs)
            inv.findings.append(finding)
            self.rt.bus.emit(_STATE_EVENT[finding.state], investigation_id=inv.id,
                             finding_id=finding.id, domain=finding.domain,
                             statement=finding.statement, basis=finding.basis)
        self._save(inv)

        panel = self.rt.cognition.generate_json("interpretation", {
            "question": inv.question,
            "hypotheses": [h.model_dump(mode="json") for h in inv.hypotheses],
            "findings": [f.model_dump(mode="json") for f in inv.findings],
            "results": [stats_payload(q) for q in inv.queries],
            "query_ids": [q.id for q in inv.queries],
        })
        inv.interpretations = [
            Interpretation(label=str(i.get("label", ""))[:60], stance=str(i.get("stance", "")),
                           narrative=str(i.get("narrative", "")),
                           cited_query_ids=list(i.get("cited_query_ids", [])),
                           cited_finding_ids=list(i.get("cited_finding_ids", [])))
            for i in panel.get("interpretations", [])[:8]
        ]
        # contested findings must reach the Studio Head with >= 2 stances (locked §2.3)
        contested = [f for f in inv.findings if f.state == VerificationState.CONTESTED]
        if contested and len({i.stance for i in inv.interpretations}) < 2:
            f0 = contested[0]
            inv.interpretations.append(Interpretation(
                label="Counter-reading", stance="counter",
                narrative=f"The disagreeing analyses behind '{f0.statement[:80]}' support the "
                          f"opposite reading; both are preserved ({f0.basis}).",
                cited_finding_ids=[f0.id], cited_query_ids=f0.evidence_query_ids))
        inv.status = InvestigationStatus.SIMULATING if self._wants_simulation(inv) \
            else InvestigationStatus.RECOMMENDED
        self._save(inv)
        return inv.status.value

    @staticmethod
    def _wants_simulation(inv: Investigation) -> bool:
        return bool(re.search(r"\b(should|what if|greenlight|scenario|shift|instead)\b",
                              inv.question, re.IGNORECASE))

    # -- stage: simulate ----------------------------------------------------
    def simulate(self, inv_id: str) -> str:
        inv = self._get(inv_id)
        if inv.status != InvestigationStatus.SIMULATING:
            return inv.status.value
        sim, query = self.rt.scenario.simulate(
            inv.question, [f.model_dump(mode="json") for f in inv.findings])
        if query is not None:
            query.snapshot_object = self.rt.objects.put_result(
                inv.id, query.id, snapshot_document(query))
            inv.queries.append(query)
            self.rt.bus.emit("analysis.executed", investigation_id=inv.id, query_id=query.id,
                             hypothesis_id="scenario", purpose=query.purpose,
                             rows=query.row_count, elapsed_ms=query.elapsed_ms,
                             repairs=query.repairs, error=query.error)
        if sim is not None:
            inv.simulation = sim
            self.rt.bus.emit("simulation.completed", investigation_id=inv.id,
                             scenario=sim.scenario, delta_p50=sim.delta.get("p50"),
                             n_runs=sim.n_runs, seed=sim.seed)
        inv.status = InvestigationStatus.RECOMMENDED
        self._save(inv)
        return inv.status.value

    # -- stage: recommend ---------------------------------------------------
    def recommend(self, inv_id: str) -> str:
        inv = self._get(inv_id)
        coverage = inv.coverage()
        total = max(1, len(inv.findings))
        # confidence is a FUNCTION OF VERIFICATION COVERAGE (locked §2.3) — computed
        # here, never asserted by the model: verified findings carry the weight,
        # era-bounded REGIME truths carry most of it (Studio Head, 2026-08-19),
        # weak ones a fraction, contested ones are preserved tension (no credit,
        # no penalty), insufficient ones subtract.
        confidence = (0.30
                      + 0.60 * coverage["VERIFIED"] / total
                      + 0.40 * coverage["REGIME"] / total
                      + 0.10 * coverage["WEAK"] / total
                      - 0.05 * coverage["INSUFFICIENT"] / total)
        confidence = round(min(0.95, max(0.20, confidence)), 2)
        synthesis = self.rt.cognition.generate_json("synthesis", {
            "question": inv.question,
            "findings": [f.model_dump(mode="json") for f in inv.findings],
            "interpretations": [i.model_dump(mode="json") for i in inv.interpretations],
            "simulation": inv.simulation.model_dump(mode="json") if inv.simulation else None,
            "coverage": coverage,
        })
        inv.recommendation = Recommendation(
            action=str(synthesis.get("action", "")).strip(),
            rationale=str(synthesis.get("rationale", "")).strip(),
            confidence=confidence, coverage=coverage,
            finding_ids=[f.id for f in inv.findings],
            caveats=[str(c) for c in synthesis.get("caveats", [])][:6],
        )
        inv.status = InvestigationStatus.RECOMMENDED
        self._save(inv)
        self.rt.bus.emit("recommendation.created", investigation_id=inv.id,
                         action=inv.recommendation.action, confidence=confidence,
                         coverage=coverage)
        return inv.status.value

    # -- stage: decide ------------------------------------------------------
    def decide(self, inv_id: str, decision: str, note: str = "") -> str:
        inv = self._get(inv_id)
        decision = decision.lower().strip()
        inv.decisions.append(Decision(decision=decision, note=note))
        self.rt.bus.emit("authorization.decided", investigation_id=inv.id,
                         decision=decision, note=note, round=inv.round)
        if decision == "approved":
            urns = self.rt.datahub.promote(inv)
            inv.promotion = Promotion(datahub_urns=urns)
            if urns:
                self.rt.bus.emit("knowledge.promoted", investigation_id=inv.id,
                                 datahub_urns=urns)
            inv.status = InvestigationStatus.PROMOTED
            self._finalize(inv)
        elif decision == "deeper" and inv.round < MAX_ROUNDS:
            if note:
                inv.deeper_guidance.append(note)
            inv.round += 1
            inv.status = InvestigationStatus.PLANNING
            self._save(inv)
            return "DEEPER"
        else:
            if decision == "deeper":
                inv.decisions.append(Decision(
                    decision="rejected",
                    note=f"deeper-analysis budget exhausted ({MAX_ROUNDS} rounds)"))
            inv.status = InvestigationStatus.REJECTED
            self._finalize(inv)
        return inv.status.value

    # -- failure ------------------------------------------------------------
    def incomplete(self, inv_id: str, reason: str) -> str:
        inv = self._get(inv_id)
        inv.status = InvestigationStatus.INCOMPLETE
        inv.incomplete_reason = reason[:500]
        self.rt.bus.emit("investigation.incomplete", investigation_id=inv.id, reason=reason[:500])
        self._finalize(inv)
        return inv.status.value

    def _finalize(self, inv: Investigation) -> None:
        self._save(inv)
        self.rt.episodic.record(inv)
        if inv.status != InvestigationStatus.INCOMPLETE:
            self.rt.bus.emit("investigation.completed", investigation_id=inv.id,
                             status=inv.status.value, rounds=inv.round,
                             queries=len(inv.queries), coverage=inv.coverage())
        self.rt.ephemeral.release_latch(INVESTIGATION_LATCH)
