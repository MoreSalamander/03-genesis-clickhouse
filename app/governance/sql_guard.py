"""SELECT-only enforcement, in code (locked §2.3 / §2.9).

Gemini writes SQL; this guard decides whether it runs. Defense in depth sits
behind it (mcp-clickhouse read-only mode + the `readonly=2` ClickHouse user),
but the first gate is ours and it is auditable.
"""
from __future__ import annotations

import re


class SQLRejected(ValueError):
    """Raised when generated SQL fails the read-only policy."""


_FORBIDDEN = re.compile(
    r"\b(insert|alter|drop|create|truncate|rename|attach|detach|optimize|grant|revoke|"
    r"set\s+role|kill|update|delete|exchange|move|undrop)\b",
    re.IGNORECASE,
)

# SYSTEM is only dangerous as a COMMAND (SYSTEM FLUSH LOGS, SYSTEM RELOAD …).
# Reading system.query_log / system.parts is how the console proves what a
# query cost — the introspection tables are part of the showcase, not a risk.
_SYSTEM_COMMAND = re.compile(r"\bsystem\s+(?!\.)[a-z]", re.IGNORECASE)
_SYSTEM_TABLES_ALLOWED = ("system.query_log", "system.parts", "system.columns",
                          "system.tables")
_SYSTEM_TABLE = re.compile(r"\bsystem\s*\.\s*([a-z_]+)", re.IGNORECASE)

_COMMENT = re.compile(r"(--[^\n]*|/\*.*?\*/)", re.DOTALL)


def ensure_select_only(sql: str) -> str:
    """Returns the cleaned single-statement SELECT, or raises SQLRejected."""
    if not sql or not sql.strip():
        raise SQLRejected("empty SQL")
    cleaned = _COMMENT.sub(" ", sql).strip().rstrip(";").strip()
    if ";" in cleaned:
        raise SQLRejected("multiple statements are not allowed")
    head = cleaned.split(None, 1)[0].lower() if cleaned.split() else ""
    if head not in ("select", "with", "describe", "show", "explain"):
        raise SQLRejected(f"only SELECT-family statements may run (got '{head}')")
    match = _FORBIDDEN.search(cleaned)
    if match:
        raise SQLRejected(f"forbidden keyword '{match.group(0)}' in generated SQL")
    if _SYSTEM_COMMAND.search(cleaned):
        raise SQLRejected("SYSTEM commands are not allowed")
    for table in _SYSTEM_TABLE.findall(cleaned):
        if f"system.{table.lower()}" not in _SYSTEM_TABLES_ALLOWED:
            raise SQLRejected(f"system.{table} is not a readable introspection table here")
    return cleaned
