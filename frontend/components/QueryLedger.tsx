"use client";
import { useState } from "react";
import { AnalyticalQuery, QueryCost, postRequery } from "@/lib/api";
import { Sql } from "@/components/Sql";
import { Note, cascade } from "@/lib/alive";

const fmtRows = (n: number) =>
  n >= 1e6 ? `${(n / 1e6).toFixed(1)}M` : n >= 1e3 ? `${Math.round(n / 1e3)}k` : `${n}`;
const fmtBytes = (n: number) =>
  n >= 1e9 ? `${(n / 1e9).toFixed(1)}GB` : n >= 1e6 ? `${Math.round(n / 1e6)}MB` : `${Math.round(n / 1e3)}kB`;

/** 1912–2026 as a strip; the years this query actually touched light up.
 *  This is partition pruning made visible: a sharp question lights a few
 *  cells, a century sweep lights the wall. */
function PartitionStrip({ years }: { years: string[] }) {
  const touched = new Set(years.map(Number));
  const cells = [];
  for (let y = 1912; y <= 2026; y++) cells.push(y);
  return (
    <div className="pstrip" title={`partitions read: ${years.length} of 115 years`}>
      {cells.map((y) => (
        <span key={y} className={`pcell${touched.has(y) ? " hit" : ""}`}
              title={touched.has(y) ? String(y) : undefined} />
      ))}
      <span className="pstrip-label">{years.length}/115 yearly partitions read</span>
    </div>
  );
}

function CostLine({ cost }: { cost: QueryCost }) {
  return (
    <div className="qcost">
      read {fmtRows(cost.read_rows)} rows · {cost.n_columns} columns · {fmtBytes(cost.read_bytes)} ·
      {" "}{Math.round(cost.duration_ms)}ms in the engine · {fmtBytes(cost.memory_bytes)} peak
    </div>
  );
}

function RequeryButton({ queryId }: { queryId: string }) {
  const [state, setState] = useState<string>("");
  const run = async (e: React.MouseEvent) => {
    e.stopPropagation();
    setState("running…");
    try {
      const r = await postRequery(queryId);
      setState(`${r.reproduced ? "REPRODUCED" : "row count drifted"} — ${r.fresh_rows} rows in ${Math.round(r.elapsed_ms)}ms`);
    } catch (err) {
      setState(`unavailable (${err instanceof Error ? err.message.slice(0, 60) : "error"})`);
    }
  };
  return (
    <span className="requery">
      <button onClick={run}>run again now</button>
      {state && <em className={state.startsWith("REPRODUCED") ? "ok" : ""}>{state}</em>}
    </span>
  );
}

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

export function QueryLedger({ queries, costs = {} }: {
  queries: AnalyticalQuery[];
  costs?: Record<string, QueryCost>;
}) {
  const [openId, setOpenId] = useState<string | null>(null);
  if (queries.length === 0) return <div className="hint">Waiting for the Query Engineer…</div>;
  return (
    <div className="query-ledger alive-cascade">
      {queries.map((query, i) => (
        <div className="query-row" key={query.id} style={cascade(i)}>
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
              <Sql sql={query.sql} />
              {costs[query.id] && <CostLine cost={costs[query.id]} />}
              {costs[query.id] && costs[query.id].years_touched.length > 0 && (
                <PartitionStrip years={costs[query.id].years_touched} />
              )}
              {query.error ? <Note tone="bad">{query.error}</Note> : <ResultTable query={query} />}
              {!query.error && <RequeryButton queryId={query.id} />}
              {query.explain && (
                <details className="explain">
                  <summary>EXPLAIN indexes — the pruning, on the record</summary>
                  <pre>{query.explain}</pre>
                </details>
              )}
            </>
          )}
        </div>
      ))}
    </div>
  );
}
