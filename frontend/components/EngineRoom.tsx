"use client";
/* The engine room: the seven showcase queries, live.

   Each card is one ClickHouse capability the deep dive promised — window
   functions, windowFunnel, quantiles, arrays, ASOF, argMax, dictGet — run
   through the same read-only MCP path as the investigations, with its timing
   and its top rows. The SQL is the exhibit: expand a card and read exactly
   what the engine was asked. */
import { useEffect, useState } from "react";
import { QueryCost, getShowcaseCosts } from "@/lib/api";

interface ShowcaseItem {
  key: string;
  feature: string;
  story: string;
  sql: string;
  columns: string[];
  rows: (string | number | null)[][];
  row_count: number;
  elapsed_ms: number;
  error: string | null;
}

export function EngineRoom() {
  const [items, setItems] = useState<ShowcaseItem[]>([]);
  const [open, setOpen] = useState<string | null>(null);
  const [ran, setRan] = useState(false);
  const [costs, setCosts] = useState<Record<string, QueryCost>>({});

  useEffect(() => {
    fetch("/api/showcase")
      .then((r) => r.json())
      .then((data) => { setItems(data); setRan(true); })
      .catch(() => setRan(true));
    // the query log flushes ~every 8s; the true costs arrive as a second beat
    const t = setTimeout(() => { getShowcaseCosts().then(setCosts).catch(() => {}); }, 9000);
    return () => clearTimeout(t);
  }, []);

  if (!ran) return <div className="hint">Running the seven exhibits through ClickHouse…</div>;
  if (items.length === 0) return <div className="hint">Showcase unavailable.</div>;

  return (
    <div className="engine-room">
      {items.map((item) => (
        <div key={item.key} className={`exhibit${open === item.key ? " open" : ""}`}>
          <button className="exhibit-head" onClick={() => setOpen(open === item.key ? null : item.key)}
                  aria-expanded={open === item.key}>
            <span className="feature">{item.feature}</span>
            <span className="story">{item.story}</span>
            <span className="cost">
              {item.error ? "failed" : <>{item.row_count} rows · {Math.round(item.elapsed_ms)}ms</>}
              {costs[`sc-${item.key}`] && (
                <em> · read {(costs[`sc-${item.key}`].read_rows / 1e6).toFixed(1)}M rows
                  · {costs[`sc-${item.key}`].years_touched.length || "–"} partitions</em>
              )}
              {" "}{open === item.key ? "▾" : "▸"}
            </span>
          </button>
          {open === item.key && (
            <div className="exhibit-body">
              {item.error
                ? <div className="err">{item.error}</div>
                : (
                  <div className="exhibit-result">
                    <table>
                      <thead><tr>{item.columns.map((c) => <th key={c}>{c}</th>)}</tr></thead>
                      <tbody>
                        {item.rows.slice(0, 10).map((row, i) => (
                          <tr key={i}>{row.map((cell, j) => (
                            <td key={j}>{Array.isArray(cell) ? JSON.stringify(cell) : String(cell)}</td>
                          ))}</tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                )}
              <pre className="exhibit-sql">{item.sql}</pre>
            </div>
          )}
        </div>
      ))}
    </div>
  );
}
