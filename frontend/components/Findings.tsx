import { useState } from "react";
import { AnalyticalQuery, Finding, Interpretation } from "@/lib/api";
import { cascade } from "@/lib/alive";

const GLYPH: Record<Finding["state"], string> = {
  VERIFIED: "✓ VERIFIED",
  REGIME: "◐ REGIME",
  WEAK: "~ WEAK",
  CONTESTED: "⚠ CONTESTED",
  INSUFFICIENT: "∅ INSUFFICIENT",
};

function statLine(stats: Record<string, number>): string {
  const parts: string[] = [];
  if (stats.effect !== undefined) parts.push(`effect ${stats.effect}`);
  if (stats.effect_over_noise !== undefined) parts.push(`effect/noise ${stats.effect_over_noise}`);
  if (stats.titles_a !== undefined) parts.push(`titles ${stats.titles_a}/${stats.titles_b}`);
  else if (stats.n_a !== undefined) parts.push(`n ${stats.n_a}/${stats.n_b}`);
  if (stats.n_eras_data !== undefined)
    parts.push(`eras ${stats.n_eras_agree ?? 0}/${stats.n_eras_data} agree`);
  if (stats.analyses !== undefined) parts.push(`${stats.analyses} disagreeing analyses`);
  return parts.join(" · ");
}

/** One side of a contested finding: the analysis, its effect, its direction, and
 *  whichever competing reading cited it. Nothing here is averaged or ranked —
 *  the two sides are rendered as equals because the ledger keeps them as equals. */
function Side({ query, interpretation }: {
  query: AnalyticalQuery;
  interpretation?: Interpretation;
}) {
  const effect = query.computed_stats?.effect;
  const direction = query.computed_stats?.direction ?? 0;
  const nA = query.computed_stats?.n_a;
  const nB = query.computed_stats?.n_b;
  const up = direction > 0;
  return (
    <div className={`contested-side ${up ? "up" : "down"}`}>
      <div className="side-head">
        {/* The sign of the computed effect, stated as the sign — the console
            does not translate it into a domain claim the rules never made. */}
        <span className="dir">{up ? "▲ positive direction" : "▼ negative direction"}</span>
        <span className="qid">{query.id}</span>
      </div>
      <div className="purpose">{(query.purpose || query.id).replace("canonical:", "")}</div>
      <div className="effect">
        {effect !== undefined ? (up ? "+" : "") + effect : "—"}
        <span className="lbl">effect</span>
      </div>
      {nA !== undefined && nB !== undefined && (
        <div className="n">n {nA} / {nB}</div>
      )}
      {interpretation && (
        <div className="reading">
          <div className="rlabel">{interpretation.label}</div>
          {interpretation.stance && <div className="rstance">{interpretation.stance}</div>}
          <div className="rnarrative">{interpretation.narrative}</div>
        </div>
      )}
    </div>
  );
}

/** A contested finding rendered as a split screen. Preserving the disagreement
 *  rather than resolving it is this system's thesis, so it gets the loudest
 *  layout on the page instead of a one-line basis string. */
function ContestedFinding({ finding, queries, interpretations }: {
  finding: Finding;
  queries: AnalyticalQuery[];
  interpretations: Interpretation[];
}) {
  const analyses = finding.evidence_query_ids
    .map((id) => queries.find((q) => q.id === id))
    .filter((q): q is AnalyticalQuery => !!q && q.computed_stats?.effect !== undefined);

  // The two extremes of the disagreement — the strongest case each way.
  const positive = analyses.filter((q) => (q.computed_stats?.direction ?? 0) > 0);
  const negative = analyses.filter((q) => (q.computed_stats?.direction ?? 0) < 0);
  const readingFor = (q: AnalyticalQuery) =>
    interpretations.find((i) => i.cited_query_ids.includes(q.id));

  // Without two opposing analyses to show, fall back rather than fabricate a split.
  if (positive.length === 0 || negative.length === 0) {
    return <PlainFinding finding={finding} />;
  }

  return (
    <div className="contested">
      <div className="contested-head">
        <span className="chip CONTESTED">{GLYPH.CONTESTED}</span>
        <div>
          <div className="domain">{finding.domain.replace("_", " ")}</div>
          <div className="statement">{finding.statement}</div>
        </div>
      </div>
      <div className="contested-split">
        <Side query={positive[0]} interpretation={readingFor(positive[0])} />
        <div className="versus" aria-hidden="true">vs</div>
        <Side query={negative[0]} interpretation={readingFor(negative[0])} />
      </div>
      <div className="preserved-seal">
        ⚖ BOTH PRESERVED — the corpus supports either reading depending on how it is
        sliced. This ledger records the disagreement; it does not resolve it.
      </div>
      <div className="basis">{finding.basis}</div>
    </div>
  );
}

/** Effect-over-noise as a dial with the 1.0 verification threshold marked.
 *  This is ONE of the rules behind a state, never the verdict itself — a WEAK
 *  finding can clear this bar comfortably and still be WEAK on cohort size. The
 *  label names the criterion so a passing gauge beside a WEAK chip reads as the
 *  detail it is rather than a contradiction. */
function EffectGauge({ ratio, threshold }: { ratio: number; threshold: number }) {
  // Effect sizes are Cohen's-d shaped now (scale-free): the dial runs to 3d and
  // the threshold mark comes from the verifier itself (stats.threshold), so the
  // console can never drift from the policy that actually judged the finding.
  const MAX = Math.max(3, threshold * 6);
  const pct = (v: number) => (Math.min(Math.max(v, 0), MAX) / MAX) * 100;
  const passes = ratio > threshold;
  return (
    <div className="gauge"
         title={`effect size ${ratio} vs dispersion — the verification threshold is ${threshold}`}>
      <span className="gauge-track">
        <span className={`gauge-fill ${passes ? "pass" : "under"}`} style={{ width: `${pct(ratio)}%` }} />
        <span className="gauge-threshold" style={{ left: `${pct(threshold)}%` }} />
      </span>
      <span className={`gauge-num ${passes ? "pass" : "under"}`}>
        {ratio.toFixed(2)} effect size — {passes ? "meets" : "below"} the {threshold} bar
      </span>
    </div>
  );
}

function EraLens({ finding, queries }: { finding: Finding; queries: AnalyticalQuery[] }) {
  const [era, setEra] = useState<string | null>(null);
  const agreement = finding.era_agreement ?? {};
  if (Object.keys(agreement).length === 0) return null;
  const primary = finding.evidence_query_ids
    .map((id) => queries.find((q) => q.id === id))
    .filter((q): q is AnalyticalQuery => !!q)
    .sort((a, b) => (b.computed_stats?.effect_over_noise ?? 0) - (a.computed_stats?.effect_over_noise ?? 0))[0];
  const eraCol = primary?.columns.findIndex((c) => ["era", "era_name", "decade", "period", "regime"].includes(c.toLowerCase())) ?? -1;
  const eraRows = era && primary && eraCol >= 0
    ? primary.rows.filter((r) => String(r[eraCol]) === era).slice(0, 6) : [];
  return (
    <>
      <div className="era-strip" title="era-by-era direction — click an era to scope the numbers">
        {Object.entries(agreement).map(([e, sign]) => (
          <button key={e} className={`era-cell ${sign > 0 ? "agree" : "disagree"}${era === e ? " on" : ""}`}
                  onClick={() => setEra(era === e ? null : e)}
                  title={`${e.replaceAll("_", " ")}: ${sign > 0 ? "agrees" : "disagrees"} — click to scope`}>
            {e.replaceAll("_", " ")}
          </button>
        ))}
      </div>
      {era && primary && eraRows.length > 0 && (
        <div className="era-lens">
          <div className="el-head">
            scoped to <b>{era.replaceAll("_", " ")}</b> — {agreement[era] > 0 ? "agrees with" : "runs AGAINST"} the century direction
          </div>
          <table>
            <thead><tr>{primary.columns.map((c) => <th key={c}>{c}</th>)}</tr></thead>
            <tbody>{eraRows.map((r, i) => (
              <tr key={i}>{r.map((cell, j) => <td key={j}>{String(cell)}</td>)}</tr>
            ))}</tbody>
          </table>
        </div>
      )}
    </>
  );
}

function PlainFinding({ finding, queries = [] }: { finding: Finding; queries?: AnalyticalQuery[] }) {
  const ratio = finding.stats.effect_over_noise;
  return (
    <div className="finding">
      <span className={`chip ${finding.state}`}>{GLYPH[finding.state]}</span>
      <div className="body">
        <div className="domain">{finding.domain.replace("_", " ")}</div>
        <div className="statement">{finding.statement}</div>
        {finding.state === "REGIME" && finding.era_range && (
          <div className="era-range">true within: {finding.era_range.replaceAll("_", " ")}</div>
        )}
        <div className="basis">{finding.basis}</div>
        {Object.keys(finding.stats).length > 0 && (
          <div className="stats">{statLine(finding.stats)}</div>
        )}
        <EraLens finding={finding} queries={queries} />
        {ratio !== undefined && <EffectGauge ratio={ratio} threshold={finding.stats.threshold ?? 0.1} />}
      </div>
    </div>
  );
}

export function Findings({ findings, queries = [], interpretations = [] }: {
  findings: Finding[];
  queries?: AnalyticalQuery[];
  interpretations?: Interpretation[];
}) {
  if (findings.length === 0) return <div className="hint">Verification pending…</div>;
  // Contested findings sort to the top: tension is the thing worth looking at.
  const ordered = [...findings].sort(
    (a, b) => Number(b.state === "CONTESTED") - Number(a.state === "CONTESTED"),
  );
  return (
    <div className="alive-cascade">
      {ordered.map((finding, i) => (
        <div key={finding.id} style={cascade(i)}>
          {finding.state === "CONTESTED"
            ? <ContestedFinding finding={finding} queries={queries} interpretations={interpretations} />
            : <PlainFinding finding={finding} queries={queries} />}
        </div>
      ))}
    </div>
  );
}
