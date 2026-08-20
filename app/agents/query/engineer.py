"""Query Engineer — schema-grounded SQL via Gemini, SELECT-only enforced in code,
bounded repair (locked §2.3: read permission only; ≤2 repairs, re-grounded).

Schema grounding comes from `list_tables` at runtime (live introspection, never
hardcoded prompts — locked §2.5).
"""
from __future__ import annotations

import json
from typing import Any

from app.governance.sql_guard import SQLRejected, ensure_select_only
from app.models.institutional import AnalyticalQuery
from app.tools.clickhouse_mcp.client import QueryResult, QuerySemanticError

MAX_REPAIRS = 2


class QueryEngineer:
    def __init__(self, cognition, clickhouse):
        self._cognition = cognition
        self._clickhouse = clickhouse
        self._schema_cache: list[dict] | None = None

    def schema_context(self) -> list[dict]:
        """Compact table schemas for prompt grounding (MV internals filtered)."""
        if self._schema_cache is not None:
            return self._schema_cache
        tables = []
        for table in self._clickhouse.list_tables():
            name = str(table.get("name", ""))
            if name.startswith(".inner") or name.endswith("_mv"):
                continue                      # MV wrappers duplicate their target tables
            columns = table.get("columns") or []
            col_desc = [
                # column COMMENTs carry the corpus semantics (nominal money, era
                # gates, NULL-outside-streaming) straight into the SQL prompts
                {"name": c.get("name"), "type": c.get("column_type") or c.get("type"),
                 **({"comment": c["comment"]} if c.get("comment") else {})}
                for c in columns
            ] if isinstance(columns, list) else []
            tables.append({
                "table": f"genesis_institutional.{name}",
                "comment": table.get("comment", ""),
                "rows": table.get("total_rows") or table.get("row_count"),
                "columns": col_desc or table.get("create_table_query", ""),
            })
        self._schema_cache = tables
        return tables

    def execute_intent(self, hypothesis_id: str, domain: str, intent: dict[str, Any]) -> AnalyticalQuery:
        """Generate → guard → run → repair (bounded) → evidence object."""
        purpose = intent.get("purpose", "")
        generated = self._cognition.generate_json(
            "sql_generation",
            {"intent": intent, "schemas": self.schema_context()},
        )
        sql = str(generated.get("sql", ""))
        record = AnalyticalQuery(hypothesis_id=hypothesis_id, domain=domain, purpose=purpose)
        repairs = 0
        while True:
            try:
                cleaned = ensure_select_only(sql)
                result: QueryResult = self._clickhouse.run_query(cleaned, tag=record.id)
                record.sql = cleaned
                record.columns = result.columns
                record.rows = result.rows[:200]                # doc-store sample; full → MinIO
                record.row_count = result.row_count
                record.elapsed_ms = round(result.elapsed_ms, 1)
                record.repairs = repairs
                record.error = None
                record._full_rows = result.rows  # type: ignore[attr-defined]  # transient, for stats/snapshots
                try:
                    # partition pruning, on the record — one line of proof per query
                    plan = self._clickhouse.run_query(f"EXPLAIN indexes = 1 {cleaned}")
                    record.explain = "\n".join(str(r[0]) for r in plan.rows)[:4000]
                except Exception:
                    record.explain = ""
                return record
            except (QuerySemanticError, SQLRejected) as err:
                if repairs >= MAX_REPAIRS:
                    record.sql = sql
                    record.repairs = repairs
                    record.error = f"unrepairable after {repairs} attempts: {err}"
                    return record
                repairs += 1
                repaired = self._cognition.generate_json(
                    "sql_repair",
                    {"intent": intent, "sql": sql, "error": str(err)[:600],
                     "schemas": self.schema_context()},
                )
                new_sql = str(repaired.get("sql", ""))
                if not new_sql.strip() or new_sql.strip() == sql.strip():
                    record.sql = sql
                    record.repairs = repairs
                    record.error = f"repair produced no change: {err}"
                    return record
                sql = new_sql


def stats_payload(query: AnalyticalQuery) -> dict:
    """Serializable evidence view for prompts (kept small)."""
    return {
        "query_id": query.id,
        "purpose": query.purpose,
        "sql": query.sql,
        "columns": query.columns,
        "rows": query.rows[:12],
        "row_count": query.row_count,
        "error": query.error,
        "computed_stats": query.computed_stats,
    }


def full_rows(query: AnalyticalQuery) -> list[list[Any]]:
    return getattr(query, "_full_rows", None) or query.rows


def snapshot_document(query: AnalyticalQuery) -> bytes:
    return json.dumps(
        {"query_id": query.id, "hypothesis_id": query.hypothesis_id, "purpose": query.purpose,
         "sql": query.sql, "columns": query.columns, "rows": full_rows(query),
         "row_count": query.row_count, "elapsed_ms": query.elapsed_ms, "at": query.at},
        ensure_ascii=False, default=str,
    ).encode()
