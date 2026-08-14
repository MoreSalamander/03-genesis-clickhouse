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

        rows = full_rows(query)
        try:
            g_idx = query.columns.index(group_col)
            o_idx = query.columns.index(outcome_col)
        except ValueError:
            query.error = f"scenario cohort lacks required columns {group_col}/{outcome_col}"
            return None, query

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
            return None, query

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
        delta = {k: round(projected[k] - baseline[k], 0) for k in ("p10", "p50", "p90")}
        narrative = (
            f"Seeded bootstrap ({N_RUNS} runs) over the comparable cohort: median projected outcome "
            f"moves from {baseline['p50']:,.0f} ({baseline_group}, n={int(baseline['cohort_n'])}) to "
            f"{projected['p50']:,.0f} ({alternative_group}, n={int(projected['cohort_n'])}); "
            f"delta at the median {delta['p50']:+,.0f}."
        )
        sim = SimulationResult(
            scenario=str(frame.get("scenario", "")),
            params={"baseline_group": baseline_group, "alternative_group": alternative_group,
                    "outcome_col": outcome_col, "scale_value": scale},
            baseline=baseline, projected=projected, delta=delta,
            n_runs=N_RUNS, seed=SIM_SEED, narrative=narrative,
            evidence_query_ids=[query.id],
        )
        return sim, query
