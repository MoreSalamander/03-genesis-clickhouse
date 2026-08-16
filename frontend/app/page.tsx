"use client";
import { useCallback, useEffect, useRef, useState } from "react";
import {
  getCorpus,
  getEvents,
  getInvestigation,
  getStatus,
  launchInvestigation,
  listInvestigations,
  sendDecision,
  Investigation,
  InvestigationSummary,
  SystemStatus,
} from "@/lib/api";
import { QueryLedger } from "@/components/QueryLedger";
import { Findings } from "@/components/Findings";
import { Interpretations } from "@/components/Interpretations";
import { SimulationPanel } from "@/components/SimulationPanel";
import { RecommendationCard } from "@/components/RecommendationCard";
import { Elapsed, EmptyState, Note, Pulse, RuntimeBar, cascade, proofItems, proofState } from "@/lib/alive";

const STAGES = ["PLANNING", "ANALYZING", "VERIFYING", "SIMULATING", "RECOMMENDED", "DECIDED"];
const TERMINAL = new Set(["PROMOTED", "REJECTED", "INCOMPLETE"]);
// Stages where the analyst is actually working. RECOMMENDED waits on the
// Studio Head, so it carries no clock and no shimmer.
const WORKING = new Set(["PLANNING", "ANALYZING", "VERIFYING", "SIMULATING"]);
const DEFAULT_QUESTION = "Should we greenlight 'Nebula Frontier 2' at $45M for a Q2 release?";

export default function Workbench() {
  const [status, setStatus] = useState<SystemStatus | null>(null);
  const [corpus, setCorpus] = useState<{ t: string; n: number }[]>([]);
  const [question, setQuestion] = useState(DEFAULT_QUESTION);
  const [active, setActive] = useState<Investigation | null>(null);
  const [history, setHistory] = useState<InvestigationSummary[]>([]);
  const [events, setEvents] = useState<Record<string, unknown>[]>([]);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const activeId = useRef<string | null>(null);

  const refresh = useCallback(async () => {
    try {
      const [s, list, evs] = await Promise.all([getStatus(), listInvestigations(), getEvents(40)]);
      setStatus(s);
      setHistory(list);
      setEvents(evs.reverse());
      if (activeId.current) {
        setActive(await getInvestigation(activeId.current));
      }
    } catch {
      setStatus(null);
    }
  }, []);

  useEffect(() => {
    refresh();
    getCorpus().then((c) => setCorpus(c.tables)).catch(() => setCorpus([]));
    const timer = setInterval(refresh, 4000); // live workbench; self-heals when the API returns
    return () => clearInterval(timer);
  }, [refresh]);

  const launch = async () => {
    setBusy(true);
    setError("");
    try {
      const res = await launchInvestigation(question);
      activeId.current = res.id;
      await refresh();
    } catch (err) {
      setError(String(err instanceof Error ? err.message : err));
    } finally {
      setBusy(false);
    }
  };

  const decide = async (decision: string, note: string) => {
    if (!active) return;
    setBusy(true);
    setError("");
    try {
      await sendDecision(active.id, decision, note);
      await refresh();
    } catch (err) {
      setError(String(err instanceof Error ? err.message : err));
    } finally {
      setBusy(false);
    }
  };

  const open = async (id: string) => {
    activeId.current = id;
    try {
      setActive(await getInvestigation(id));
    } catch (err) {
      setError(String(err instanceof Error ? err.message : err));
    }
  };

  const stageIndex = active
    ? TERMINAL.has(active.status) ? STAGES.length - 1 : STAGES.indexOf(active.status)
    : -1;
  const tables = corpus.filter((row) => row.t && Number.isFinite(Number(row.n)));
  const working = !!active && WORKING.has(active.status);
  const heartbeat = `${history.length}|${active?.status ?? ""}|${active?.queries.length ?? 0}|${events.length}`;

  return (
    <div className="frame">
      <header className="masthead">
        <div>
          <h1><a href="/">GENESIS OS — INSTITUTIONAL INTELLIGENCE</a></h1>
          <div className="dept">Convergence Studios · Analytical Cognition · ClickHouse track</div>
        </div>
        <div className="mode">
          {status ? (
            <>
              <div><Pulse signal={heartbeat} /> ClickHouse MCP {(() => {
                const s = proofState(status.runtime_proof, "clickhouse", status.clickhouse_live);
                return s === "LIVE" ? <span className="live">LIVE</span> : s;
              })()}</div>
              <div>Gemini {status.gemini_live ? <span className="live">LIVE</span> : "MOCK"}</div>
            </>
          ) : (
            "backend offline — start uvicorn on :8020"
          )}
        </div>
      </header>

      <div className="corpus-strip">
        <span>CORPUS</span>
        {/* In mock mode /corpus answers with a placeholder row carrying neither a
            table name nor a count — render counts only, never a bare NaN. */}
        {tables.length === 0 && <span>— (mock fixtures)</span>}
        {tables.map((row) => (
          <span key={row.t}><b>{Number(row.n).toLocaleString()}</b> {row.t}</span>
        ))}
      </div>

      <div className="question-bar">
        <label>Studio Head question — what should our history tell us?</label>
        <div className="question-row">
          <input
            value={question}
            onChange={(e) => setQuestion(e.target.value)}
            onKeyDown={(e) => e.key === "Enter" && !busy && launch()}
            placeholder="Ask the corpus…"
          />
          <button onClick={launch} disabled={busy}>OPEN INVESTIGATION</button>
        </div>
        {error && <Note tone="bad">{error}</Note>}
      </div>

      {!active && history.length === 0 && (
        <div style={{ margin: "26px 0" }}>
          <EmptyState
            eyebrow="Institutional Intelligence · ClickHouse track"
            title="Ten years of studio history, and every number auditable."
            lead="The analyst plans hypotheses, writes the SQL itself, runs it against the corpus
                  through the ClickHouse MCP server, and verifies each finding by rule rather than by
                  narration. Readings that disagree are kept side by side as CONTESTED — the ledger
                  preserves the argument instead of averaging it away. The question above is loaded
                  and ready."
            action={
              <button className="btn approve" onClick={launch} disabled={busy}>
                {busy ? "OPENING…" : "START HERE — OPEN THE INVESTIGATION"}
              </button>
            }
          />
        </div>
      )}

      {active && (
        <>
          <div className="stage-rail">
            {STAGES.map((stage, i) => {
              const here = i === stageIndex;
              return (
                <div
                  key={stage}
                  className={
                    "stage" +
                    (i < stageIndex ? " done" : "") +
                    (here ? " current" : "") +
                    (here && working ? " alive-active" : "")
                  }
                >
                  {stage === "DECIDED" && TERMINAL.has(active.status) ? active.status : stage}
                  {here && working && <> <Elapsed stage={active.status} running={working} /></>}
                </div>
              );
            })}
          </div>
          {active.round > 1 && (
            <div className="round-flag">
              ROUND {active.round} — deeper analysis requested: {active.deeper_guidance.join(" · ")}
            </div>
          )}

          <div className="two-col">
            <div>
              <section className="section">
                <h2>Query ledger <span className="count">{active.queries.length} executed · every number auditable</span></h2>
                <QueryLedger queries={active.queries} />
              </section>

              <section className="section">
                <h2>Findings <span className="count">rule-derived verification, computed in code</span></h2>
                <Findings findings={active.findings} queries={active.queries}
                          interpretations={active.interpretations} />
              </section>

              {active.interpretations.length > 0 && (
                <section className="section">
                  <h2>Competing interpretations <span className="count">contested readings preserved</span></h2>
                  <Interpretations interpretations={active.interpretations} />
                </section>
              )}

              {active.simulation && (
                <section className="section">
                  <h2>Scenario simulation <span className="count">seeded bootstrap · {active.simulation.n_runs} runs</span></h2>
                  <SimulationPanel sim={active.simulation} />
                </section>
              )}

              {active.recommendation && (
                <section className="section">
                  <h2>Recommendation</h2>
                  <RecommendationCard inv={active} busy={busy} onDecide={decide} />
                </section>
              )}
              {active.status === "INCOMPLETE" && (
                <Note tone="bad">
                  INCOMPLETE — {active.incomplete_reason ?? "substrate unavailable"}; numbers are never fabricated.
                </Note>
              )}
            </div>

            <aside>
              <section className="section">
                <h2>Event fabric</h2>
                <div className="event-feed">
                  {events.map((ev, i) => (
                    <div className="ev" key={i}>
                      <b>{String(ev.event)}</b>{" "}
                      {String((ev as { investigation_id?: string }).investigation_id ?? "")}
                    </div>
                  ))}
                </div>
              </section>
            </aside>
          </div>
        </>
      )}

      <section className="section alive-cascade">
        <h2>Investigation ledger <span className="count">{history.length} on record</span></h2>
        {history.map((item, i) => (
          <div className="history-item" style={cascade(i)} key={item.id} onClick={() => open(item.id)}>
            <span className="q">{item.question}</span>
            <span className="s">
              {item.status} · r{item.round} · {item.queries} queries
              {item.confidence != null ? ` · ${Math.round(item.confidence * 100)}%` : ""}
            </span>
          </div>
        ))}
        {history.length === 0 && <div className="hint">No investigations yet — open one above.</div>}
      </section>

      <RuntimeBar items={proofItems(status?.runtime_proof, [
        ["gemini", "Gemini"],
        ["clickhouse", "ClickHouse MCP"],
        ["temporal", "Temporal"],
        ["datahub", "DataHub"],
      ])} />
    </div>
  );
}
