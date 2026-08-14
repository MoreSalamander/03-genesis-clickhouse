"use client";
import { useState } from "react";
import { AnalyticalQuery } from "@/lib/api";

function ResultTable({ query }: { query: AnalyticalQuery }) {
  if (query.rows.length === 0) return null;
  const shown = query.rows.slice(0, 10);
  return (
    <div className="query-result">
      <table>
        <thead>
          <tr>{query.columns.map((c) => <th key={c}>{c}</th>)}</tr>
        </thead>
        <tbody>
          {shown.map((row, i) => (
            <tr key={i}>
              {row.map((cell, j) => (
                <td key={j}>{typeof cell === "number" ? cell.toLocaleString() : String(cell)}</td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
      {query.rows.length > shown.length && (
        <div className="hint">… {query.row_count.toLocaleString()} rows total (full set snapshotted to MinIO)</div>
      )}
    </div>
  );
}

export function QueryLedger({ queries }: { queries: AnalyticalQuery[] }) {
  const [openId, setOpenId] = useState<string | null>(null);
  if (queries.length === 0) return <div className="hint">Waiting for the Query Engineer…</div>;
  return (
    <div className="query-ledger">
      {queries.map((query) => (
        <div className="query-row" key={query.id}>
          <div className="query-head" onClick={() => setOpenId(openId === query.id ? null : query.id)}>
            <span className="qid">{query.id}</span>
            <span className="purpose">{query.purpose.replace("canonical:", "")}</span>
            <span className="meta">
              {query.error
                ? <span className="err">FAILED after {query.repairs} repair(s)</span>
                : <>{query.row_count.toLocaleString()} rows · {Math.round(query.elapsed_ms)}ms
                    {query.repairs > 0 ? ` · ${query.repairs} repair(s)` : ""}</>}
              {" "}{openId === query.id ? "▾" : "▸"}
            </span>
          </div>
          {openId === query.id && (
            <>
              <div className="query-sql">{query.sql}</div>
              {query.error ? <div className="error-note">{query.error}</div> : <ResultTable query={query} />}
            </>
          )}
        </div>
      ))}
    </div>
  );
}
