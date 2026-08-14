import { Simulation } from "@/lib/api";

const money = (v: number | undefined) =>
  v === undefined ? "—" : `$${(v / 1e6).toFixed(1)}M`;

export function SimulationPanel({ sim }: { sim: Simulation }) {
  const base = sim.baseline;
  const proj = sim.projected;
  return (
    <div className="sim-panel">
      <div className="scenario">“{sim.scenario}”</div>
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
