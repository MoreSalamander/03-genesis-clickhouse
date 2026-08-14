"""Statistical Verification Agent — verification states computed IN CODE from
the numbers ClickHouse returned (locked §2.3: rule-derived, never model-asserted).

Rules (policy in app/config.py, VerificationPolicy):
  VERIFIED     n >= min_cohort_n, |effect| > effect_over_noise x standard error,
               and the effect direction holds across the split column when present
  WEAK         a signal is present but under-powered (small n or effect within noise)
  CONTESTED    two intents on the same hypothesis disagree in direction — preserved
  INSUFFICIENT the result cannot support the computation (too few rows / no metric)
"""
from __future__ import annotations

import math
from typing import Any

from app.config import VerificationPolicy
from app.models.institutional import AnalyticalQuery, Finding, Hypothesis, VerificationState


def _to_float(value: Any) -> float | None:
    try:
        if value is None:
            return None
        return float(value)
    except (TypeError, ValueError):
        return None


def _column(query: AnalyticalQuery, rows: list[list[Any]], name: str | None) -> list[Any]:
    if not name or name not in query.columns:
        return []
    idx = query.columns.index(name)
    return [row[idx] for row in rows]


def _infer_spec(query: AnalyticalQuery, rows: list[list[Any]], spec: dict) -> dict:
    """Reconcile the planner's verification spec with the columns the SQL actually
    returned. Cognition drifts; the rules must not — when a named column is
    missing, fall back to structural inference over the real result table."""
    cols = query.columns
    if not rows or not cols:
        return spec
    resolved = dict(spec)
    numeric_cols, categorical_cols = [], []
    sample = rows[0]
    for i, name in enumerate(cols):
        if _to_float(sample[i]) is not None and not isinstance(sample[i], bool):
            numeric_cols.append(name)
        else:
            categorical_cols.append(name)

    def missing(key: str) -> bool:
        return not resolved.get(key) or resolved[key] not in cols

    if missing("n_col"):
        resolved["n_col"] = next((c for c in numeric_cols
                                  if c.lower() in ("n", "count", "cnt", "samples", "titles",
                                                   "num_projects", "project_count", "n_titles")
                                  or c.lower().startswith(("n_", "count", "num_"))), None)
    if missing("std_col"):
        resolved["std_col"] = next((c for c in numeric_cols if "std" in c.lower()), None)
    if missing("group_col"):
        resolved["group_col"] = categorical_cols[0] if categorical_cols else None
    if missing("metric_col"):
        reserved = {resolved.get("n_col"), resolved.get("std_col")}
        resolved["metric_col"] = next((c for c in numeric_cols if c not in reserved), None)
    if missing("split_col"):
        resolved["split_col"] = None
    return resolved


def analyze_query(query: AnalyticalQuery, rows: list[list[Any]], spec: dict) -> dict[str, float]:
    """Two-group effect statistics from an aggregate result table."""
    stats: dict[str, float] = {}
    spec = _infer_spec(query, rows, spec)
    metric = [_to_float(v) for v in _column(query, rows, spec.get("metric_col"))]
    groups = _column(query, rows, spec.get("group_col"))
    counts = [_to_float(v) or 0 for v in _column(query, rows, spec.get("n_col"))]
    stds = [_to_float(v) for v in _column(query, rows, spec.get("std_col"))]
    split = _column(query, rows, spec.get("split_col"))

    if not metric or all(v is None for v in metric):
        return stats

    # aggregate per group (a split column may repeat groups across eras)
    per_group: dict[str, dict[str, float]] = {}
    for i, group in enumerate(groups if groups else ["all"] * len(metric)):
        value = metric[i]
        if value is None:
            continue
        g = str(group)
        acc = per_group.setdefault(g, {"sum": 0.0, "n": 0.0, "wsum": 0.0, "std": 0.0, "k": 0})
        weight = counts[i] if i < len(counts) and counts[i] else 1.0
        acc["sum"] += value * weight
        acc["wsum"] += weight
        acc["n"] += counts[i] if i < len(counts) else 0.0
        if i < len(stds) and stds[i] is not None:
            acc["std"] += stds[i]
            acc["k"] += 1

    if not per_group:
        return stats
    means = {g: a["sum"] / a["wsum"] for g, a in per_group.items() if a["wsum"]}
    stats["groups"] = float(len(means))
    stats["n_total"] = float(sum(a["n"] or a["wsum"] for a in per_group.values()))

    if len(means) >= 2:
        # compare the two largest cohorts
        ranked = sorted(per_group.items(), key=lambda kv: -(kv[1]["n"] or kv[1]["wsum"]))[:2]
        (g_a, acc_a), (g_b, acc_b) = ranked
        mean_a, mean_b = means[g_a], means[g_b]
        n_a = max(acc_a["n"] or acc_a["wsum"], 1.0)
        n_b = max(acc_b["n"] or acc_b["wsum"], 1.0)
        std_a = (acc_a["std"] / acc_a["k"]) if acc_a["k"] else abs(mean_a) * 0.5
        std_b = (acc_b["std"] / acc_b["k"]) if acc_b["k"] else abs(mean_b) * 0.5
        effect = mean_a - mean_b
        se = math.sqrt((std_a ** 2) / n_a + (std_b ** 2) / n_b) or 1e-9
        stats.update({
            "mean_a": round(mean_a, 6), "mean_b": round(mean_b, 6),
            "n_a": n_a, "n_b": n_b,
            "effect": round(effect, 6), "std_error": round(se, 6),
            "effect_over_noise": round(abs(effect) / se, 3),
        })
        # direction across the full ordering (max vs min group) for narrative use
        ordered = sorted(means.items(), key=lambda kv: kv[1])
        stats["spread"] = round(ordered[-1][1] - ordered[0][1], 6)
        stats["direction"] = 1.0 if effect > 0 else (-1.0 if effect < 0 else 0.0)

        if split:
            # stability: does the top-vs-bottom group ordering hold within each split?
            eras: dict[str, dict[str, list[float]]] = {}
            for i, era in enumerate(split):
                if metric[i] is None:
                    continue
                eras.setdefault(str(era), {}).setdefault(str(groups[i]), []).append(metric[i])
            signs = set()
            for era_groups in eras.values():
                if g_a in era_groups and g_b in era_groups:
                    diff = (sum(era_groups[g_a]) / len(era_groups[g_a])
                            - sum(era_groups[g_b]) / len(era_groups[g_b]))
                    if diff:
                        signs.add(1.0 if diff > 0 else -1.0)
            stats["stable_across_splits"] = 1.0 if len(signs) <= 1 else 0.0
    return stats


class StatisticalVerifier:
    def __init__(self, policy: VerificationPolicy):
        self.policy = policy

    def verify_hypothesis(self, hypothesis: Hypothesis, queries: list[AnalyticalQuery],
                          rows_of: dict[str, list[list[Any]]], specs: dict[str, dict]) -> Finding:
        usable = [q for q in queries if q.error is None and q.row_count > 0]
        if not usable:
            return Finding(
                hypothesis_id=hypothesis.id, domain=hypothesis.domain,
                statement=f"{hypothesis.statement} — the corpus cannot answer this.",
                state=VerificationState.INSUFFICIENT,
                basis="no usable query results (errors or empty tables)",
                evidence_query_ids=[q.id for q in queries],
            )

        for query in usable:
            spec = specs.get(query.id, {})
            query.computed_stats = analyze_query(query, rows_of.get(query.id, query.rows), spec)

        analyzed = [q for q in usable if q.computed_stats.get("effect") is not None]
        if not analyzed:
            return Finding(
                hypothesis_id=hypothesis.id, domain=hypothesis.domain,
                statement=f"{hypothesis.statement} — results lack comparable groups.",
                state=VerificationState.INSUFFICIENT,
                basis="no two-group comparison could be computed from the result tables",
                evidence_query_ids=[q.id for q in usable],
            )

        # CONTESTED first: two analyses of the same hypothesis disagreeing in direction
        directions = {q.id: q.computed_stats.get("direction", 0.0) for q in analyzed}
        signs = {d for d in directions.values() if d}
        if len(analyzed) >= 2 and len(signs) > 1:
            detail = "; ".join(
                f"{q.purpose or q.id}: effect {q.computed_stats.get('effect')} "
                f"({'+' if q.computed_stats.get('direction', 0) > 0 else '-'})"
                for q in analyzed
            )
            return Finding(
                hypothesis_id=hypothesis.id, domain=hypothesis.domain,
                statement=f"{hypothesis.statement} — the corpus supports BOTH directions depending on slicing.",
                state=VerificationState.CONTESTED,
                basis=f"disagreeing effect directions across analyses ({detail}) — preserved, not resolved",
                stats={"analyses": float(len(analyzed))},
                evidence_query_ids=[q.id for q in analyzed],
            )

        primary = max(analyzed, key=lambda q: q.computed_stats.get("effect_over_noise", 0.0))
        stats = primary.computed_stats
        n_min = min(stats.get("n_a", 0.0), stats.get("n_b", 0.0))
        powered = n_min >= self.policy.min_cohort_n
        signal = stats.get("effect_over_noise", 0.0) > self.policy.effect_over_noise
        stable = stats.get("stable_across_splits", 1.0) >= 1.0

        if powered and signal and stable:
            state = VerificationState.VERIFIED
            basis = (f"n_min={n_min:.0f} >= {self.policy.min_cohort_n}, "
                     f"effect/noise={stats.get('effect_over_noise')} > {self.policy.effect_over_noise}, "
                     f"direction stable across splits")
        elif signal or stats.get("effect"):
            state = VerificationState.WEAK
            reasons = []
            if not powered:
                reasons.append(f"n_min={n_min:.0f} < {self.policy.min_cohort_n}")
            if not signal:
                reasons.append(f"effect/noise={stats.get('effect_over_noise')} <= {self.policy.effect_over_noise}")
            if not stable:
                reasons.append("direction flips across splits")
            basis = "signal present but under-powered: " + ", ".join(reasons)
        else:
            state = VerificationState.INSUFFICIENT
            basis = "no measurable effect in the result"

        return Finding(
            hypothesis_id=hypothesis.id, domain=hypothesis.domain,
            statement=hypothesis.statement, state=state, basis=basis,
            stats={k: v for k, v in stats.items() if isinstance(v, (int, float))},
            evidence_query_ids=[q.id for q in analyzed],
        )
