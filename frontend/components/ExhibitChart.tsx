"use client";
/* Charts for the engine-room exhibits — each showcase result drawn instead of
   printed, in the workbench's own hand-rolled SVG. The raw table stays below
   as the audit view; these are the read. */

type Row = (string | number | null | number[])[];
interface Item { key: string; columns: string[]; rows: Row[] }

const BLUE = "#2456a6", ORANGE = "#c24a12", GREEN = "#0c8a5a", GOLD = "#a67a00";
const num = (v: unknown) => (typeof v === "number" ? v : Number(v ?? 0));

function col(item: Item, name: string): number {
  return item.columns.indexOf(name);
}

/** cash_curves: cumulative overrun trajectories. Four storied eras carry
 *  color; the other six stay as context ink — never nine hues. */
function CashCurves({ item }: { item: Item }) {
  const HI: Record<string, string> = {
    golden_age: GREEN, conglomerate: ORANGE, dvd_peak: BLUE, streaming_wars_covid: GOLD,
  };
  const eI = col(item, "era"), mI = col(item, "month_index"), vI = col(item, "cumulative_overrun");
  const byEra = new Map<string, { m: number; v: number }[]>();
  for (const r of item.rows) {
    const e = String(r[eI]);
    (byEra.get(e) ?? byEra.set(e, []).get(e)!).push({ m: num(r[mI]), v: num(r[vI]) });
  }
  const all = [...byEra.values()].flat();
  const vMin = Math.min(...all.map((p) => p.v), 0.99);
  const vMax = Math.max(...all.map((p) => p.v), 1.05);
  const W = 560, H = 170, L = 34, B = 20, T = 8;
  const px = (m: number) => L + ((m - 1) / 17) * (W - L - 8);
  const py = (v: number) => H - B - ((v - vMin) / (vMax - vMin)) * (H - T - B);
  const line = (pts: { m: number; v: number }[]) =>
    "M" + pts.sort((a, b) => a.m - b.m).map((p) => `${px(p.m).toFixed(1)},${py(p.v).toFixed(1)}`).join("L");
  return (
    <svg viewBox={`0 0 ${W} ${H}`} className="xchart" role="img"
         aria-label="Cumulative overrun by production month, per era">
      <line x1={L} y1={py(1)} x2={W - 8} y2={py(1)} className="x-base" />
      <text x={L - 4} y={py(1) + 3} className="x-tick" textAnchor="end">1.00</text>
      <text x={L - 4} y={py(vMax) + 8} className="x-tick" textAnchor="end">{vMax.toFixed(2)}</text>
      {[...byEra.entries()].filter(([e]) => !HI[e]).map(([e, pts]) => (
        <path key={e} d={line(pts)} className="x-context"><title>{e}</title></path>
      ))}
      {[...byEra.entries()].filter(([e]) => HI[e]).map(([e, pts]) => {
        const last = pts.reduce((a, b) => (a.m > b.m ? a : b));
        return (
          <g key={e}>
            <path d={line(pts)} fill="none" stroke={HI[e]} strokeWidth="2"><title>{e}</title></path>
            <text x={px(last.m) - 2} y={py(last.v) - 4} className="x-label" fill={HI[e]}
                  textAnchor="end">{e.replaceAll("_", " ")}</text>
          </g>
        );
      })}
      <text x={W - 8} y={H - 6} className="x-tick" textAnchor="end">month 18 of production →</text>
    </svg>
  );
}

/** collapsing_window: two shares per era, horizontal paired bars. */
function WindowLadder({ item }: { item: Item }) {
  const eI = col(item, "era"), yI = col(item, "home_within_year"), dI = col(item, "home_within_45_days");
  const rows = item.rows;
  const W = 560, RH = 15, GAP = 7, L = 168;
  const H = rows.length * (RH + GAP) + 26;
  const bw = (v: number) => Math.max(v > 0 ? 3 : 0, v * (W - L - 60));
  return (
    <svg viewBox={`0 0 ${W} ${H}`} className="xchart" role="img"
         aria-label="Share of features reaching a home release, by era">
      {rows.map((r, i) => {
        const y = i * (RH + GAP) + 4;
        const yr = num(r[yI]), d45 = num(r[dI]);
        return (
          <g key={String(r[eI])}>
            <text x={L - 6} y={y + RH - 3} className="x-tick" textAnchor="end">
              {String(r[eI]).replaceAll("_", " ")}</text>
            <rect x={L} y={y} width={bw(yr)} height={RH - 6} rx="2" fill={BLUE}>
              <title>{`home within a year: ${(yr * 100).toFixed(0)}%`}</title></rect>
            <rect x={L} y={y + RH - 5} width={bw(d45)} height={4} rx="2" fill={GOLD}>
              <title>{`home within 45 days: ${(d45 * 100).toFixed(0)}%`}</title></rect>
            {yr > 0 && <text x={L + bw(yr) + 4} y={y + RH - 4} className="x-num">{(yr * 100).toFixed(0)}%</text>}
          </g>
        );
      })}
      <g>
        <rect x={L} y={H - 16} width="12" height="8" rx="2" fill={BLUE} />
        <text x={L + 16} y={H - 9} className="x-tick">within a year</text>
        <rect x={L + 110} y={H - 14} width="12" height="4" rx="2" fill={GOLD} />
        <text x={L + 126} y={H - 9} className="x-tick">within 45 days (PVOD era only)</text>
      </g>
    </svg>
  );
}

/** revenue_quantiles: P10–P90 fans per era, one hue for one measure. */
function QuantileFans({ item }: { item: Item }) {
  const eI = col(item, "era"), qI = col(item, "rev_multiple_p10_to_p90");
  const rows = item.rows.filter((r) => Array.isArray(r[qI]));
  const maxV = Math.max(...rows.map((r) => num((r[qI] as number[])[4])), 3);
  const W = 560, RH = 15, GAP = 7, L = 168;
  const H = rows.length * (RH + GAP) + 20;
  const px = (v: number) => L + (Math.min(v, maxV) / maxV) * (W - L - 46);
  return (
    <svg viewBox={`0 0 ${W} ${H}`} className="xchart" role="img"
         aria-label="Revenue multiple distribution per era, P10 to P90 with median">
      <line x1={px(1)} y1={0} x2={px(1)} y2={H - 18} className="x-base" />
      <text x={px(1) + 3} y={H - 22} className="x-tick">break-even ×1</text>
      {rows.map((r, i) => {
        const q = r[qI] as number[];
        const y = i * (RH + GAP) + 4;
        return (
          <g key={String(r[eI])}>
            <text x={L - 6} y={y + RH - 3} className="x-tick" textAnchor="end">
              {String(r[eI]).replaceAll("_", " ")}</text>
            <rect x={px(q[0])} y={y + 3} width={Math.max(2, px(q[4]) - px(q[0]))} height={RH - 10}
                  rx="2" fill={BLUE} opacity="0.25">
              <title>{`P10 ×${q[0]} — P90 ×${q[4]}`}</title></rect>
            <rect x={px(q[1])} y={y + 1} width={Math.max(2, px(q[3]) - px(q[1]))} height={RH - 6}
                  rx="2" fill={BLUE} opacity="0.45">
              <title>{`P25 ×${q[1]} — P75 ×${q[3]}`}</title></rect>
            <rect x={px(q[2]) - 1.5} y={y - 1} width="3" height={RH - 2} rx="1" fill={BLUE}>
              <title>{`median ×${q[2]}`}</title></rect>
            <text x={px(q[4]) + 5} y={y + RH - 4} className="x-num">×{q[2]}</text>
          </g>
        );
      })}
    </svg>
  );
}

/** franchise_fatigue_curves: small multiples, one 3-point line each. */
function FatigueMultiples({ item }: { item: Item }) {
  const cI = col(item, "cycle_type"), aI = col(item, "avg_multiple_vs_entry1"),
        nI = col(item, "n_franchises");
  const rows = item.rows.filter((r) => Array.isArray(r[aI]));
  const CW = 128, CH = 92, PER = 4;
  const W = Math.min(rows.length, PER) * (CW + 14);
  const H = Math.ceil(rows.length / PER) * (CH + 18);
  const vMax = Math.max(...rows.flatMap((r) => r[aI] as number[]), 1.3);
  return (
    <svg viewBox={`0 0 ${W} ${H}`} className="xchart" role="img"
         aria-label="Average revenue multiple by entry number, per franchise cycle type">
      {rows.map((r, i) => {
        const curve = r[aI] as number[];
        const ox = (i % PER) * (CW + 14), oy = Math.floor(i / PER) * (CH + 18);
        const px = (j: number) => ox + 16 + (j / (curve.length - 1)) * (CW - 30);
        const py = (v: number) => oy + 12 + (1 - v / vMax) * (CH - 34);
        const d = "M" + curve.map((v, j) => `${px(j).toFixed(1)},${py(v).toFixed(1)}`).join("L");
        return (
          <g key={String(r[cI])}>
            <line x1={ox + 16} y1={py(1)} x2={ox + CW - 14} y2={py(1)} className="x-base" />
            <path d={d} fill="none" stroke={GREEN} strokeWidth="2" />
            {curve.map((v, j) => (
              <circle key={j} cx={px(j)} cy={py(v)} r="3.5" fill={GREEN}>
                <title>{`entry ${j + 1}: ×${v} of entry 1`}</title></circle>
            ))}
            <text x={ox + 16} y={oy + CH - 8} className="x-tick">
              {String(r[cI]).replaceAll("_", " ")} · {num(r[nI])} franchises</text>
            <text x={px(curve.length - 1) + 2} y={py(curve[curve.length - 1]) + 3}
                  className="x-num">{curve[curve.length - 1]}</text>
          </g>
        );
      })}
    </svg>
  );
}

/** simple horizontal bars for the attribution exhibits: one measure, one hue. */
function Bars({ item, labelCol, valueCol, fmt }: {
  item: Item; labelCol: string; valueCol: string; fmt: (v: number) => string;
}) {
  const lI = col(item, labelCol), vI = col(item, valueCol);
  const rows = item.rows.slice(0, 12);
  const maxV = Math.max(...rows.map((r) => num(r[vI])), 0.001);
  const W = 560, RH = 14, GAP = 6, L = 210;
  const H = rows.length * (RH + GAP) + 6;
  return (
    <svg viewBox={`0 0 ${W} ${H}`} className="xchart" role="img"
         aria-label={`${valueCol} by ${labelCol}`}>
      {rows.map((r, i) => {
        const y = i * (RH + GAP) + 2, v = num(r[vI]);
        return (
          <g key={i}>
            <text x={L - 6} y={y + RH - 3} className="x-tick" textAnchor="end">
              {String(r[lI]).replaceAll("_", " ").slice(0, 34)}</text>
            <rect x={L} y={y} width={Math.max(3, (v / maxV) * (W - L - 64))} height={RH - 4}
                  rx="2" fill={BLUE}><title>{fmt(v)}</title></rect>
            <text x={L + Math.max(3, (v / maxV) * (W - L - 64)) + 5} y={y + RH - 4}
                  className="x-num">{fmt(v)}</text>
          </g>
        );
      })}
    </svg>
  );
}

export function ExhibitChart({ item }: { item: Item }) {
  if (!item.rows.length) return null;
  switch (item.key) {
    case "cash_curves": return <CashCurves item={item} />;
    case "collapsing_window": return <WindowLadder item={item} />;
    case "revenue_quantiles": return <QuantileFans item={item} />;
    case "franchise_fatigue_curves": return <FatigueMultiples item={item} />;
    case "shock_attribution":
      return <Bars item={item} labelCol="nearest_preceding_shock"
                   valueCol="opening_over_budget" fmt={(v) => `×${v.toFixed(2)}`} />;
    case "era_attribution_dict":
      return <Bars item={item} labelCol="era_earned"
                   valueCol="revenue_earned_b" fmt={(v) => `$${v.toFixed(1)}B`} />;
    default: return null;   // superlatives + sparkbar read best as their tables
  }
}
