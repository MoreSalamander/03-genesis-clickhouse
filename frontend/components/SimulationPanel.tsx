import { Simulation } from "@/lib/api";

// dollar projections when the scenario scaled to a budget; ×multiples otherwise
const money = (v: number | undefined) =>
  v === undefined ? "—"
    : Math.abs(v) >= 100_000 ? `$${(v / 1e6).toFixed(1)}M`
    : `×${v.toFixed(2)}`;

/** P10–P90 as a band with the median marked, baseline and alternative drawn on
 *  one shared scale so the overlap — or the lack of it — is the thing you see.
 *  Three numbers in a row cannot show whether two distributions overlap. */
function DistributionStrip({ sim }: { sim: Simulation }) {
  const rows = [
    { label: "baseline", d: sim.baseline, cls: "base" },
    { label: "alternative", d: sim.projected, cls: "alt" },
  ];
  const values = rows.flatMap((r) => [r.d.p10, r.d.p50, r.d.p90])
    .filter((v): v is number => typeof v === "number");
  if (values.length < 6) return null;   // partial distribution — draw nothing rather than guess

  const lo = Math.min(...values);
  const hi = Math.max(...values);
  const span = hi - lo || 1;
  const pct = (v: number) => ((v - lo) / span) * 100;

  return (
    <div className="dist">
      {rows.map((row) => (
        <div className="dist-row" key={row.label}>
          <span className="dist-label">{row.label}</span>
          <span className="dist-track">
            <span className={`dist-band ${row.cls}`}
                  style={{ left: `${pct(row.d.p10!)}%`, width: `${pct(row.d.p90!) - pct(row.d.p10!)}%` }} />
            <span className={`dist-median ${row.cls}`} style={{ left: `${pct(row.d.p50!)}%` }} />
          </span>
          <span className="dist-num">{money(row.d.p50)}</span>
        </div>
      ))}
      <div className="dist-axis">
        <span>{money(lo)}</span>
        <span className="dist-axis-label">P10 — P90 band, median marked · shared scale</span>
        <span>{money(hi)}</span>
      </div>
    </div>
  );
}

export function SimulationPanel({ sim }: { sim: Simulation }) {
  const base = sim.baseline;
  const proj = sim.projected;
  return (
    <div className="sim-panel">
      <div className="scenario">“{sim.scenario}”</div>
      <DistributionStrip sim={sim} />
      <div className="sim-cols">
        <div className="sim-col">
          <h4>Baseline</h4>
          <div className="p50">{money(base.p50)}</div>
          <div className="band">P10 {money(base.p10)} — P90 {money(base.p90)} · n={base.cohort_n}</div>
        </div>
        <div className="sim-col">
          <h4>Alternative</h4>
          <div className="p50">{money(proj.p50)}</div>
          <div className="band">P10 {money(proj.p10)} — P90 {money(proj.p90)} · n={proj.cohort_n}</div>
        </div>
        <div className="sim-col delta">
          <h4>Δ median</h4>
          <div className="p50">{sim.delta.p50 >= 0 ? "+" : ""}{money(sim.delta.p50)}</div>
          <div className="band">seeded · reproducible (seed {sim.seed})</div>
        </div>
      </div>
      <div className="sim-note">{sim.narrative}</div>
    </div>
  );
}
