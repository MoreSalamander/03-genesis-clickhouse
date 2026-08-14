import { Interpretation } from "@/lib/api";

export function Interpretations({ interpretations }: { interpretations: Interpretation[] }) {
  return (
    <div className="interp-grid">
      {interpretations.map((interp) => (
        <div className={`interp ${interp.stance.toLowerCase()}`} key={interp.id}>
          <div className="label">{interp.label}</div>
          <div className="stance">{interp.stance}</div>
          <div className="narrative">{interp.narrative}</div>
          {interp.cited_query_ids.length > 0 && (
            <div className="cites">evidence: {interp.cited_query_ids.join(", ")}</div>
          )}
        </div>
      ))}
    </div>
  );
}
