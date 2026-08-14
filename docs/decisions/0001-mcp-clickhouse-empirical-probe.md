# ADR 0001 — Empirical probe of the official mcp-clickhouse server

**Date:** 2026-08-13 · **Status:** accepted · **Verified against:** `mcp-clickhouse 2.14.7` (PyPI, run per [ops/mcp-clickhouse/Dockerfile](../../ops/mcp-clickhouse/Dockerfile))

Locked §2.5 requires the official mcp-clickhouse server as the agents' only path to
ClickHouse, with tool names captured at architecture time as
`run_select_query · list_tables · list_databases`. Per the build plan, tool schemas
were verified empirically before agent wiring. Findings:

## Verified server behavior (probe transcript, 2026-08-13, local stack)

- **Transport**: streamable-HTTP at `/mcp`; **bearer auth is mandatory** for HTTP/SSE
  transports (`CLICKHOUSE_MCP_AUTH_TOKEN` static token; the alternative
  `CLICKHOUSE_MCP_AUTH_DISABLED=true` is dev-only and not used).
- **Tools exposed** (3):
  - `list_databases` — no args.
  - `list_tables` — args `database` (required), `like`, `not_like`, `page_token`,
    `page_size`, `include_detailed_columns`; returns schema, comment, row/column counts.
  - `run_query` — arg `query` (required). **The architecture-time name
    `run_select_query` no longer exists in 2.14.7** — the server renamed it to
    `run_query`, which "runs in read-only mode by default" (writes require
    `CLICKHOUSE_ALLOW_WRITE_ACCESS=true`, which we do NOT set).
- **Result shape**: `run_query` returns one text content block of JSON:
  `{"columns": [...], "rows": [[...], ...]}`.
- **Write defense in depth confirmed**: an INSERT through MCP fails twice over —
  the server's read-only default AND ClickHouse's `readonly=2` profile on the `mcp`
  user (`DB::Exception: Cannot execute query in readonly mode`).

## Decision

The client wrapper ([app/tools/clickhouse_mcp/client.py](../../app/tools/clickhouse_mcp/client.py))
targets the **verified** tool set (`run_query`, `list_tables`, `list_databases`).
The locked architecture's *requirement* (official server, read-only, schema grounding
via live introspection) is unchanged; only the architecture document's captured tool
name drifted from the shipped server. Deviation recorded here rather than silently
adapted, per the requirement-classification discipline.

Config gotcha recorded: the ClickHouse container reads `users.d/*.xml` directly —
mount the user file itself, not a parent directory.
