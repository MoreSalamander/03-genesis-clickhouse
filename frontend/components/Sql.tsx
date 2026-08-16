"use client";
/* SQL rendering for the query ledger.

   "Every number auditable" only lands if the SQL is actually readable, so the
   ledger tokenizes it here rather than pulling in a highlighter: one regex, one
   pass, no dependency, and a copy button so a reviewer can run the query
   themselves against the same corpus. */

import { useState } from "react";

const KEYWORDS = new Set([
  "SELECT", "FROM", "WHERE", "PREWHERE", "GROUP", "BY", "ORDER", "HAVING", "LIMIT",
  "OFFSET", "JOIN", "LEFT", "RIGHT", "INNER", "FULL", "OUTER", "CROSS", "ON", "USING",
  "AS", "AND", "OR", "NOT", "IN", "IS", "NULL", "CASE", "WHEN", "THEN", "ELSE", "END",
  "WITH", "UNION", "ALL", "DISTINCT", "ASC", "DESC", "BETWEEN", "LIKE", "ILIKE",
  "INTERVAL", "SETTINGS", "FORMAT", "SAMPLE", "ARRAY", "OVER", "PARTITION", "WINDOW",
  "EXISTS", "ANY", "GLOBAL", "FINAL", "TOP", "INTO", "VALUES", "TRUE", "FALSE",
]);

// comment | string | number | word | whitespace | anything else
const TOKENS = /(--[^\n]*|\/\*[\s\S]*?\*\/)|('(?:''|\\.|[^'\\])*')|(\b\d+(?:\.\d+)?\b)|([A-Za-z_][A-Za-z0-9_$]*)|(\s+)|([^\s])/g;

interface Token { text: string; kind: string }

export function tokenizeSql(sql: string): Token[] {
  const out: Token[] = [];
  TOKENS.lastIndex = 0;
  let match: RegExpExecArray | null;
  while ((match = TOKENS.exec(sql)) !== null) {
    const [text, comment, str, num, word, space] = match;
    if (comment) out.push({ text, kind: "c" });
    else if (str) out.push({ text, kind: "s" });
    else if (num) out.push({ text, kind: "n" });
    else if (word) {
      if (KEYWORDS.has(word.toUpperCase())) out.push({ text, kind: "k" });
      // A word immediately followed by "(" is a call — count(), quantile(), …
      else if (sql[TOKENS.lastIndex] === "(") out.push({ text, kind: "f" });
      else out.push({ text, kind: "i" });
    } else if (space) out.push({ text, kind: "w" });
    else out.push({ text, kind: "p" });
  }
  return out;
}

export function Sql({ sql }: { sql: string }) {
  const [copied, setCopied] = useState(false);

  const copy = async () => {
    try {
      await navigator.clipboard.writeText(sql);
      setCopied(true);
      setTimeout(() => setCopied(false), 1600);
    } catch {
      setCopied(false); // clipboard blocked (insecure origin) — the SQL is still selectable
    }
  };

  return (
    <div className="sql-block">
      <button className="sql-copy" onClick={copy} title="Copy this query to the clipboard">
        {copied ? "✓ COPIED" : "COPY"}
      </button>
      <pre className="query-sql">
        {tokenizeSql(sql).map((token, i) =>
          token.kind === "w"
            ? token.text
            : <span key={i} className={`t-${token.kind}`}>{token.text}</span>,
        )}
      </pre>
    </div>
  );
}
