# Genesis OS — Institutional Intelligence

**ClickHouse track · Google Cloud Agentic Cinema Hackathon · Convergence Studios**

A standalone multi-agent analytical-cognition system for a film studio's ten years of
institutional history. It answers the Studio Head's question:

> *"What does our accumulated history tell us — and what happens if we change this assumption?"*

Not "chat with your database": investigations are multi-step analytical campaigns —
baseline → cohort → comparison → trend → simulation — where every number comes from
ClickHouse through the **official `mcp-clickhouse` MCP server**, every statistic is
computed in code, and every finding carries a rule-derived verification state
(`VERIFIED / WEAK / CONTESTED / INSUFFICIENT`). Conflicting analyses are preserved and
presented side-by-side, never silently resolved by the model.

```
Studio Head question
  → Analytical Planner (hypotheses per cognitive domain)
  → Query Engineer (Gemini writes SQL, schema-grounded, SELECT-only enforced in code)
  → official mcp-clickhouse server → ClickHouse (10y corpus, ~5M rows)
  → Statistical Verification (states computed in Python, never model-asserted)
  → Competing interpretations → Findings → Scenario simulation
  → Recommendation (confidence = verification coverage)
  → Studio Head: approve / reject / request deeper analysis   (Temporal signal)
  → VERIFIED knowledge promoted to DataHub with full query lineage
```

## Runtime proof (hackathon compliance)

| Requirement | Where |
|---|---|
| Google Cloud AI at runtime (`google-genai`, Vertex AI Gemini) | [`app/tools/google/gemini.py`](app/tools/google/gemini.py) |
| Official `mcp-clickhouse` MCP server at runtime (MCP Python SDK client) | [`app/tools/clickhouse_mcp/client.py`](app/tools/clickhouse_mcp/client.py) · server: [`ops/mcp-clickhouse/Dockerfile`](ops/mcp-clickhouse/Dockerfile) + [`ops/docker-compose.yml`](ops/docker-compose.yml) |
| ClickHouse cluster (self-hosted container; Cloud = env swap) | [`ops/docker-compose.yml`](ops/docker-compose.yml) · schema [`seed/schema.sql`](seed/schema.sql) |

Agents reach ClickHouse **exclusively** through the MCP server as a read-only user.
The seeder and the NATS→ClickHouse ingest worker use a separate writer user, never MCP.

## Quickstart

```bash
# 1. Infrastructure (ClickHouse + mcp-clickhouse + PostgreSQL + NATS + Temporal + Redis)
cd ops && docker compose up -d --build && cd ..

# 2. Python env
python3 -m venv .venv && .venv/bin/pip install -e ".[dev]"

# 3. Seed the deterministic 10-year corpus (~5M rows, engineered correlations)
.venv/bin/python -m seed.generate

# 4. Configure (optional — boots in MOCK mode with no keys)
cp .env.example .env   # add Google Cloud project / API key for LIVE cognition

# 5. API + Temporal worker + console
.venv/bin/uvicorn app.main:app --port 8020
.venv/bin/python -m app.workflows.worker
cd frontend && npm install && npm run dev   # console on :3020
```

Mock mode (no keys, no Docker) still runs the full loop against a recorded corpus
sample with deterministic cognition — `GENESIS_MOCK=1`.

## Architecture

- **4+1 cognitive domains**: Production Economics · Audience & Distribution · Financial
  Performance · Operational History, with Strategic Pattern cognition cross-cutting.
- **Agents**: Institutional Intelligence Executive · Analytical Planner · Domain
  Analysts · Query Engineer (SELECT-guard in code, ≤2 bounded repairs) · Statistical
  Verification (rule-derived states) · Scenario/Simulation (seeded, computed in code).
- **Preserved production stack, all deployed**: PostgreSQL (durable investigation
  state) · Temporal (durable workflow with the Studio-Head decision as a signal) ·
  NATS (`genesis.institutional.events`) · Redis (investigation latch) · DataHub
  (table registration + VERIFIED-finding promotion with query lineage) · MinIO
  (full result-set snapshots) · OpenTelemetry → Google Cloud Trace.
- **Corpus**: deterministic seeded generator — ~60 projects across 10 years with
  engineered correlations (overrun-by-scale/genre, release-window seasonality,
  contested sequel economics, platform-mix drift). Reproducible analyses.

Part of the **Genesis OS** federation (five standalone partner systems + a
coordination layer that none of them depend on). This system runs entirely alone.

## License

MIT — see [LICENSE](LICENSE).
