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
from app import runtime_proof

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
        "\"verification\": {\"metric_col\": str, \"group_col\": str, \"n_col\": str, \"titles_col\": str|null, "
        "\"std_col\": str|null, \"split_col\": str|null}}]}]}. 3-5 hypotheses total, 1-2 intents each. Each intent must be "
        "answerable by ONE aggregate SELECT whose result includes the verification columns: a grouping "
        "column, a numeric metric, an observation count (n_col), a TITLE-GRAIN count (titles_col — "
        "power is judged on the number of titles compared, never on fact rows), a stddev column, "
        "and an ERA SPLIT column (split_col) whenever the question permits one — cross-era "
        "stability is what separates VERIFIED (institutional truth) from REGIME (era-bounded). The corpus is Convergence Studios' complete "
        "history: ~4,600 titles across 114 years (1912-2026) in ten named industry eras (the `eras` "
        "table; projects carry era_id). Three structural requirements: (1) money columns are NOMINAL "
        "dollars of their year — any cross-era money comparison must deflate via cpi_annual "
        "(mult_to_2026) or compare era-relative fields like budget_class; (2) prefer ERA-SCOPED cohorts "
        "(join eras on era_id, or filter released_at ranges): a finding that holds across eras is "
        "institutional truth, one that holds in a single era is a regime — both are worth surfacing, "
        "and per-era title cohorts run in the hundreds while high-volume tables (audience_performance "
        "daily rows, production_events, financial_ledger) reach the millions; (3) for contested "
        "territory (e.g. sequel premium vs franchise fatigue) give the SAME hypothesis two intents "
        "whose slicings could plausibly DISAGREE in direction (e.g. opening-window comparison vs "
        "tail-share comparison) — disagreement between a hypothesis's own analyses is how the system "
        "surfaces contested truths. For long trend scans prefer the monthly rollups "
        "(audience_monthly, financial_monthly) over raw daily sweeps."
    ),
    "sql_generation": (
        "You are the Query Engineer for a film studio's analytical system on ClickHouse. Write ONE "
        "ClickHouse SELECT statement for the given intent, grounded STRICTLY in the provided schemas "
        "(never invent tables or columns). The result's OUTPUT COLUMN ALIASES must EXACTLY equal the "
        "names in the intent's verification spec — alias with AS: the grouping column AS <group_col>, "
        "the numeric metric AS <metric_col>, the per-group observation count AS <n_col> (use count()), "
        "a title-grain count AS <titles_col> (use uniqExact(project_id) — REQUIRED whenever titles "
        "are the unit), and when given, a stddevPop AS <std_col> and the era split AS <split_col> (use the era NAME e.name, never era_id — ranges must read as eras) "
        "(join eras ON era_id = projects.era_id and select e.name — REQUIRED when the spec names one). Prefer "
        "aggregates over raw scans; joins on project_id; LIMIT 200. ClickHouse dialect notes: "
        "use countIf/sumIf/avgIf/medianExact/stddevPop freely; Nullable dates compare with IS NOT NULL. The full instrument rack is available and ENCOURAGED where the intent calls for it: window functions (sum()/row_number() OVER (PARTITION BY ... ORDER BY ...)) for running curves and trajectories; quantiles(0.1,...,0.9)() for distributions instead of averages; groupArray/arraySort/arrayMap/arrayDifference/avgForEach for per-entity curve analysis; windowFunnel over genesis_institutional.distribution_events for release-window sequences; ASOF JOIN (equality key plus >=) for nearest-event attribution such as the shock_calendar; dictGetString('genesis_institutional.era_dict', 'name', toUInt64(0), toInt64(<Date32 col>)) to attribute any fact date to its era without a join. "
        "Corpus notes: money is NOMINAL — deflate with cpi_annual.mult_to_2026 when comparing across "
        "eras; audience_performance.completion is NULL outside streaming channels (2015+), so guard "
        "with isNotNull; era splits join eras ON era_id = projects.era_id (do NOT use range conditions "
        "inside JOIN ON — for date-range era attribution use CROSS JOIN eras plus a WHERE at BETWEEN "
        "start_date AND end_date); channels are era-gated (no home_video before 1980, no streaming "
        "before 2008). Return JSON: {\"sql\": str, \"reasoning\": str (one sentence)}."
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
        # First-hand proof of Google Cloud usage: the call came back.
        runtime_proof.record("gemini", "LIVE",
                             f"{self._model} returned a response this session")
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
        "SELECT p.budget_class AS budget_class, e.name AS era, "
        "round(sum(f.actual)/sum(f.planned), 4) AS overrun_ratio, "
        "count() AS n, uniqExact(p.project_id) AS n_titles, "
        "round(stddevPop(f.actual/nullIf(f.planned,0)), 4) AS spend_std "
        "FROM genesis_institutional.financial_ledger f "
        "JOIN genesis_institutional.projects p ON p.project_id = f.project_id "
        "JOIN genesis_institutional.eras e ON e.era_id = p.era_id "
        "WHERE p.project_type = 'feature' "
        "GROUP BY p.budget_class, e.era_id, e.name ORDER BY e.era_id, budget_class LIMIT 200"
    ),
    # the century's U-shape: factory-era discipline is the minimum, the 70s and
    # the COVID era the peaks — era-qualified truth, not a single number
    "overrun_by_era": (
        "SELECT e.name AS era, p.budget_class AS budget_class, "
        "round(sum(f.actual)/sum(f.planned), 4) AS overrun_ratio, "
        "count() AS n, uniqExact(p.project_id) AS n_titles, "
        "round(stddevPop(f.actual/nullIf(f.planned,0)), 4) AS spend_std "
        "FROM genesis_institutional.financial_ledger f "
        "JOIN genesis_institutional.projects p ON p.project_id = f.project_id "
        "JOIN genesis_institutional.eras e ON e.era_id = p.era_id "
        "GROUP BY e.era_id, e.name, p.budget_class ORDER BY e.era_id, budget_class LIMIT 200"
    ),
    "sequel_opening_premium": (
        "SELECT p.is_sequel AS is_sequel, e.name AS era, round(avg(t.open_ratio), 4) AS open_over_budget, "
        "count() AS n_titles, round(stddevPop(t.open_ratio), 4) AS ratio_std "
        "FROM (SELECT a.project_id, sum(a.revenue)/any(p2.budget_usd) AS open_ratio "
        "      FROM genesis_institutional.audience_performance a "
        "      JOIN genesis_institutional.projects p2 ON p2.project_id = a.project_id "
        "      WHERE p2.released_at IS NOT NULL AND a.at < p2.released_at + 30 "
        "      AND a.channel IN ('theatrical', 'pvod') "
        "      AND p2.released_at >= '1995-01-01' AND p2.project_type = 'feature' "
        "      AND p2.franchise_id != '' "
        "      GROUP BY a.project_id) t "
        "JOIN genesis_institutional.projects p ON p.project_id = t.project_id "
        "JOIN genesis_institutional.eras e ON e.era_id = p.era_id "
        "GROUP BY p.is_sequel, e.era_id, e.name ORDER BY is_sequel, e.era_id LIMIT 200"
    ),
    "sequel_franchise_decay": (
        "SELECT p.is_sequel AS is_sequel, e.name AS era, round(avg(t.tail_share), 4) AS tail_share, "
        "count() AS n_titles, round(stddevPop(t.tail_share), 4) AS share_std "
        "FROM (SELECT a.project_id, sumIf(a.revenue, a.at >= p2.released_at + 365)/sum(a.revenue) AS tail_share "
        "      FROM genesis_institutional.audience_performance a "
        "      JOIN genesis_institutional.projects p2 ON p2.project_id = a.project_id "
        "      WHERE p2.franchise != '' AND p2.released_at IS NOT NULL "
        "      AND p2.released_at >= '1995-01-01' AND p2.released_at < '2023-08-01' "
        "      AND p2.project_type = 'feature' "
        "      GROUP BY a.project_id) t "
        "JOIN genesis_institutional.projects p ON p.project_id = t.project_id "
        "JOIN genesis_institutional.eras e ON e.era_id = p.era_id "
        "GROUP BY p.is_sequel, e.era_id, e.name ORDER BY is_sequel, e.era_id LIMIT 200"
    ),
    # the regime flip: summer is a modern invention (1975-06-20, to the day)
    "release_window_seasonality": (
        "SELECT p.release_window AS release_window, round(avg(a.revenue), 2) AS daily_revenue, "
        "count() AS n, uniqExact(p.project_id) AS n_titles, round(stddevPop(a.revenue), 2) AS revenue_std, "
        "if(p.released_at < '1975-06-20', 'pre_blockbuster', 'blockbuster_era') AS era "
        "FROM genesis_institutional.audience_performance a "
        "JOIN genesis_institutional.projects p ON p.project_id = a.project_id "
        "WHERE a.at < p.released_at + 90 AND a.channel IN ('theatrical', 'theatrical_reissue') "
        "GROUP BY p.release_window, era ORDER BY p.release_window, era LIMIT 200"
    ),
    "overrun_schedule_coupling": (
        "SELECT p.budget_class AS budget_class, e.name AS era, round(avg(s.slip_days), 2) AS avg_slip_days, "
        "count() AS n_titles, round(stddevPop(s.slip_days), 2) AS slip_std "
        "FROM (SELECT project_id, sum(value) AS slip_days "
        "      FROM genesis_institutional.production_events WHERE event_type = 'schedule_slip' "
        "      GROUP BY project_id) s "
        "JOIN genesis_institutional.projects p ON p.project_id = s.project_id "
        "JOIN genesis_institutional.eras e ON e.era_id = p.era_id "
        "GROUP BY p.budget_class, e.era_id, e.name ORDER BY e.era_id, avg_slip_days DESC LIMIT 200"
    ),
    # money is nominal — the cohort band deflates through cpi_annual so a 1989
    # picture and a 2019 picture qualify on the same real-dollar terms
    "scenario_cohort_windows": (
        "SELECT p.release_window AS release_window, p.title AS title, "
        "round(sum(a.revenue)/any(p.budget_usd), 4) AS rev_multiple "
        "FROM genesis_institutional.audience_performance a "
        "JOIN genesis_institutional.projects p ON p.project_id = a.project_id "
        "JOIN genesis_institutional.cpi_annual c ON c.year = toYear(p.released_at) "
        "WHERE p.budget_usd * c.mult_to_2026 BETWEEN 20000000 AND 250000000 "
        "AND p.released_at >= '1985-01-01' AND p.project_type = 'feature' "
        "AND p.released_at IS NOT NULL "
        "GROUP BY p.release_window, p.title ORDER BY p.release_window, rev_multiple "
        "LIMIT 50 BY p.release_window LIMIT 200"
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
                                               "n_col": "n", "titles_col": "n_titles",
                                               "std_col": "spend_std", "split_col": "era"}}]},
                {"domain": "audience_distribution",
                 "statement": "Sequels outperform originals — or underperform once decay is controlled: the corpus decides.",
                 "rationale": "Sequel economics drive the premium-vs-fatigue tension in every greenlight.",
                 "intents": [{"purpose": "canonical:sequel_opening_premium",
                              "verification": {"metric_col": "open_over_budget", "group_col": "is_sequel",
                                               "n_col": "n_titles", "titles_col": "n_titles",
                                               "std_col": "ratio_std", "split_col": "era"}},
                             {"purpose": "canonical:sequel_franchise_decay",
                              "verification": {"metric_col": "tail_share", "group_col": "is_sequel",
                                               "n_col": "n_titles", "titles_col": "n_titles",
                                               "std_col": "share_std", "split_col": "era"}}]},
                {"domain": "audience_distribution",
                 "statement": "Release window materially shifts early revenue (Q2/Q4 premium).",
                 "rationale": "Window choice is a controllable lever in the proposal.",
                 "intents": [{"purpose": "canonical:release_window_seasonality",
                              "verification": {"metric_col": "daily_revenue", "group_col": "release_window",
                                               "n_col": "n", "titles_col": "n_titles",
                                               "std_col": "revenue_std", "split_col": "era"}}]},
                {"domain": "operational_history",
                 "statement": "Schedule slips concentrate in larger productions, coupling delivery risk to budget class.",
                 "rationale": "Slip history calibrates the operational risk of the proposal.",
                 "intents": [{"purpose": "canonical:overrun_schedule_coupling",
                              "verification": {"metric_col": "avg_slip_days", "group_col": "budget_class",
                                               "n_col": "n_titles", "titles_col": "n_titles",
                                               "std_col": "slip_std", "split_col": "era"}}]},
                {"domain": "financial_performance",
                 "statement": "Overrun discipline is era-dependent: the studio-system factory was the century's minimum, and the 1970s and 2020s its peaks.",
                 "rationale": "A century of ledger history says when the studio was disciplined — and what conditions broke it.",
                 "intents": [{"purpose": "canonical:overrun_by_era",
                              "verification": {"metric_col": "overrun_ratio", "group_col": "era",
                                               "n_col": "n", "titles_col": "n_titles",
                                               "std_col": "spend_std", "split_col": "budget_class"}}]},
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
        regime = [f for f in payload.get("findings", []) if f.get("state") == "REGIME"]
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
        if regime:
            interpretations.append(
                {"label": "Era-bounded truth", "stance": "context",
                 "narrative": f"This holds within {regime[0].get('era_range') or 'a bounded era range'} "
                              "and not across the century — treat it as a regime of the current "
                              "industry structure, not a law of the studio.",
                 "cited_query_ids": [], "cited_finding_ids": [regime[0].get("id", "")]})
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
                        if contested else [])
                       + (["At least one finding is REGIME: true within its era range only — "
                           "check its bounds before acting on it."] if coverage.get("REGIME", 0) else [])
                       + ["Statistics summarize the studio's own corpus, not the market."],
        }


def get_cognition(settings: Settings) -> Cognition:
    if settings.gemini_live:
        return GeminiCognition(settings)
    return MockCognition()
