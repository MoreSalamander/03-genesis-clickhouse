import { Finding } from "@/lib/api";

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

export function Findings({ findings }: { findings: Finding[] }) {
  if (findings.length === 0) return <div className="hint">Verification pending…</div>;
  return (
    <div>
      {findings.map((finding) => (
        <div className="finding" key={finding.id}>
          <span className={`chip ${finding.state}`}>{GLYPH[finding.state]}</span>
          <div className="body">
            <div className="domain">{finding.domain.replace("_", " ")}</div>
            <div className="statement">{finding.statement}</div>
            <div className="basis">{finding.basis}</div>
            {Object.keys(finding.stats).length > 0 && (
              <div className="stats">{statLine(finding.stats)}</div>
            )}
          </div>
        </div>
      ))}
    </div>
  );
}
