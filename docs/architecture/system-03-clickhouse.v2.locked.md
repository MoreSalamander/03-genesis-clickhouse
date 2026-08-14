# System 03 — ClickHouse — Architecture Review V2 (LOCKED — approved by Studio Head 2026-08-13)

> Builder-drafted per the agreed process (only 01/02 completed architect-chat reviews). Follows the
> locked review protocol: technology deep dive first, then the proposed architecture. On approval,
> **this exact document locks** — not a summary of it. Claims are classified as
> **VERIFIED REQUIREMENT** / **ARCHITECTURAL DECISION** / **RECOMMENDATION** / **INFERENCE**.
> Locked boundaries honored throughout (Handoff §4): ClickHouse provides analytical evidence; it is
> NOT the global memory system and replaces nothing in the preserved stack.

---

## PART 1 — TECHNOLOGY DEEP DIVE

### 1.1 What ClickHouse is

An open-source, column-oriented OLAP database built for real-time analytical queries over very
large event volumes. Data is stored by column and processed with vectorized execution, so a query
that aggregates three columns across 500 million rows reads only those three columns — at
compression ratios and scan speeds that make sub-second, interactive aggregation over years of
history routine.

### 1.2 What it actually does

- **MergeTree storage engines**: append-heavy immutable event tables, partitioned by time,
  ordered by key; background merges; specialized variants (Summing/Aggregating/Replacing) for
  continuous rollups.
- **Analytical SQL**: window functions, quantiles, correlations/stddev, arrays + lambdas,
  funnel/retention functions, `GROUP BY` at billions-of-rows scale.
- **Materialized views**: rollups computed at insert time (e.g., monthly cost per project) so
  agent queries stay fast forever.
- **Low-latency iteration**: an agent can run 10–15 exploratory queries in a single reasoning
  loop and stay interactive — the property that makes *agentic* analytics feasible.

### 1.3 Why a film studio needs it

A studio is an event engine: production telemetry (shot iterations, render hours, overtime),
money movement (ledger lines per cost center per day), audience behavior (views, completion,
revenue by title/platform/territory/day), distribution activity. Institutional questions —
*"do sci-fi sequels at this budget class overrun?"*, *"what does a Q4 release cost us vs Q2?"* —
are aggregations over **years** of those events. That corpus and those computations are what
ClickHouse owns.

### 1.4 What ClickHouse does that the rest of the stack does not

| vs | Their job | ClickHouse's job |
|---|---|---|
| PostgreSQL | current durable state, transactions (missions/investigations) | scan/aggregate the historical event corpus interactively |
| DataHub | what data *is*, where it came from, lineage, promoted knowledge | *compute* the analytical results that may become knowledge |
| Qdrant | semantic similarity | numeric aggregation; no vectors needed |
| OpenSearch | text relevance over evidence | columnar math over events; not text |
| Neo4j | relationship traversal | wide aggregations relationships can't express |
| Prometheus/Grafana | *now*-focused operational metrics, bounded retention | unbounded business-event history, arbitrary dimensions |
| BigQuery | batch warehouse economics | low-latency interactive loops for agents; self-hostable; **and it is the partner requirement** |

### 1.5 Hackathon requirements

- **VERIFIED REQUIREMENT** (supplied Official Rules): the project must actively use ClickHouse at
  runtime **via the official ClickHouse MCP server (`mcp-clickhouse`)**, connected to ClickHouse
  Cloud **or a self-hosted cluster**. ClickHouse Agent Skills during development optional.
  Google Cloud AI only; public OSS repo; hosted URL; ≤3-min video.
- **INFERENCE**: judges verify the MCP integration is in the executed code path, as with the
  other tracks. **Action**: re-verify live Devpost track text before build/submission (standing flag).

### 1.6 What ClickHouse must NOT own here (locked, Handoff §4)

Not the global memory system; not context/provenance (DataHub), durable app state (PostgreSQL),
semantics (Qdrant), objects (MinIO), text search (OpenSearch), workflows (Temporal), or the event
fabric (NATS). It owns the **institutional event corpus and analytical computation over it**.

---

## PART 2 — PROPOSED ARCHITECTURE

### 2.1 Identity

**SYSTEM:** Genesis OS — Institutional Intelligence
**FUNCTION:** Analytical memory of Convergence Studios
**PARTNER:** ClickHouse
**MISSION:** Turn the studio's accumulated event history into statistically defensible evidence,
findings, and recommendations.
**STUDIO HEAD QUESTION:** *"What does our accumulated history tell us — and what happens if we
change this assumption?"*

### 2.2 Cognitive hierarchy (ARCHITECTURAL DECISION — revises the unlocked Appendix E hypothesis)

Appendix E proposed seven domains as an explicit starting point requiring review. Consolidated to
four + one cross-cutting, because agents exist only where they own distinct cognition (locked
principle) and Marketing/Distribution/Audience/Performance overlap heavily:

```
INSTITUTIONAL COGNITION (Executive)
├── PRODUCTION ECONOMICS      schedules, overruns, render/resource economics
├── AUDIENCE & DISTRIBUTION   viewing, completion, revenue by platform/territory, windows, marketing response
├── FINANCIAL PERFORMANCE     budgets vs actuals, ROI by class/genre, cash curves
├── OPERATIONAL HISTORY       incidents, pipeline throughput, ops events (live feed from 01/02 fabrics)
└── STRATEGIC PATTERN (cross-cutting)  multi-domain patterns, what-if scenarios
```

### 2.3 Agent organization

| Agent | Owns | Permissions |
|---|---|---|
| **Institutional Intelligence Executive** | the analytical objective; plan → synthesis → recommendation | read, analyze, recommend |
| **Analytical Planner** | decomposing a question into testable hypotheses + query intents per domain | read, analyze |
| **Domain Analysts** (4, cognitive roles — instantiated per investigation) | domain framing + interpretation of that domain's results | read, analyze |
| **Query Engineer** | schema-grounded SQL generation (Gemini) + repair; **SELECT-only, enforced in code** | read |
| **Statistical Verification Agent** | verification states computed IN CODE: sample size, dispersion, effect size | read, analyze |
| **Scenario/Simulation Agent** | what-if projections: parameterized re-aggregation + seeded Monte-Carlo-lite computed in code | read, analyze |
| Studio Head (human) | authorization: approve / reject / request deeper analysis | authorize |

**The anti-"SQL chatbot" mechanics** (this is the heart of it):
1. Investigations are multi-step: baseline → cohort → comparison → trend → (optional) simulation,
   each an auditable query with results attached as evidence.
2. **Verification states are rule-derived, never model-asserted** (mirror of 01's §6):
   - `VERIFIED` — n ≥ 30 cohort, effect > noise (computed), stable across the comparison split
   - `WEAK` — signal present but under-powered (n < 30 or effect within dispersion)
   - `CONTESTED` — two analyses disagree (e.g., sequel premium vs franchise fatigue) —
     **preserved, never resolved by Gemini**
   - `INSUFFICIENT` — the corpus can't answer; said plainly
3. Recommendation confidence is a function of verification coverage — not vibes.
4. Gemini writes SQL, frames interpretations, and narrates; **all numbers come from ClickHouse,
   all statistics are computed in Python** — cognition never invents a digit.

### 2.4 Data architecture (`genesis_institutional`)

Dimensions: `projects` (id, title, type, genre, budget_class, budget, greenlit_at, released_at,
release_window, is_sequel, status).

Facts (MergeTree, `PARTITION BY toYYYYMM(at)`, ordered by (project/title, at)):
- `production_events` — dept, event_type, metric, value (schedule slips, render hours, overtime)
- `financial_ledger` — cost_center, category, planned, actual
- `audience_performance` — title, platform, territory, date, views, completion, revenue
- `distribution_events` — deals, windows, platform launches
- `ops_events` — **live mirror of the NATS fabrics** (genesis.signal/ops.events) via a
  consume-only ingest worker: institutional memory grows from the studio's own operation.
  (Optional presence — 03 runs fully without 01/02; independence preserved.)

Materialized views: monthly rollups per project/domain. **Seeded corpus** (ARCHITECTURAL
DECISION): ~10 years, ~60 projects, ~5–10M event rows, generated by a deterministic seeded
generator with *engineered correlations* (overrun patterns by genre/scale, seasonality, sequel
economics, platform decay curves) so analyses are reproducible and demonstrably non-trivial.

### 2.5 Runtime integration (VERIFIED REQUIREMENT path)

```
Agents ──MCP Python SDK──▶ official mcp-clickhouse server (:8687, streamable-http)
                                   │ run_select_query · list_tables · list_databases
                                   ▼
                         ClickHouse (self-hosted container; HTTP :8123, native :19000)
                         — ClickHouse Cloud swap = connection env only
```

MCP connects as a **read-only ClickHouse user**; the ingest worker and seeder use a separate
writer user, never through MCP. Schema grounding for the Query Engineer comes from `list_tables`
at runtime (live introspection, not hardcoded prompts).

### 2.6 The investigation loop (locked global loop, instantiated)

Question → scope/context (DataHub graph + project dims) → analytical plan (hypotheses) →
iterative SQL via MCP → `AnalyticalEvidence{sql, result_table, computed_stats}` → statistical
verification → **competing interpretations** (≥2, each citing evidence) → findings → optional
simulation → recommendation (confidence = verification coverage) → **Studio Head signal**
(approve / reject / request deeper analysis — deeper loops back with guidance) → promotion →
observation.

### 2.7 Preserved-stack responsibilities (production directive — all deployed, owned by 03)

PostgreSQL :5435 (durable investigation state) · NATS :4225 (`genesis.institutional.events` +
ops ingest) · Temporal :7235/UI :8235 (durable InvestigationWorkflow with the human-decision
signal, 02's proven pattern) · Redis :6382 (investigation latch) · **DataHub** (CH tables
registered as datasets with lineage; VERIFIED findings promoted as institutional knowledge
entities linked to their queries) · MinIO (full result-set snapshots as evidence objects) ·
OTel → **Cloud Trace** (no Grafana of its own — independence; spans: gemini.generate,
clickhouse.mcp.*) · Docker. Ports per the audited map; ClickHouse native remapped to
:19000 (MinIO owns :9000).

### 2.8 Gemini / Google Cloud roles

Gemini (`gemini-flash-latest`, Vertex, global): analytical planning, schema-grounded SQL
generation + repair (≤2 attempts, re-grounded), interpretation generation, narrative synthesis.
Google Cloud: Vertex AI, Cloud Run (API + mcp-clickhouse sidecar + console), Secret Manager,
Cloud Trace. Hosted ClickHouse for the public URL: ClickHouse Cloud trial (user account) **or**
GCE VM — *user decision at deploy time; local-first until then.*

### 2.9 Human boundary, failure, security

- Autonomous: query, analyze, verify, simulate, draft recommendations. Human-gated: every
  recommendation; any consequential action. "Request deeper analysis" is a first-class decision.
- Failures: ClickHouse unreachable → INCOMPLETE (numbers are never fabricated); SQL errors →
  bounded repair; under-powered analysis → finding stays WEAK/INSUFFICIENT and cannot raise
  confidence; conflicting analyses → CONTESTED, preserved to the Studio Head.
- Security: read-only MCP user; SELECT-guard in code; secrets in env/Secret Manager; full audit
  via events + OTel + evidence objects.

### 2.10 Repository & console

`03-genesis-clickhouse/` mirrors the proven production skeleton: `app/` (agents/{executive,
planner, analysts, query, verification, simulation}, tools/{clickhouse_mcp, google}, workflows/
{temporal}, memory, knowledge/{datahub, objects}, events, governance, api), `ingest/` (NATS→CH
worker), `seed/` (corpus generator), `ops/` (compose: clickhouse, mcp-clickhouse, postgres, nats,
temporal+ui, redis), `frontend/` (console :3020 — a third distinct design: analytical
workbench — question bar, live query log with SQL + row counts, findings with stat chips
[✓ VERIFIED / ~ WEAK / ⚠ CONTESTED / ∅ INSUFFICIENT], competing interpretations side-by-side,
simulation panel, recommendation card with approve/reject/deeper), tests, Dockerfiles, MIT, README
with runtime-proof links. API :8020.

### 2.11 Demo (≤3 min)

*"Should we greenlight 'Nebula Frontier 2' at $45M for a Q2 release?"* — cohort of comparable
sci-fi titles ($30–60M) → overrun pattern by budget class (VERIFIED) → sequel economics
(**CONTESTED**: premium vs fatigue, both preserved with evidence) → release-window seasonality
(VERIFIED) → simulation: Q2 vs Q4 shift on the cohort's curves → recommendation with confidence →
Studio Head approves → finding promoted to DataHub with full query lineage. Every stage visibly
runs real SQL through the official MCP server.

### 2.12 Events

`investigation.started/completed/incomplete`, `analysis.executed`, `finding.verified/contested/
insufficient`, `simulation.completed`, `recommendation.created`, `authorization.decided`,
`knowledge.promoted` — on `genesis.institutional.events` + JSONL audit.

### 2.13 Explicit deviations from the (unlocked) Appendix E hypotheses

1. Seven proposed domains consolidated to four + one cross-cutting (rationale in 2.2).
2. Proposed roster refined: "Pattern Discovery" and "Performance Analysis" fold into Domain
   Analysts + the Statistical Verification Agent; "Explanation" folds into the Executive's
   synthesis (agents only where cognition is owned).
3. Everything else follows the hypothesis flow (Query→Analyze→Discover→Explain→Simulate→Recommend).

---

**APPROVAL:** On the Studio Head's approval, this exact document locks as the canonical System 03
architecture (renamed `system-03-clickhouse.v2.locked.md`). Requested changes will be applied and
re-presented before locking.
