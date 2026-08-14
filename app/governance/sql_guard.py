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
    r"set\s+role|kill|system|update|delete|exchange|move|undrop)\b",
    re.IGNORECASE,
)

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
    return cleaned
