"""Statistical Verification Agent — verification states computed IN CODE from
the numbers ClickHouse returned (rule-derived, never model-asserted).

Recalibrated for the century corpus (2026-08-19). The rules a 62-project corpus
tolerated broke at 104M rows: an n that counts fact rows clears any bar, and an
effect divided by the standard error grows with √n — scale masquerading as
significance. The rules now:

  VERIFIED     powered on the COMPARED UNIT (titles when a titles-grain count is
               present), effect size exceeds the dispersion threshold (Cohen's-d
               shaped, scale-free), AND the direction agrees in >= min_stable_eras
               eras with no era disagreeing — a law of the studio, not of a decade
  REGIME       powered and clear, but true only within an era range: some era
               disagrees, or the data itself spans fewer than min_stable_eras eras
               (a streaming-era question IS era-bounded) — carried with its range
  WEAK         signal present but under-powered, within noise, or era stability
               unprovable because the result carries no era split
  CONTESTED    two intents on the same hypothesis disagree in direction — preserved
  INSUFFICIENT the result cannot support the computation

The verifier is a pure function over rows already fetched — it can never ask a
follow-up question, so era stability exists only if the SQL brought an era
column home (the prompts require exactly that).
"""
from __future__ import annotations

import math
from typing import Any, NamedTuple

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


TITLE_GRAIN_NAMES = ("n_titles", "titles", "project_count", "num_projects", "n_projects",
                     "uniq_titles", "title_count")
SPLIT_NAMES = ("era", "era_name", "eras", "decade", "regime", "period")


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

    if missing("titles_col"):
        resolved["titles_col"] = next(
            (c for c in numeric_cols if c.lower() in TITLE_GRAIN_NAMES), None)
    if missing("n_col"):
        resolved["n_col"] = next((c for c in numeric_cols
                                  if c.lower() in ("n", "count", "cnt", "samples", "titles",
                                                   "num_projects", "project_count", "n_titles")
                                  or c.lower().startswith(("n_", "count", "num_"))), None)
    if missing("std_col"):
        resolved["std_col"] = next((c for c in numeric_cols if "std" in c.lower()), None)
    if missing("split_col"):
        # era stability is only computable when the result carries the split —
        # recognize the corpus's own era vocabulary even when the planner forgot
        resolved["split_col"] = next(
            (c for c in categorical_cols if c.lower() in SPLIT_NAMES), None)
    if missing("group_col"):
        candidates = [c for c in categorical_cols if c != resolved.get("split_col")]
        resolved["group_col"] = candidates[0] if candidates else None
    if missing("metric_col"):
        reserved = {resolved.get("n_col"), resolved.get("std_col"), resolved.get("titles_col")}
        resolved["metric_col"] = next((c for c in numeric_cols if c not in reserved), None)
    return resolved


class EraAgreement(NamedTuple):
    n_data: int          # eras where BOTH compared groups have rows
    n_agree: int         # of those, eras whose effect sign matches the overall sign
    disagree: bool       # at least one era's sign opposes the overall sign
    span: str            # human-readable range of agreeing eras, result order
    per_era: dict        # {era: +1 agree | -1 disagree} in result order


def _era_agreement(metric: list[float | None], groups: list[Any], counts: list[float],
                   split: list[Any], g_a: str, g_b: str, overall_sign: float) -> EraAgreement:
    """Per-era agreement of the two-group effect, n-weighted within each era."""
    eras: dict[str, dict[str, list[tuple[float, float]]]] = {}
    order: list[str] = []
    for i, era in enumerate(split):
        if metric[i] is None:
            continue
        e = str(era)
        if e not in eras:
            order.append(e)
        weight = counts[i] if i < len(counts) and counts[i] else 1.0
        eras.setdefault(e, {}).setdefault(str(groups[i]), []).append((metric[i], weight))

    n_data = n_agree = 0
    disagree = False
    agreeing: list[str] = []
    per_era: dict = {}
    for era in order:
        era_groups = eras[era]
        if g_a not in era_groups or g_b not in era_groups:
            continue
        n_data += 1

        def wmean(pairs: list[tuple[float, float]]) -> float:
            total = sum(w for _, w in pairs) or 1.0
            return sum(v * w for v, w in pairs) / total

        diff = wmean(era_groups[g_a]) - wmean(era_groups[g_b])
        if diff == 0:
            continue
        sign = 1.0 if diff > 0 else -1.0
        if overall_sign and sign == overall_sign:
            n_agree += 1
            agreeing.append(era)
            per_era[era] = 1
        elif overall_sign:
            disagree = True
            per_era[era] = -1
    # numeric split values (a model splitting on era_id) still read as eras:
    # sort them and say "era" — names pass through in result order
    if agreeing and all(a.replace(".", "", 1).isdigit() for a in agreeing):
        agreeing = [f"era {int(float(a))}" for a in
                    sorted(agreeing, key=lambda a: float(a))]
    span = (agreeing[0] if len(agreeing) == 1
            else f"{agreeing[0]} → {agreeing[-1]}" if agreeing else "")
    return EraAgreement(n_data, n_agree, disagree, span, per_era)


def era_detail(query: AnalyticalQuery, rows: list[list[Any]], spec: dict) -> EraAgreement:
    """The full era-agreement picture for a query's primary two-group effect."""
    spec = _infer_spec(query, rows, spec)
    metric = [_to_float(v) for v in _column(query, rows, spec.get("metric_col"))]
    groups = _column(query, rows, spec.get("group_col"))
    counts = [_to_float(v) or 0 for v in _column(query, rows, spec.get("n_col"))]
    split = _column(query, rows, spec.get("split_col"))
    if not metric or not split:
        return EraAgreement(0, 0, False, "", {})
    per_group: dict[str, float] = {}
    weights: dict[str, float] = {}
    for i, group in enumerate(groups if groups else ["all"] * len(metric)):
        if metric[i] is None:
            continue
        g = str(group)
        w = counts[i] if i < len(counts) and counts[i] else 1.0
        per_group[g] = per_group.get(g, 0.0) + metric[i] * w
        weights[g] = weights.get(g, 0.0) + w
    if len(per_group) < 2:
        return EraAgreement(0, 0, False, "", {})
    ranked = sorted(weights.items(), key=lambda kv: -kv[1])[:2]
    g_a, g_b = ranked[0][0], ranked[1][0]
    effect = per_group[g_a] / weights[g_a] - per_group[g_b] / weights[g_b]
    sign = 1.0 if effect > 0 else (-1.0 if effect < 0 else 0.0)
    return _era_agreement(metric, groups, counts, split, g_a, g_b, sign)


def analyze_query(query: AnalyticalQuery, rows: list[list[Any]], spec: dict) -> dict[str, float]:
    """Two-group effect statistics from an aggregate result table.

    effect_over_noise is Cohen's-d shaped: |mean_a − mean_b| / pooled dispersion.
    It is deliberately scale-FREE — 91 million rows cannot buy significance, only
    a genuinely large and consistent effect can.
    """
    stats: dict[str, float] = {}
    spec = _infer_spec(query, rows, spec)
    metric = [_to_float(v) for v in _column(query, rows, spec.get("metric_col"))]
    groups = _column(query, rows, spec.get("group_col"))
    counts = [_to_float(v) or 0 for v in _column(query, rows, spec.get("n_col"))]
    titles = [_to_float(v) or 0 for v in _column(query, rows, spec.get("titles_col"))]
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
        acc = per_group.setdefault(g, {"sum": 0.0, "n": 0.0, "t": 0.0,
                                       "wsum": 0.0, "std": 0.0, "k": 0})
        weight = counts[i] if i < len(counts) and counts[i] else 1.0
        acc["sum"] += value * weight
        acc["wsum"] += weight
        acc["n"] += counts[i] if i < len(counts) else 0.0
        acc["t"] += titles[i] if i < len(titles) else 0.0
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
        # pooled dispersion, never the standard error: dividing by SE let n buy
        # significance (the old demo's "effect/noise 231" was row count, not truth)
        pooled = math.sqrt((std_a ** 2 + std_b ** 2) / 2) or 1e-9
        stats.update({
            "mean_a": round(mean_a, 6), "mean_b": round(mean_b, 6),
            "n_a": n_a, "n_b": n_b,
            "effect": round(effect, 6), "dispersion": round(pooled, 6),
            "effect_over_noise": round(abs(effect) / pooled, 3),
        })
        if acc_a["t"] or acc_b["t"]:
            stats["titles_a"] = acc_a["t"]
            stats["titles_b"] = acc_b["t"]
        # direction across the full ordering (max vs min group) for narrative use
        ordered = sorted(means.items(), key=lambda kv: kv[1])
        stats["spread"] = round(ordered[-1][1] - ordered[0][1], 6)
        stats["direction"] = 1.0 if effect > 0 else (-1.0 if effect < 0 else 0.0)

        if split:
            era = _era_agreement(metric, groups, counts, split, g_a, g_b,
                                 stats["direction"])
            stats["n_eras_data"] = float(era.n_data)
            stats["n_eras_agree"] = float(era.n_agree)
            stats["stable_across_splits"] = 0.0 if era.disagree else 1.0
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
        stats["threshold"] = self.policy.effect_over_noise   # the gauge is self-describing

        # power is judged on the COMPARED UNIT: titles when the SQL counted them,
        # row-grain n as an annotated fallback (the scale-free effect and the era
        # gate are what actually close the 91M-row loophole)
        title_grain = "titles_a" in stats
        if title_grain:
            unit_min = min(stats.get("titles_a", 0.0), stats.get("titles_b", 0.0))
            unit_note = f"titles_min={unit_min:.0f}"
        else:
            unit_min = min(stats.get("n_a", 0.0), stats.get("n_b", 0.0))
            unit_note = f"n_min={unit_min:.0f} (power unit approximate: row-grain n)"
        powered = unit_min >= self.policy.min_cohort_n
        signal = stats.get("effect_over_noise", 0.0) > self.policy.effect_over_noise
        split_present = stats.get("n_eras_data", 0.0) > 0
        n_agree = int(stats.get("n_eras_agree", 0.0))
        disagree = stats.get("stable_across_splits", 1.0) < 1.0
        era_range: str | None = None
        detail = (era_detail(primary, rows_of.get(primary.id, primary.rows),
                             specs.get(primary.id, {}))
                  if split_present else EraAgreement(0, 0, False, "", {}))

        if powered and signal and split_present:
            if not disagree and n_agree >= self.policy.min_stable_eras:
                state = VerificationState.VERIFIED
                basis = (f"{unit_note} >= {self.policy.min_cohort_n}, "
                         f"effect size {stats.get('effect_over_noise')} > {self.policy.effect_over_noise}, "
                         f"direction holds in all {n_agree} eras with data — institutional truth")
            elif n_agree >= 1:
                state = VerificationState.REGIME
                era_range = detail.span
                bound = ("an era disagrees" if disagree
                         else f"the data spans only {int(stats.get('n_eras_data', 0))} era(s)")
                basis = (f"{unit_note} >= {self.policy.min_cohort_n}, "
                         f"effect size {stats.get('effect_over_noise')} > {self.policy.effect_over_noise}, "
                         f"but {bound} — true within {era_range or 'a bounded range'}, "
                         f"not across the century")
            else:
                state = VerificationState.WEAK
                basis = "signal present but direction unstable in every era"
        elif powered and signal and not split_present:
            state = VerificationState.WEAK
            basis = ("signal present but era stability unproven — "
                     "the result carries no era split")
        elif signal or stats.get("effect"):
            state = VerificationState.WEAK
            reasons = []
            if not powered:
                reasons.append(f"{unit_note} < {self.policy.min_cohort_n}")
            if not signal:
                reasons.append(f"effect size {stats.get('effect_over_noise')} <= {self.policy.effect_over_noise}")
            basis = "signal present but under-powered: " + ", ".join(reasons) if reasons \
                else "signal within noise"
        else:
            state = VerificationState.INSUFFICIENT
            basis = "no measurable effect in the result"

        return Finding(
            hypothesis_id=hypothesis.id, domain=hypothesis.domain,
            statement=hypothesis.statement, state=state, basis=basis,
            era_range=era_range,
            era_agreement={str(k): int(v) for k, v in detail.per_era.items()},
            stats={k: v for k, v in stats.items() if isinstance(v, (int, float))},
            evidence_query_ids=[q.id for q in analyzed],
        )
