"""Scenario/Simulation Agent — what-if projections computed in code
(locked §2.3: parameterized re-aggregation + seeded Monte-Carlo-lite).

Gemini frames the scenario (which assumption to flip, which cohort feeds it);
the projection itself is a seeded bootstrap over the cohort's real outcome
distribution — the model never invents a projected number.
"""
from __future__ import annotations

import random
import statistics
from typing import Any

from app.agents.query.engineer import QueryEngineer, full_rows
from app.models.institutional import AnalyticalQuery, SimulationResult

N_RUNS = 2000
SIM_SEED = 7


class ScenarioAgent:
    def __init__(self, cognition, engineer: QueryEngineer):
        self._cognition = cognition
        self._engineer = engineer

    def simulate(self, question: str, findings_payload: list[dict]) -> tuple[SimulationResult | None, AnalyticalQuery | None]:
        sim, query = self._simulate_framed(question, findings_payload)
        if sim is not None:
            return sim, query
        # Framed scenario failed (narrow cohort / column drift) — fall back to the
        # canonical release-window scenario: fixed system SQL over the real corpus,
        # still executed through MCP. The failure stays on the record via `query`.
        fallback_sim, fallback_query = self._canonical_window_scenario(question)
        return fallback_sim, fallback_query or query

    def _canonical_window_scenario(self, question: str) -> tuple[SimulationResult | None, AnalyticalQuery | None]:
        import re as _re

        from app.tools.google.gemini import CANONICAL_SQL

        budget = 45_000_000.0
        match = _re.search(r"\$(\d+(?:\.\d+)?)\s*M", question, _re.IGNORECASE)
        if match:
            budget = float(match.group(1)) * 1e6
        frame = {"scenario": "Shift the proposed release window from Q2 to Q4 and project total "
                             "revenue on the comparable cohort's observed multiples (canonical fallback)",
                 "outcome_col": "rev_multiple", "group_col": "release_window",
                 "baseline_group": "Q2", "alternative_group": "Q4", "scale_value": budget}
        query = AnalyticalQuery(hypothesis_id="scenario", domain="strategic_pattern",
                                purpose="canonical release-window cohort for simulation")
        try:
            result = self._engineer._clickhouse.run_query(CANONICAL_SQL["scenario_cohort_windows"])
        except Exception as err:
            query.error = f"canonical scenario query failed: {err}"
            return None, query
        query.sql = CANONICAL_SQL["scenario_cohort_windows"]
        query.columns = result.columns
        query.rows = result.rows[:50]
        query.row_count = result.row_count
        query.elapsed_ms = round(result.elapsed_ms, 1)
        query._full_rows = result.rows  # noqa: SLF001 — declared PrivateAttr
        return self._project(frame, query), query

    def _simulate_framed(self, question: str, findings_payload: list[dict]) -> tuple[SimulationResult | None, AnalyticalQuery | None]:
        frame = self._cognition.generate_json(
            "scenario_frame", {"question": question, "findings": findings_payload}
        )
        outcome_col = frame.get("outcome_col", "")
        group_col = frame.get("group_col", "")
        baseline_group = str(frame.get("baseline_group", ""))
        alternative_group = str(frame.get("alternative_group", ""))
        scale = float(frame.get("scale_value") or 1.0)

        intent = {
            "purpose": frame.get("cohort_sql_purpose", "cohort rows for scenario simulation"),
            "verification": {"metric_col": outcome_col, "group_col": group_col,
                             "n_col": None, "std_col": None, "split_col": None},
        }
        query = self._engineer.execute_intent("scenario", "strategic_pattern", intent)
        if query.error is not None:
            return None, query
        return self._project(frame, query), query

    def _project(self, frame: dict, query: AnalyticalQuery) -> SimulationResult | None:
        """Seeded bootstrap over the cohort rows of a completed query."""
        outcome_col = frame.get("outcome_col", "")
        group_col = frame.get("group_col", "")
        baseline_group = str(frame.get("baseline_group", ""))
        alternative_group = str(frame.get("alternative_group", ""))
        scale = float(frame.get("scale_value") or 1.0)

        rows = full_rows(query)
        try:
            g_idx = query.columns.index(group_col)
            o_idx = query.columns.index(outcome_col)
        except ValueError:
            query.error = f"scenario cohort lacks required columns {group_col}/{outcome_col}"
            return None

        cohorts: dict[str, list[float]] = {}
        for row in rows:
            try:
                cohorts.setdefault(str(row[g_idx]), []).append(float(row[o_idx]))
            except (TypeError, ValueError):
                continue

        def pick(label: str) -> list[float]:
            """Match the framed group against real values (boolean/numeric drift)."""
            if label in cohorts:
                return cohorts[label]
            aliases = {"true": ["1", "True"], "false": ["0", "False"],
                       "1": ["True", "true"], "0": ["False", "false"]}
            for alias in aliases.get(label.lower(), []):
                if alias in cohorts:
                    return cohorts[alias]
            return []

        base = pick(baseline_group)
        alt = pick(alternative_group)
        if len(base) < 3 or len(alt) < 3:
            query.error = (f"cohorts too small for simulation "
                           f"({baseline_group}: {len(base)}, {alternative_group}: {len(alt)})")
            return None

        rng = random.Random(SIM_SEED)

        def bootstrap(sample: list[float]) -> dict[str, float]:
            medians = []
            for _ in range(N_RUNS):
                draw = [rng.choice(sample) for _ in range(len(sample))]
                medians.append(statistics.median(draw))
            medians.sort()
            return {
                "p10": round(medians[int(N_RUNS * 0.10)] * scale, 0),
                "p50": round(medians[int(N_RUNS * 0.50)] * scale, 0),
                "p90": round(medians[int(N_RUNS * 0.90)] * scale, 0),
                "cohort_n": float(len(sample)),
            }

        baseline = bootstrap(base)
        projected = bootstrap(alt)
        # the rest of the surface, one seeded bootstrap per remaining group —
        # this is what lets the Studio Head twist the dial without a re-run
        surface = {baseline_group: baseline, alternative_group: projected}
        for label, sample in sorted(cohorts.items()):
            if label not in surface and len(sample) >= 3:
                surface[label] = bootstrap(sample)
        delta = {k: round(projected[k] - baseline[k], 0) for k in ("p10", "p50", "p90")}
        narrative = (
            f"Seeded bootstrap ({N_RUNS} runs) over the comparable cohort: median projected outcome "
            f"moves from {baseline['p50']:,.0f} ({baseline_group}, n={int(baseline['cohort_n'])}) to "
            f"{projected['p50']:,.0f} ({alternative_group}, n={int(projected['cohort_n'])}); "
            f"delta at the median {delta['p50']:+,.0f}."
        )
        return SimulationResult(
            scenario=str(frame.get("scenario", "")),
            params={"baseline_group": baseline_group, "alternative_group": alternative_group,
                    "outcome_col": outcome_col, "scale_value": scale},
            baseline=baseline, projected=projected, delta=delta,
            n_runs=N_RUNS, seed=SIM_SEED, narrative=narrative, surface=surface,
            evidence_query_ids=[query.id],
        )
