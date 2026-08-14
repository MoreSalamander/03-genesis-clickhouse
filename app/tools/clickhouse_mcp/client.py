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
                return text
            except QuerySemanticError:
                raise
            except Exception as err:
                last_err = err
                time.sleep(1.0 + attempt)
        raise ClickHouseUnavailable(f"ClickHouse MCP call '{tool}' failed: {last_err}")

    # -- verified tool surface ---------------------------------------------
    def run_query(self, sql: str) -> QueryResult:
        cleaned = ensure_select_only(sql)
        t0 = time.time()
        text = self._call("run_query", {"query": cleaned})
        elapsed = (time.time() - t0) * 1000
        try:
            payload = json.loads(text)
            return QueryResult(payload.get("columns", []), payload.get("rows", []), elapsed)
        except json.JSONDecodeError as err:
            raise ClickHouseUnavailable(f"unparseable run_query payload: {text[:200]}") from err

    def list_tables(self) -> list[dict]:
        text = self._call("list_tables", {"database": self.database})
        try:
            payload = json.loads(text)
        except json.JSONDecodeError:
            return [{"raw": text}]
        if isinstance(payload, dict):
            return payload.get("tables", payload.get("items", [payload]))
        return payload

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

    def run_query(self, sql: str) -> QueryResult:
        cleaned = ensure_select_only(sql)
        for fixture in self._fixtures.get("queries", []):
            if fixture.get("match") and fixture["match"] in cleaned:
                return QueryResult(fixture["columns"], fixture["rows"], 4.2)
        # honest default: an empty result, never invented numbers
        return QueryResult(["note"], [["mock mode: no recorded result matches this query"]], 1.0)

    def list_tables(self) -> list[dict]:
        return self._fixtures.get("tables", [])

    def list_databases(self) -> list[str]:
        return [self.database]


def get_clickhouse(settings: Settings):
    if settings.clickhouse_live:
        return LiveClickHouseMCP(settings)
    return MockClickHouseMCP(settings)
