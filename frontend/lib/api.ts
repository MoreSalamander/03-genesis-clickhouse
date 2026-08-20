import type { RuntimeProof } from "@/lib/alive";

// Typed client for the Institutional Intelligence API (via the runtime proxy).

export interface SystemStatus {
  system: string;
  banner: string;
  clickhouse_live: boolean;
  gemini_live: boolean;
  investigations: number;
  /** Substrate states for the runtime-proof footer (app/runtime_proof.py). */
  runtime_proof?: RuntimeProof;
}

export interface Finding {
  id: string;
  domain: string;
  statement: string;
  state: "VERIFIED" | "REGIME" | "WEAK" | "CONTESTED" | "INSUFFICIENT";
  basis: string;
  era_range?: string | null;
  era_agreement?: Record<string, number>;
  stats: Record<string, number>;
  evidence_query_ids: string[];
}

export interface AnalyticalQuery {
  id: string;
  hypothesis_id: string;
  domain: string;
  purpose: string;
  sql: string;
  columns: string[];
  rows: unknown[][];
  row_count: number;
  elapsed_ms: number;
  repairs: number;
  error: string | null;
  explain?: string;
  computed_stats: Record<string, number>;
}

export interface Interpretation {
  id: string;
  label: string;
  stance: string;
  narrative: string;
  cited_query_ids: string[];
  cited_finding_ids: string[];
}

export interface Simulation {
  scenario: string;
  baseline: Record<string, number>;
  projected: Record<string, number>;
  delta: Record<string, number>;
  n_runs: number;
  seed: number;
  narrative: string;
  params?: Record<string, unknown>;
  surface?: Record<string, { p10?: number; p50?: number; p90?: number; cohort_n?: number }>;
}

export interface Recommendation {
  action: string;
  rationale: string;
  confidence: number;
  coverage: Record<string, number>;
  caveats: string[];
}

export interface Decision {
  decision: string;
  note: string;
  at: string;
}

export interface Investigation {
  id: string;
  question: string;
  status: string;
  round: number;
  deeper_guidance: string[];
  hypotheses: { id: string; domain: string; statement: string; rationale: string }[];
  queries: AnalyticalQuery[];
  findings: Finding[];
  interpretations: Interpretation[];
  simulation: Simulation | null;
  recommendation: Recommendation | null;
  decisions: Decision[];
  promotion: { datahub_urns: string[] } | null;
  escalated: boolean;
  incomplete_reason: string | null;
  created_at: string;
  updated_at: string;
}

export interface InvestigationSummary {
  id: string;
  question: string;
  status: string;
  round: number;
  queries: number;
  coverage: Record<string, number>;
  confidence: number | null;
  action: string | null;
  created_at: string;
}

async function req<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(`/api${path}`, {
    ...init,
    headers: { "content-type": "application/json", ...(init?.headers ?? {}) },
    cache: "no-store",
  });
  if (!res.ok) {
    let detail = res.statusText;
    try {
      const body = await res.json();
      detail = body.detail ?? JSON.stringify(body);
    } catch { /* keep statusText */ }
    throw new Error(detail);
  }
  return res.json();
}

export const getStatus = () => req<SystemStatus>("/status");
export const getCorpus = () => req<{ tables: { t: string; n: number }[]; mode: string }>("/corpus");
export const listInvestigations = () => req<InvestigationSummary[]>("/investigations");
export const getInvestigation = (id: string) => req<Investigation>(`/investigations/${id}`);
export const launchInvestigation = (question: string) =>
  req<{ id: string; execution: string }>("/investigations", {
    method: "POST",
    body: JSON.stringify({ question }),
  });
export const sendDecision = (id: string, decision: string, note: string) =>
  req<{ status: string }>(`/investigations/${id}/decision`, {
    method: "POST",
    body: JSON.stringify({ decision, note }),
  });
export const getEvents = (limit = 60) => req<Record<string, unknown>[]>(`/events?limit=${limit}`);

export interface QueryCost {
  read_rows: number; read_bytes: number; memory_bytes: number;
  duration_ms: number; n_columns: number; years_touched: string[];
}
export const getInvestigationCosts = (id: string) =>
  req<Record<string, QueryCost>>(`/investigations/${id}/costs`);
export const getShowcaseCosts = () => req<Record<string, QueryCost>>("/showcase/costs");
export interface SufficiencyChannel {
  channel: string; from_year: number; to_year: number; titles: number; has_completion: number;
}
export const getSufficiency = () =>
  req<{ channels: SufficiencyChannel[]; corpus: { founded?: number; titles?: number }; mode: string }>("/sufficiency");
export const postRequery = (queryId: string) =>
  req<{ original_rows: number; fresh_rows: number; reproduced: boolean; elapsed_ms: number }>(
    `/requery/${queryId}`, { method: "POST" });
