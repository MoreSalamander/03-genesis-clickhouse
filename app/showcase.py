"""The showcase queries — the deep dive's §1.2 capabilities, on camera.

Seven queries, each exercising a named ClickHouse capability the investigation
loop's plain aggregates never touch, each answering a real institutional
question over the century corpus. They run through the same read-only MCP path
as everything else (GET /api/showcase) and their SQL is the exhibit: window
functions, windowFunnel, quantile families, array combinators, ASOF JOIN,
argMax, and a range-dictionary lookup.
"""
from __future__ import annotations

DB = "genesis_institutional"

SHOWCASE: dict[str, dict[str, str]] = {
    "cash_curves": {
        "feature": "window functions",
        "story": "Cumulative spend against plan, month by production month, era by era — "
                 "WHERE the century's overruns happen inside a production, not just that they do.",
        "sql": f"""
SELECT era, month_index, round(avg(cum_actual / cum_planned), 4) AS cumulative_overrun,
       uniqExact(project_id) AS n_titles
FROM (
    SELECT e.name AS era, f.project_id AS project_id,
           row_number() OVER w AS month_index,
           sum(f.actual)  OVER w AS cum_actual,
           sum(f.planned) OVER w AS cum_planned
    FROM {DB}.financial_ledger f
    JOIN {DB}.projects p ON p.project_id = f.project_id
    JOIN {DB}.eras e ON e.era_id = p.era_id
    WHERE p.project_type = 'feature'
    WINDOW w AS (PARTITION BY f.project_id ORDER BY f.at)
)
GROUP BY era, month_index
HAVING month_index <= 18
ORDER BY era, month_index
LIMIT 200""",
    },
    "collapsing_window": {
        "feature": "windowFunnel",
        "story": "The theatrical-to-home window, collapsing across a century: the share of "
                 "features whose home release followed theatrical within a year — and within 45 "
                 "days, which was unthinkable before 2020.",
        "sql": f"""
SELECT e.name AS era, count() AS n_titles,
       round(countIf(lvl_year >= 2) / count(), 3) AS home_within_year,
       round(countIf(lvl_45d >= 2) / count(), 3) AS home_within_45_days
FROM (
    SELECT d.project_id,
           windowFunnel(365)(toUInt32(toInt64(d.at) + 25567),
                             d.event_type = 'theatrical_open',
                             d.event_type IN ('video_release', 'window_open')) AS lvl_year,
           windowFunnel(45)(toUInt32(toInt64(d.at) + 25567),
                            d.event_type = 'theatrical_open',
                            d.event_type IN ('video_release', 'window_open')) AS lvl_45d
    FROM {DB}.distribution_events d
    GROUP BY d.project_id
) t
JOIN {DB}.projects p ON p.project_id = t.project_id
JOIN {DB}.eras e ON e.era_id = p.era_id
WHERE p.project_type = 'feature'
GROUP BY e.era_id, e.name
ORDER BY e.era_id
LIMIT 200""",
    },
    "revenue_quantiles": {
        "feature": "quantile families",
        "story": "Not the average — the whole distribution: revenue multiples at five "
                 "quantiles per era, computed over the full corpus in one pass.",
        "sql": f"""
SELECT e.name AS era,
       arrayMap(x -> round(x, 2), quantiles(0.1, 0.25, 0.5, 0.75, 0.9)(t.mult)) AS rev_multiple_p10_to_p90,
       count() AS n_titles
FROM (
    SELECT a.project_id, sum(a.revenue) / any(p.budget_usd) AS mult
    FROM {DB}.audience_performance a
    JOIN {DB}.projects p ON p.project_id = a.project_id
    WHERE p.project_type = 'feature' AND p.released_at IS NOT NULL
    GROUP BY a.project_id
) t
JOIN {DB}.projects p2 ON p2.project_id = t.project_id
JOIN {DB}.eras e ON e.era_id = p2.era_id
GROUP BY e.era_id, e.name
ORDER BY e.era_id
LIMIT 200""",
    },
    "franchise_fatigue_curves": {
        "feature": "array combinators",
        "story": "Every franchise's revenue curve as an array — sorted, normalized to its "
                 "first entry, and averaged element-wise per cycle type. The monster cycle's "
                 "fatigue shape, derived live instead of asserted.",
        "sql": f"""
SELECT fr.cycle_type AS cycle_type, count() AS n_franchises,
       arrayMap(x -> round(x, 3), avgForEach(arrayResize(curve, 3))) AS avg_multiple_vs_entry1
FROM (
    SELECT franchise_id,
           arrayMap(t -> t.2 / (arraySort(x -> x.1, groupArray((entry_number, mult)))[1]).2,
                    arraySort(x -> x.1, groupArray((entry_number, mult)))) AS curve
    FROM (
        SELECT p.franchise_id AS franchise_id, p.entry_number AS entry_number,
               sum(a.revenue) / any(p.budget_usd) AS mult
        FROM {DB}.audience_performance a
        JOIN {DB}.projects p ON p.project_id = a.project_id
        WHERE p.franchise_id != '' AND p.entry_number > 0 AND p.released_at IS NOT NULL
        GROUP BY p.franchise_id, p.entry_number
    )
    GROUP BY franchise_id
    HAVING length(curve) >= 3
) c
JOIN {DB}.franchises fr ON fr.franchise_id = c.franchise_id
GROUP BY cycle_type
ORDER BY cycle_type
LIMIT 200""",
    },
    "shock_attribution": {
        "feature": "ASOF JOIN",
        "story": "Every feature joined to the nearest shock that preceded it — was the weak "
                 "opening the picture, or the weather? The 1918 flu, the Depression, and COVID "
                 "cohorts answer together.",
        "sql": f"""
SELECT s.name AS nearest_preceding_shock, count() AS n_titles,
       round(avg(t.open_rev / t.budget), 3) AS opening_over_budget
FROM (
    SELECT p.project_id, 1 AS k, p.released_at AS released_at,
           any(p.budget_usd) AS budget,
           sumIf(a.revenue, a.at < p.released_at + 90) AS open_rev
    FROM {DB}.audience_performance a
    JOIN {DB}.projects p ON p.project_id = a.project_id
    WHERE p.project_type = 'feature' AND p.released_at IS NOT NULL
      AND a.channel IN ('theatrical', 'theatrical_reissue')
    GROUP BY p.project_id, p.released_at
) t
ASOF JOIN (
    SELECT 1 AS k, name, start_date FROM {DB}.shock_calendar
) s ON t.k = s.k AND t.released_at >= s.start_date
GROUP BY s.name
ORDER BY opening_over_budget ASC
LIMIT 200""",
    },
    "superlatives": {
        "feature": "argMax / argMin",
        "story": "The record book in one aggregate pass: every superlative carries its "
                 "holder, and on this corpus the holders are the story titles.",
        "sql": f"""
SELECT
    argMax(concat(p.title, ' (', toString(toYear(p.released_at)), ')'),
           p.shoot_days_actual - p.shoot_days_planned) AS longest_shoot_overrun,
    max(p.shoot_days_actual - p.shoot_days_planned) AS overrun_days,
    argMax(concat(p.title, ' (', toString(toYear(p.released_at)), ')'),
           p.budget_usd * c.mult_to_2026) AS biggest_budget_real_dollars,
    round(max(p.budget_usd * c.mult_to_2026) / 1e6) AS budget_2026_m,
    argMin(concat(p.title, ' (', toString(toYear(p.released_at)), ')'),
           p.budget_usd * c.mult_to_2026) AS smallest_budget_real_dollars
FROM {DB}.projects p
JOIN {DB}.cpi_annual c ON c.year = toYear(p.greenlit_at)
WHERE p.project_type = 'feature' AND p.released_at IS NOT NULL
LIMIT 200""",
    },
    "era_attribution_dict": {
        "feature": "range dictionary (dictGet)",
        "story": "91 million rows attributed to the era the money was EARNED in — one "
                 "dictionary lookup per row, no join. Silent-era titles are still earning "
                 "in the streaming wars; this is the query that shows it.",
        "sql": f"""
SELECT dictGetString('{DB}.era_dict', 'name', toUInt64(0), toInt64(a.at)) AS era_earned,
       round(sum(a.revenue) / 1e9, 3) AS revenue_earned_b,
       uniqExact(a.project_id) AS titles_earning,
       uniqExactIf(a.project_id, p.era_id <= 2) AS of_them_pre_1935_titles
FROM {DB}.audience_performance a
JOIN {DB}.projects p ON p.project_id = a.project_id
GROUP BY era_earned
ORDER BY revenue_earned_b DESC
LIMIT 200""",
    },
}
