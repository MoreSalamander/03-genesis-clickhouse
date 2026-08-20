"""ClickHouse MCP integration — the analytical substrate (locked §2.5).

LIVE mode connects to the **official mcp-clickhouse server** over
streamable-HTTP via the MCP Python SDK and calls its verified tools at runtime:
`run_query`, `list_tables`, `list_databases` (tool set verified empirically —
docs/decisions/0001). This is the ClickHouse-track runtime requirement: agents
reach ClickHouse exclusively through this server, as a read-only user.

MOCK mode replays recorded results from the deterministic seeded corpus so the
full investigation loop runs from a clean clone with no keys and no Docker.
Every query passes the in-code SELECT guard first; statistics are computed by
the Statistical Verification agent in Python — cognition never invents a digit.
"""
from __future__ import annotations

import asyncio
import json
import time
from pathlib import Path
from typing import Any

from app.config import Settings
from app import runtime_proof
from app.governance.sql_guard import ensure_select_only


class ClickHouseUnavailable(RuntimeError):
    """MCP server unreachable / tool failure → the investigation is marked
    INCOMPLETE (locked §2.9: numbers are never fabricated)."""


class QueryResult:
    def __init__(self, columns: list[str], rows: list[list[Any]], elapsed_ms: float = 0.0):
        self.columns = columns
        self.rows = rows
        self.elapsed_ms = elapsed_ms

    @property
    def row_count(self) -> int:
        return len(self.rows)

    def column(self, name: str) -> list[Any]:
        if name not in self.columns:
            raise KeyError(f"column '{name}' not in result ({self.columns})")
        idx = self.columns.index(name)
        return [row[idx] for row in self.rows]

    def as_dicts(self) -> list[dict[str, Any]]:
        return [dict(zip(self.columns, row)) for row in self.rows]


# ---------------------------------------------------------------------------
# LIVE — official mcp-clickhouse server via the MCP Python SDK
# ---------------------------------------------------------------------------

class LiveClickHouseMCP:
    live = True

    def __init__(self, settings: Settings):
        self.settings = settings
        self.url = settings.clickhouse_mcp_url
        self.database = settings.clickhouse_database
        self.headers = (
            {"Authorization": f"Bearer {settings.clickhouse_mcp_token}"}
            if settings.clickhouse_mcp_token else None
        )

    # -- MCP plumbing -------------------------------------------------------
    def _call(self, tool: str, args: dict) -> str:
        from app.observability.tracing import span as otel_span

        with otel_span(f"clickhouse.mcp.{tool}", tool=tool):
            return self._call_inner(tool, args)

    def _call_inner(self, tool: str, args: dict) -> str:
        async def run():
            from mcp import ClientSession

            try:  # mcp SDK 2.x: streams tuple + headers via custom http client
                from mcp.client.streamable_http import streamable_http_client as connect

                kwargs: dict = {}
                if self.headers:
                    import httpx

                    kwargs["http_client"] = httpx.AsyncClient(headers=self.headers, timeout=60.0)
                async with connect(self.url, **kwargs) as streams:
                    read, write = streams[0], streams[1]
                    async with ClientSession(read, write) as session:
                        await session.initialize()
                        return await session.call_tool(tool, args)
            except ImportError:  # older SDK spelling
                from mcp.client.streamable_http import streamablehttp_client as connect_old

                async with connect_old(self.url, headers=self.headers) as (read, write, _):
                    async with ClientSession(read, write) as session:
                        await session.initialize()
                        return await session.call_tool(tool, args)

        last_err: Exception | None = None
        for attempt in range(2):
            try:
                result = asyncio.run(run())
                text = _first_text(result)
                if getattr(result, "isError", False):
                    # tool-level errors (bad SQL etc.) are semantic, not transport —
                    # surface them to the bounded-repair loop instead of retrying
                    raise QuerySemanticError(text or f"MCP tool {tool} returned an error")
                # Proof lives here: a configured URL is not evidence, a returned
                # call is. /status reports IDLE until this fires.
                runtime_proof.record("clickhouse", "LIVE",
                                     f"MCP tool '{tool}' returned from {self.url}")
                return text
            except QuerySemanticError:
                # A tool-level error still proves the substrate answered.
                runtime_proof.record("clickhouse", "LIVE",
                                     f"MCP tool '{tool}' answered from {self.url}")
                raise
            except Exception as err:
                last_err = err
                time.sleep(1.0 + attempt)
        runtime_proof.record("clickhouse", "DEGRADED",
                             f"MCP call '{tool}' failed against {self.url} ({last_err})")
        raise ClickHouseUnavailable(f"ClickHouse MCP call '{tool}' failed: {last_err}")

    # -- verified tool surface ---------------------------------------------
    def run_query(self, sql: str, tag: str | None = None) -> QueryResult:
        cleaned = ensure_select_only(sql)
        if tag:
            # the tag rides into system.query_log, where costs_for() finds it —
            # added AFTER the guard so the guard never sees injected text
            cleaned = f"/* qtag:{tag} */ {cleaned}"
        t0 = time.time()
        text = self._call("run_query", {"query": cleaned})
        elapsed = (time.time() - t0) * 1000
        try:
            payload = json.loads(text)
            return QueryResult(payload.get("columns", []), payload.get("rows", []), elapsed)
        except json.JSONDecodeError as err:
            raise ClickHouseUnavailable(f"unparseable run_query payload: {text[:200]}") from err

    def list_tables(self) -> list[dict]:
        """All tables, following pagination — 14 objects can exceed one page.

        mcp-clickhouse supports page_token/page_size (verified in ADR 0001);
        stopping at page one would silently truncate the schema grounding.
        """
        tables: list[dict] = []
        token = ""
        for _ in range(10):                        # hard bound, never spin
            args: dict = {"database": self.database}
            if token:
                args["page_token"] = token
            text = self._call("list_tables", args)
            try:
                payload = json.loads(text)
            except json.JSONDecodeError:
                return tables or [{"raw": text}]
            if isinstance(payload, dict):
                tables.extend(payload.get("tables", payload.get("items", [payload])))
                token = str(payload.get("next_page_token", "") or "")
                if not token:
                    break
            else:
                tables.extend(payload)
                break
        return tables

    def costs_for(self, tags: list[str]) -> dict[str, dict]:
        """What each tagged query actually cost, from system.query_log.

        Batched into one lookup; the log flushes every ~7.5s, so costs resolve
        lazily — a missing tag means "not flushed yet", never an error.
        """
        if not tags:
            return {}
        needles = ", ".join(f"'qtag:{t}'" for t in tags)
        sql = (
            "SELECT extract(query, 'qtag:([a-zA-Z0-9_-]+)') AS tag, "
            "any(read_rows) AS read_rows, any(read_bytes) AS read_bytes, "
            "any(memory_usage) AS memory_bytes, any(query_duration_ms) AS duration_ms, "
            "any(length(columns)) AS n_columns, any(partitions) AS partitions "
            "FROM system.query_log "
            f"WHERE type = 'QueryFinish' AND event_date >= yesterday() "
            f"AND multiSearchAny(query, [{needles}]) "
            "GROUP BY tag"
        )
        try:
            result = self.run_query(sql)
        except Exception:
            return {}
        out: dict[str, dict] = {}
        for row in result.as_dicts():
            years = sorted({p.rsplit(".", 1)[-1] for p in (row.get("partitions") or [])
                            if str(p.rsplit(".", 1)[-1]).isdigit()})
            out[str(row["tag"])] = {
                "read_rows": row.get("read_rows", 0),
                "read_bytes": row.get("read_bytes", 0),
                "memory_bytes": row.get("memory_bytes", 0),
                "duration_ms": row.get("duration_ms", 0),
                "n_columns": row.get("n_columns", 0),
                "years_touched": years,
            }
        return out

    def list_databases(self) -> list[str]:
        text = self._call("list_databases", {})
        try:
            payload = json.loads(text)
            return payload if isinstance(payload, list) else [str(payload)]
        except json.JSONDecodeError:
            return [text]


class QuerySemanticError(RuntimeError):
    """SQL reached ClickHouse and was rejected (syntax/semantics) — feeds the
    Query Engineer's bounded repair loop, never the transport retry loop."""


def _first_text(result) -> str:
    for content in getattr(result, "content", []) or []:
        text = getattr(content, "text", None)
        if text:
            return text
    return ""


# ---------------------------------------------------------------------------
# MOCK — recorded results from the deterministic corpus (clean-clone mode)
# ---------------------------------------------------------------------------

class MockClickHouseMCP:
    live = False

    def __init__(self, settings: Settings):
        self.settings = settings
        self.database = settings.clickhouse_database
        fixture_path = Path(__file__).parent / "fixtures" / "recorded_results.json"
        self._fixtures: dict[str, dict] = {}
        if fixture_path.exists():
            self._fixtures = json.loads(fixture_path.read_text(encoding="utf-8"))

    def run_query(self, sql: str, tag: str | None = None) -> QueryResult:
        cleaned = ensure_select_only(sql)
        for fixture in self._fixtures.get("queries", []):
            if fixture.get("match") and fixture["match"] in cleaned:
                return QueryResult(fixture["columns"], fixture["rows"], 4.2)
        # honest default: an empty result, never invented numbers
        return QueryResult(["note"], [["mock mode: no recorded result matches this query"]], 1.0)

    def list_tables(self) -> list[dict]:
        return self._fixtures.get("tables", [])

    def costs_for(self, tags: list[str]) -> dict[str, dict]:
        return {}                      # no query_log offline — costs are a live-only proof

    def costs_for(self, tags: list[str]) -> dict[str, dict]:
        """What each tagged query actually cost, from system.query_log.

        Batched into one lookup; the log flushes every ~7.5s, so costs resolve
        lazily — a missing tag means "not flushed yet", never an error.
        """
        if not tags:
            return {}
        needles = ", ".join(f"'qtag:{t}'" for t in tags)
        sql = (
            "SELECT extract(query, 'qtag:([a-zA-Z0-9_-]+)') AS tag, "
            "any(read_rows) AS read_rows, any(read_bytes) AS read_bytes, "
            "any(memory_usage) AS memory_bytes, any(query_duration_ms) AS duration_ms, "
            "any(length(columns)) AS n_columns, any(partitions) AS partitions "
            "FROM system.query_log "
            f"WHERE type = 'QueryFinish' AND event_date >= yesterday() "
            f"AND multiSearchAny(query, [{needles}]) "
            "GROUP BY tag"
        )
        try:
            result = self.run_query(sql)
        except Exception:
            return {}
        out: dict[str, dict] = {}
        for row in result.as_dicts():
            years = sorted({p.rsplit(".", 1)[-1] for p in (row.get("partitions") or [])
                            if str(p.rsplit(".", 1)[-1]).isdigit()})
            out[str(row["tag"])] = {
                "read_rows": row.get("read_rows", 0),
                "read_bytes": row.get("read_bytes", 0),
                "memory_bytes": row.get("memory_bytes", 0),
                "duration_ms": row.get("duration_ms", 0),
                "n_columns": row.get("n_columns", 0),
                "years_touched": years,
            }
        return out

    def list_databases(self) -> list[str]:
        return [self.database]


def get_clickhouse(settings: Settings):
    if settings.clickhouse_live:
        return LiveClickHouseMCP(settings)
    return MockClickHouseMCP(settings)
