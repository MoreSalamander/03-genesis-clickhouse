"""Record canonical query results from the live seeded corpus into the mock
fixtures (app/tools/clickhouse_mcp/fixtures/recorded_results.json).

Mock mode then replays REAL recorded numbers — deterministic because the corpus
itself is deterministically seeded. Re-run after changing seed/generate.py.

Usage: .venv/bin/python -m seed.record_fixtures   (needs the live local stack)
"""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path

# distinctive substring of each canonical SQL → fixture match key
MATCHES = {
    "cohort_overrun_by_class": "sum(f.actual)/sum(f.planned)",
    "sequel_opening_premium": "a.at < p2.released_at + 30",
    "sequel_franchise_decay": "p2.franchise != ''",
    "release_window_seasonality": "if(toYear(a.at) >= 2021",
    "overrun_schedule_coupling": "event_type = 'schedule_slip'",
    "scenario_cohort_windows": "p.budget_usd BETWEEN 10000000 AND 120000000",
    "corpus_summary": "GROUP BY status ORDER BY n DESC",
}


def main() -> int:
    sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    from app.config import Settings
    from app.tools.clickhouse_mcp.client import LiveClickHouseMCP
    from app.tools.google.gemini import CANONICAL_SQL

    settings = Settings()
    client = LiveClickHouseMCP(settings)

    extra_sql = {
        "corpus_summary": (
            "SELECT status, count() AS n, round(sum(budget_usd)/1e6, 1) AS total_budget_m "
            "FROM genesis_institutional.projects GROUP BY status ORDER BY n DESC"
        ),
    }
    queries = []
    for key, sql in {**CANONICAL_SQL, **extra_sql}.items():
        result = client.run_query(sql)
        queries.append({
            "key": key,
            "match": MATCHES[key],
            "columns": result.columns,
            "rows": result.rows,
        })
        print(f"[fixtures] {key}: {result.row_count} rows")

    tables = [t for t in client.list_tables() if not str(t.get("name", "")).startswith(".inner")]
    slim_tables = []
    for table in tables:
        slim_tables.append({
            "name": table.get("name"),
            "comment": table.get("comment", ""),
            "total_rows": table.get("total_rows") or table.get("row_count"),
            "columns": [
                {"name": c.get("name"), "column_type": c.get("column_type") or c.get("type")}
                for c in (table.get("columns") or [])
            ],
        })

    out = Path(__file__).resolve().parent.parent / "app" / "tools" / "clickhouse_mcp" / "fixtures"
    out.mkdir(parents=True, exist_ok=True)
    path = out / "recorded_results.json"
    path.write_text(json.dumps({"queries": queries, "tables": slim_tables},
                               ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"[fixtures] wrote {path} ({len(queries)} queries, {len(slim_tables)} tables)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
