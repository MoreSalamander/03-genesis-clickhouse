"""Gemini cognition layer (locked §2.8: planning, schema-grounded SQL, framing,
narrative — while every number comes from ClickHouse and every statistic is
computed in Python).

LIVE mode calls Gemini at runtime via the official `google-genai` SDK (accepted
hackathon Google Cloud SDK — imported and actually called). MOCK mode is a
deterministic stand-in so the full loop runs with no credentials. Both speak the
same role-based interface, so agents never know which one they have.
"""
from __future__ import annotations

import json
import re
from typing import Any, Protocol

from app.config import Settings

DOMAINS = ["production_economics", "audience_distribution", "financial_performance",
           "operational_history"]

ROLE_PROMPTS: dict[str, str] = {
    "analytical_plan": (
        "You are the Analytical Planner for a film studio's Institutional Intelligence system. "
        "Decompose the Studio Head's question into testable hypotheses across these cognitive domains: "
        "production_economics, audience_distribution, financial_performance, operational_history "
        "(strategic_pattern insights emerge in synthesis). Use the provided table schemas. Return JSON: "
        "{\"hypotheses\": [{\"domain\": str, \"statement\": str (a falsifiable claim about the corpus), "
        "\"rationale\": str, \"intents\": [{\"purpose\": str (what one SQL query should measure), "
        "\"verification\": {\"metric_col\": str, \"group_col\": str, \"n_col\": str, \"std_col\": str|null, "
        "\"split_col\": str|null}}]}]}. 3-5 hypotheses total, 1-2 intents each. Each intent must be "
        "answerable by ONE aggregate SELECT whose result includes the verification columns: a grouping "
        "column, a numeric metric, an observation count (n_col), and where meaningful a stddev column "
        "and a second split column for stability checks. For contested territory (e.g. sequel economics) "
        "give the SAME hypothesis two intents whose slicings could plausibly disagree."
    ),
    "sql_generation": (
        "You are the Query Engineer for a film studio's analytical system on ClickHouse. Write ONE "
        "ClickHouse SELECT statement for the given intent, grounded STRICTLY in the provided schemas "
        "(never invent tables or columns). The result's OUTPUT COLUMN ALIASES must EXACTLY equal the "
        "names in the intent's verification spec — alias with AS: the grouping column AS <group_col>, "
        "the numeric metric AS <metric_col>, the per-group observation count AS <n_col> (use count()), "
        "and when given, a stddevPop AS <std_col> and a second grouping AS <split_col>. Prefer "
        "aggregates over raw scans; joins on project_id; LIMIT 200. ClickHouse dialect notes: "
        "use countIf/sumIf/avgIf/medianExact/stddevPop freely; Nullable dates compare with IS NOT NULL. "
        "Return JSON: {\"sql\": str, \"reasoning\": str (one sentence)}."
    ),
    "sql_repair": (
        "You are the Query Engineer repairing a failed ClickHouse SELECT. Use the error message and the "
        "schemas to produce a corrected query with the same analytical intent and required result "
        "columns. Return JSON: {\"sql\": str, \"fix\": str (what changed)}."
    ),
    "interpretation": (
        "You are a Domain Analyst panel for a film studio. Given hypotheses, executed query results, "
        "and rule-derived verification states (computed in code — do not dispute them), write competing "
        "interpretations of the evidence. For every CONTESTED finding produce at least two "
        "interpretations with genuinely opposing stances, each citing the specific query ids that "
        "support it. Return JSON: {\"interpretations\": [{\"label\": str (short), \"stance\": str, "
        "\"narrative\": str (2-3 sentences, cite numbers from the results verbatim), "
        "\"cited_query_ids\": [str], \"cited_finding_ids\": [str]}]}. Never invent numbers."
    ),
    "scenario_frame": (
        "You are the Scenario agent for a film studio. From the Studio Head's question and the findings, "
        "define ONE what-if simulation the system should run over the historical cohort. The group must "
        "be a CATEGORICAL STRING column (e.g. release_window, budget_class, genre — never a boolean), "
        "baseline_group/alternative_group must be values that column actually takes, and the cohort "
        "filter must be broad enough that EACH group keeps at least 5 titles (prefer wide budget bands "
        "like $10M-$120M and multiple genres). Return JSON: "
        "{\"scenario\": str (plain-language), \"cohort_sql_purpose\": str (what per-title cohort rows "
        "the simulation needs: one row per comparable title with a numeric outcome column and the group "
        "column for the assumption being changed), \"outcome_col\": str, \"group_col\": str, "
        "\"baseline_group\": str, \"alternative_group\": str, \"scale_value\": float (e.g. the proposed "
        "budget in USD the outcome multiple applies to, or 1.0)}."
    ),
    "synthesis": (
        "You are the Institutional Intelligence Executive of a film studio ('Convergence Studios'). "
        "Synthesize the investigation into one recommendation for the Studio Head. The confidence "
        "number is computed by the system from verification coverage — do NOT produce one. Ground "
        "every claim in the findings/simulation given; preserve contested readings as open tensions. "
        "Return JSON: {\"action\": str (one imperative sentence), \"rationale\": str (3-5 sentences "
        "citing findings by their statements and numbers), \"caveats\": [str, ...] (each contested or "
        "insufficient area, plainly)}."
    ),
}


class Cognition(Protocol):
    live: bool

    def generate_json(self, role: str, payload: dict[str, Any]) -> dict[str, Any]: ...


class GeminiCognition:
    """Real Gemini via google-genai (API key or Vertex AI, auto-detected from env)."""

    live = True

    def __init__(self, settings: Settings):
        from google import genai  # accepted hackathon SDK: google-genai

        self.settings = settings
        self._client = genai.Client()
        self._model = settings.gemini_model

    def generate_json(self, role: str, payload: dict[str, Any]) -> dict[str, Any]:
        from app.observability.tracing import span

        prompt = ROLE_PROMPTS[role] + "\n\nINPUT:\n" + json.dumps(payload, ensure_ascii=False, default=str)
        with span("gemini.generate", role=role, model=self._model) as sp:
            response = self._client.models.generate_content(
                model=self._model,
                contents=prompt,
                config={"response_mime_type": "application/json", "temperature": 0.2},
            )
            usage = getattr(response, "usage_metadata", None)
            if sp is not None and usage is not None:
                sp.set_attribute("tokens.prompt", getattr(usage, "prompt_token_count", 0) or 0)
                sp.set_attribute("tokens.total", getattr(usage, "total_token_count", 0) or 0)
        text = response.text or ""
        try:
            return json.loads(text)
        except json.JSONDecodeError:
            match = re.search(r"\{.*\}", text, re.DOTALL)
            if match:
                return json.loads(match.group(0))
            raise


# ---------------------------------------------------------------------------
# MOCK — deterministic cognition over the canonical greenlight investigation
# ---------------------------------------------------------------------------

CANONICAL_SQL = {
    "cohort_overrun_by_class": (
        "SELECT p.budget_class AS budget_class, round(sum(f.actual)/sum(f.planned), 4) AS overrun_ratio, "
        "count() AS n, round(stddevPop(f.actual/nullIf(f.planned,0)), 4) AS spend_std "
        "FROM genesis_institutional.financial_ledger f "
        "JOIN genesis_institutional.projects p ON p.project_id = f.project_id "
        "GROUP BY p.budget_class ORDER BY overrun_ratio DESC LIMIT 200"
    ),
    "sequel_opening_premium": (
        "SELECT p.is_sequel AS is_sequel, round(avg(t.open_ratio), 4) AS open_over_budget, "
        "count() AS n, round(stddevPop(t.open_ratio), 4) AS ratio_std "
        "FROM (SELECT a.project_id, sum(a.revenue)/any(p2.budget_usd) AS open_ratio "
        "      FROM genesis_institutional.audience_performance a "
        "      JOIN genesis_institutional.projects p2 ON p2.project_id = a.project_id "
        "      WHERE p2.released_at IS NOT NULL AND a.at < p2.released_at + 30 "
        "      GROUP BY a.project_id) t "
        "JOIN genesis_institutional.projects p ON p.project_id = t.project_id "
        "GROUP BY p.is_sequel ORDER BY is_sequel LIMIT 200"
    ),
    "sequel_franchise_decay": (
        "SELECT p.is_sequel AS is_sequel, round(avg(t.tail_share), 4) AS tail_share, "
        "count() AS n, round(stddevPop(t.tail_share), 4) AS share_std "
        "FROM (SELECT a.project_id, sumIf(a.revenue, a.at >= p2.released_at + 365)/sum(a.revenue) AS tail_share "
        "      FROM genesis_institutional.audience_performance a "
        "      JOIN genesis_institutional.projects p2 ON p2.project_id = a.project_id "
        "      WHERE p2.franchise != '' AND p2.released_at IS NOT NULL "
        "      GROUP BY a.project_id) t "
        "JOIN genesis_institutional.projects p ON p.project_id = t.project_id "
        "GROUP BY p.is_sequel ORDER BY is_sequel LIMIT 200"
    ),
    "release_window_seasonality": (
        "SELECT p.release_window AS release_window, round(avg(a.revenue), 2) AS daily_revenue, "
        "count() AS n, round(stddevPop(a.revenue), 2) AS revenue_std, "
        "if(toYear(a.at) >= 2021, 'post2021', 'pre2021') AS era "
        "FROM genesis_institutional.audience_performance a "
        "JOIN genesis_institutional.projects p ON p.project_id = a.project_id "
        "WHERE a.at < p.released_at + 90 "
        "GROUP BY p.release_window, era ORDER BY p.release_window, era LIMIT 200"
    ),
    "overrun_schedule_coupling": (
        "SELECT p.budget_class AS budget_class, round(avg(s.slip_days), 2) AS avg_slip_days, "
        "count() AS n, round(stddevPop(s.slip_days), 2) AS slip_std "
        "FROM (SELECT project_id, sum(value) AS slip_days "
        "      FROM genesis_institutional.production_events WHERE event_type = 'schedule_slip' "
        "      GROUP BY project_id) s "
        "JOIN genesis_institutional.projects p ON p.project_id = s.project_id "
        "GROUP BY p.budget_class ORDER BY avg_slip_days DESC LIMIT 200"
    ),
    "scenario_cohort_windows": (
        "SELECT p.release_window AS release_window, p.title AS title, "
        "round(sum(a.revenue)/any(p.budget_usd), 4) AS rev_multiple "
        "FROM genesis_institutional.audience_performance a "
        "JOIN genesis_institutional.projects p ON p.project_id = a.project_id "
        "WHERE p.genre IN ('scifi','fantasy','action','animation','thriller') AND p.budget_usd BETWEEN 10000000 AND 120000000 "
        "AND p.released_at IS NOT NULL "
        "GROUP BY p.release_window, p.title ORDER BY p.release_window, rev_multiple LIMIT 200"
    ),
}


class MockCognition:
    """Deterministic cognition — the canonical greenlight investigation."""

    live = False

    def generate_json(self, role: str, payload: dict[str, Any]) -> dict[str, Any]:
        handler = getattr(self, f"_{role}", None)
        if handler is None:
            raise ValueError(f"MockCognition has no handler for role '{role}'")
        return handler(payload)

    def _analytical_plan(self, payload: dict) -> dict:
        return {
            "hypotheses": [
                {"domain": "financial_performance",
                 "statement": "Cost overruns scale with budget class; a tentpole-adjacent budget carries a materially higher overrun ratio.",
                 "rationale": "Planned-vs-actual ledger history is the studio's strongest predictor of budget risk.",
                 "intents": [{"purpose": "canonical:cohort_overrun_by_class",
                              "verification": {"metric_col": "overrun_ratio", "group_col": "budget_class",
                                               "n_col": "n", "std_col": "spend_std", "split_col": None}}]},
                {"domain": "audience_distribution",
                 "statement": "Sequels outperform originals — or underperform once decay is controlled: the corpus decides.",
                 "rationale": "Sequel economics drive the premium-vs-fatigue tension in every greenlight.",
                 "intents": [{"purpose": "canonical:sequel_opening_premium",
                              "verification": {"metric_col": "open_over_budget", "group_col": "is_sequel",
                                               "n_col": "n", "std_col": "ratio_std", "split_col": None}},
                             {"purpose": "canonical:sequel_franchise_decay",
                              "verification": {"metric_col": "tail_share", "group_col": "is_sequel",
                                               "n_col": "n", "std_col": "share_std", "split_col": None}}]},
                {"domain": "audience_distribution",
                 "statement": "Release window materially shifts early revenue (Q2/Q4 premium).",
                 "rationale": "Window choice is a controllable lever in the proposal.",
                 "intents": [{"purpose": "canonical:release_window_seasonality",
                              "verification": {"metric_col": "daily_revenue", "group_col": "release_window",
                                               "n_col": "n", "std_col": "revenue_std", "split_col": "era"}}]},
                {"domain": "operational_history",
                 "statement": "Schedule slips concentrate in larger productions, coupling delivery risk to budget class.",
                 "rationale": "Slip history calibrates the operational risk of the proposal.",
                 "intents": [{"purpose": "canonical:overrun_schedule_coupling",
                              "verification": {"metric_col": "avg_slip_days", "group_col": "budget_class",
                                               "n_col": "n", "std_col": "slip_std", "split_col": None}}]},
            ]
        }

    def _sql_generation(self, payload: dict) -> dict:
        purpose = payload.get("intent", {}).get("purpose", "")
        key = purpose.split("canonical:", 1)[-1] if "canonical:" in purpose else ""
        sql = CANONICAL_SQL.get(key)
        if sql is None:
            sql = ("SELECT budget_class, count() AS n FROM genesis_institutional.projects "
                   "GROUP BY budget_class LIMIT 200")
        return {"sql": sql, "reasoning": f"canonical query for {key or 'fallback'}"}

    def _sql_repair(self, payload: dict) -> dict:
        return {"sql": payload.get("sql", ""), "fix": "mock repair: unchanged"}

    def _interpretation(self, payload: dict) -> dict:
        contested = [f for f in payload.get("findings", []) if f.get("state") == "CONTESTED"]
        interpretations = [
            {"label": "Scale discipline", "stance": "risk",
             "narrative": "Overrun ratios rise monotonically with budget class in the ledger history; "
                          "a $45M proposal sits in the band where overruns and schedule slips concentrate.",
             "cited_query_ids": payload.get("query_ids", [])[:1], "cited_finding_ids": []},
        ]
        if contested:
            interpretations += [
                {"label": "Sequel premium", "stance": "for",
                 "narrative": "Sequels open materially above originals per budget dollar in the 30-day window — "
                              "the franchise brand converts directly into opening revenue.",
                 "cited_query_ids": payload.get("query_ids", [])[1:2],
                 "cited_finding_ids": [contested[0].get("id", "")]},
                {"label": "Franchise fatigue", "stance": "against",
                 "narrative": "Within franchises, sequels hold a smaller share of revenue past year one — "
                              "the premium is front-loaded and decays faster than originals.",
                 "cited_query_ids": payload.get("query_ids", [])[2:3],
                 "cited_finding_ids": [contested[0].get("id", "")]},
            ]
        return {"interpretations": interpretations}

    def _scenario_frame(self, payload: dict) -> dict:
        question = payload.get("question", "")
        budget = 45_000_000.0
        match = re.search(r"\$(\d+(?:\.\d+)?)\s*M", question, re.IGNORECASE)
        if match:
            budget = float(match.group(1)) * 1e6
        return {"scenario": "Shift the proposed release from Q2 to Q4 and project total revenue on the "
                            "comparable cohort's distribution",
                "cohort_sql_purpose": "canonical:scenario_cohort_windows",
                "outcome_col": "rev_multiple", "group_col": "release_window",
                "baseline_group": "Q2", "alternative_group": "Q4", "scale_value": budget}

    def _synthesis(self, payload: dict) -> dict:
        coverage = payload.get("coverage", {})
        contested = coverage.get("CONTESTED", 0)
        return {
            "action": "Greenlight at the proposed budget with a staged contingency, and hold the release "
                      "window decision until the simulation delta is reviewed.",
            "rationale": "Verified history shows overruns scale with budget class and slips concentrate in "
                         "larger productions, so the proposal carries quantifiable but bounded delivery risk. "
                         "Release-window seasonality is verified and favors the stronger window. Sequel "
                         "economics remain contested in our own history — openings run ahead of originals "
                         "while franchise tails decay faster — and both readings are preserved.",
            "caveats": (["Sequel premium vs franchise fatigue is CONTESTED — do not treat either as settled."]
                        if contested else []) + ["Statistics summarize the studio's own corpus, not the market."],
        }


def get_cognition(settings: Settings) -> Cognition:
    if settings.gemini_live:
        return GeminiCognition(settings)
    return MockCognition()
