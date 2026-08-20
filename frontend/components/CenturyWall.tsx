"use client";
/* A century of us — the whole corpus as one picture.

   Stacked areas of yearly revenue by channel group, in 2026 dollars (the
   corpus's own rule: cross-era money deflates). Era boundaries are rules,
   attendance shocks are shaded bands, and every visual feature is an
   engineered truth the probes verify by SQL: the 1946 peak, television
   arriving in 1955, video passing theatrical in 1986, the 2004 DVD summit,
   the COVID notch, the streaming flood.

   Five channel groups, fixed order and fixed hues (validated against the
   paper surface for CVD separation and contrast — see decisions.md). */
import { useEffect, useMemo, useRef, useState } from "react";

interface SeriesRow { y: number; channel_group: string; revenue_2026_m: number }
interface EraRow { era_id: number; name: string; from_year: number; to_year: number }
interface ShockRow { name: string; from_year: number; to_year: number; attendance_mult: number }

// fixed order = narrative order (birth order); hues validated, never cycled
const GROUPS: { key: string; label: string; hue: string }[] = [
  { key: "theatrical", label: "theatrical", hue: "#2456a6" },
  { key: "television", label: "television", hue: "#c24a12" },
  { key: "home_video", label: "home video & transactional", hue: "#0c8a5a" },
  { key: "licensed_streaming", label: "licensed streaming", hue: "#8a4fc8" },
  { key: "convergence_plus", label: "Convergence+", hue: "#a67a00" },
];

const W = 1000, H = 300, TOP = 34, BOTTOM = 26, LEFT = 8, RIGHT = 8;
const Y0 = 1912, Y1 = 2026;

export function CenturyWall() {
  const [series, setSeries] = useState<SeriesRow[]>([]);
  const [eras, setEras] = useState<EraRow[]>([]);
  const [shocks, setShocks] = useState<ShockRow[]>([]);
  const [hoverYear, setHoverYear] = useState<number | null>(null);
  const svgRef = useRef<SVGSVGElement>(null);

  useEffect(() => {
    fetch("/api/century").then((r) => r.json())
      .then((d) => { setSeries(d.series ?? []); setEras(d.eras ?? []); setShocks(d.shocks ?? []); })
      .catch(() => {});
  }, []);

  const { paths, totals, maxTotal } = useMemo(() => {
    const byYear = new Map<number, Record<string, number>>();
    for (const row of series) {
      const y = byYear.get(row.y) ?? {};
      y[row.channel_group] = (y[row.channel_group] ?? 0) + row.revenue_2026_m;
      byYear.set(row.y, y);
    }
    const years: number[] = [];
    for (let y = Y0; y <= Y1; y++) years.push(y);
    const totals = new Map<number, number>();
    let maxTotal = 1;
    for (const y of years) {
      const t = GROUPS.reduce((acc, g) => acc + (byYear.get(y)?.[g.key] ?? 0), 0);
      totals.set(y, t);
      if (t > maxTotal) maxTotal = t;
    }
    const px = (y: number) => LEFT + ((y - Y0) / (Y1 - Y0)) * (W - LEFT - RIGHT);
    const py = (v: number) => H - BOTTOM - (v / maxTotal) * (H - TOP - BOTTOM);
    // stack bottom-up in group order
    const paths = GROUPS.map((g, gi) => {
      const lower = years.map((y) => {
        let s = 0;
        for (let k = 0; k < gi; k++) s += byYear.get(y)?.[GROUPS[k].key] ?? 0;
        return { y, v: s };
      });
      const upper = years.map((y, i) => ({ y, v: lower[i].v + (byYear.get(y)?.[g.key] ?? 0) }));
      const d = "M" + upper.map((p) => `${px(p.y).toFixed(1)},${py(p.v).toFixed(1)}`).join("L")
        + "L" + [...lower].reverse().map((p) => `${px(p.y).toFixed(1)},${py(p.v).toFixed(1)}`).join("L")
        + "Z";
      return { ...g, d };
    });
    return { paths, totals, maxTotal };
  }, [series]);

  if (series.length === 0) return null;   // mock-degraded or still loading — the wall is a live exhibit

  const px = (y: number) => LEFT + ((y - Y0) / (Y1 - Y0)) * (W - LEFT - RIGHT);
  const hover = hoverYear !== null ? {
    year: hoverYear,
    total: totals.get(hoverYear) ?? 0,
    parts: GROUPS.map((g) => ({
      ...g,
      v: series.filter((r) => r.y === hoverYear && r.channel_group === g.key)
               .reduce((a, r) => a + r.revenue_2026_m, 0),
    })).filter((p) => p.v > 0.5),
  } : null;

  const onMove = (e: React.MouseEvent<SVGSVGElement>) => {
    const rect = svgRef.current?.getBoundingClientRect();
    if (!rect) return;
    const fx = ((e.clientX - rect.left) / rect.width) * W;
    const year = Math.round(Y0 + ((fx - LEFT) / (W - LEFT - RIGHT)) * (Y1 - Y0));
    setHoverYear(year >= Y0 && year <= Y1 ? year : null);
  };

  return (
    <div className="century-wall">
      <svg ref={svgRef} viewBox={`0 0 ${W} ${H}`} role="img"
           aria-label="Yearly revenue by channel group, 1912 to 2026, in 2026 dollars"
           onMouseMove={onMove} onMouseLeave={() => setHoverYear(null)}>
        {/* attendance shocks as shaded bands, under everything */}
        {shocks.map((s) => (
          <rect key={s.name} x={px(s.from_year)} y={TOP}
                width={Math.max(2, px(s.to_year) - px(s.from_year))} height={H - TOP - BOTTOM}
                className="wall-shock">
            <title>{s.name}</title>
          </rect>
        ))}
        {/* the stacked bands, 2px paper gap between fills */}
        {paths.map((p) => (
          <path key={p.key} d={p.d} fill={p.hue} stroke="var(--paper-raised)" strokeWidth="2">
            <title>{p.label}</title>
          </path>
        ))}
        {/* era boundaries: recessive rules + names along the top */}
        {eras.map((e) => (
          <g key={e.era_id}>
            <line x1={px(e.from_year)} y1={TOP - 4} x2={px(e.from_year)} y2={H - BOTTOM}
                  className="wall-era-rule" />
            <text x={px(e.from_year) + 3} y={TOP - 8} className="wall-era-name">
              {e.name.replaceAll("_", " ")}
            </text>
          </g>
        ))}
        {/* crosshair */}
        {hover && (
          <line x1={px(hover.year)} y1={TOP} x2={px(hover.year)} y2={H - BOTTOM}
                className="wall-crosshair" />
        )}
        {/* year axis, sparse */}
        {[1912, 1930, 1950, 1970, 1990, 2010, 2026].map((y) => (
          <text key={y} x={px(y)} y={H - 8} className="wall-year">{y}</text>
        ))}
      </svg>
      {hover && hover.parts.length > 0 && (
        <div className="wall-tooltip" style={{ left: `${(px(hover.year) / W) * 100}%` }}>
          <div className="wt-year">{hover.year} · ${(hover.total / 1000).toFixed(2)}B total (2026 $)</div>
          {hover.parts.map((p) => (
            <div key={p.key} className="wt-row">
              <span className="wt-swatch" style={{ background: p.hue }} />
              {p.label}: ${p.v >= 1000 ? `${(p.v / 1000).toFixed(2)}B` : `${p.v.toFixed(0)}M`}
            </div>
          ))}
        </div>
      )}
      <div className="wall-legend">
        {GROUPS.map((g) => (
          <span key={g.key} className="wl-item">
            <span className="wt-swatch" style={{ background: g.hue }} />{g.label}
          </span>
        ))}
        <span className="wl-note">
          yearly revenue in 2026 dollars · era rules · shaded bands are attendance shocks
        </span>
      </div>
    </div>
  );
}
