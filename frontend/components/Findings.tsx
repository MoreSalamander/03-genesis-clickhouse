import { AnalyticalQuery, Finding, Interpretation } from "@/lib/api";
import { cascade } from "@/lib/alive";

const GLYPH: Record<Finding["state"], string> = {
  VERIFIED: "✓ VERIFIED",
  WEAK: "~ WEAK",
  CONTESTED: "⚠ CONTESTED",
  INSUFFICIENT: "∅ INSUFFICIENT",
};

function statLine(stats: Record<string, number>): string {
  const parts: string[] = [];
  if (stats.effect !== undefined) parts.push(`effect ${stats.effect}`);
  if (stats.effect_over_noise !== undefined) parts.push(`effect/noise ${stats.effect_over_noise}`);
  if (stats.n_a !== undefined) parts.push(`n ${stats.n_a}/${stats.n_b}`);
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
function EffectGauge({ ratio }: { ratio: number }) {
  // Ratios here run from under 1 to nearly 30, so a linear dial pegs every
  // strong finding at full and stops distinguishing anything. Log scaling keeps
  // the 1.0 threshold at a fixed mark while 3.6×, 11.5× and 27× stay apart.
  const MAX = 30;
  const pct = (v: number) =>
    (Math.log10(Math.min(Math.max(v, 0), MAX) + 1) / Math.log10(MAX + 1)) * 100;
  const passes = ratio > 1;
  return (
    <div className="gauge"
         title={`effect/noise ${ratio} — the verification threshold is 1.0 (log scale to ${MAX}×)`}>
      <span className="gauge-track">
        <span className={`gauge-fill ${passes ? "pass" : "under"}`} style={{ width: `${pct(ratio)}%` }} />
        <span className="gauge-threshold" style={{ left: `${pct(1)}%` }} />
      </span>
      <span className={`gauge-num ${passes ? "pass" : "under"}`}>
        {ratio.toFixed(2)}× effect/noise — {passes ? "meets" : "below"} threshold
      </span>
    </div>
  );
}

function PlainFinding({ finding }: { finding: Finding }) {
  const ratio = finding.stats.effect_over_noise;
  return (
    <div className="finding">
      <span className={`chip ${finding.state}`}>{GLYPH[finding.state]}</span>
      <div className="body">
        <div className="domain">{finding.domain.replace("_", " ")}</div>
        <div className="statement">{finding.statement}</div>
        <div className="basis">{finding.basis}</div>
        {Object.keys(finding.stats).length > 0 && (
          <div className="stats">{statLine(finding.stats)}</div>
        )}
        {ratio !== undefined && <EffectGauge ratio={ratio} />}
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
            : <PlainFinding finding={finding} />}
        </div>
      ))}
    </div>
  );
}
