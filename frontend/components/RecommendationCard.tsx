"use client";
import { useState } from "react";
import { Investigation } from "@/lib/api";

export function RecommendationCard({
  inv,
  busy,
  onDecide,
}: {
  inv: Investigation;
  busy: boolean;
  onDecide: (decision: string, note: string) => void;
}) {
  const [note, setNote] = useState("");
  const rec = inv.recommendation!;
  const awaiting = inv.status === "RECOMMENDED";
  const lastDecision = inv.decisions[inv.decisions.length - 1];

  return (
    <div className="rec-card">
      <div className="action">{rec.action}</div>
      <div className="rationale">{rec.rationale}</div>
      <div className="rec-meter">
        <span className="num">{Math.round(rec.confidence * 100)}%</span>
        <div className="bar"><div className="fill" style={{ width: `${rec.confidence * 100}%` }} /></div>
        <span className="hint">confidence = f(verification coverage)</span>
      </div>
      <div className="coverage-chips">
        {Object.entries(rec.coverage).map(([state, count]) =>
          count > 0 ? <span key={state} className={`chip ${state}`}>{count} {state}</span> : null
        )}
      </div>
      {rec.caveats.length > 0 && (
        <ul className="caveats">
          {rec.caveats.map((caveat, i) => <li key={i}>{caveat}</li>)}
        </ul>
      )}

      {awaiting ? (
        <div className="decide-row">
          <input
            placeholder="Note to the record (required for deeper analysis)…"
            value={note}
            onChange={(e) => setNote(e.target.value)}
          />
          <button className="btn approve" disabled={busy} onClick={() => onDecide("approved", note)}>
            APPROVE &amp; PROMOTE
          </button>
          <button className="btn deeper" disabled={busy || !note.trim()}
                  onClick={() => onDecide("deeper", note)}>
            REQUEST DEEPER ANALYSIS
          </button>
          <button className="btn reject" disabled={busy} onClick={() => onDecide("rejected", note)}>
            REJECT
          </button>
        </div>
      ) : (
        lastDecision && (
          <div className={`verdict ${lastDecision.decision}`}>
            {lastDecision.decision.toUpperCase()}
            {lastDecision.note ? ` — ${lastDecision.note}` : ""} · {inv.status}
          </div>
        )
      )}
      {inv.promotion && inv.promotion.datahub_urns.length > 0 && (
        <div className="promoted-note">
          {inv.promotion.datahub_urns.length} finding(s) promoted to DataHub with query lineage
        </div>
      )}
    </div>
  );
}
