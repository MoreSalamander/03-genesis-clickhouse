# Institutional Intelligence Contract (federation boundary)

The interface Genesis OS will consume through an adapter (Handoff §16). The
standalone owns this API; the federation calls it — never the reverse. No code
is shared: this document is the contract, vendored per repo.

## Direction

Genesis OS → **Institutional Intelligence Contract** → ClickHouse-system adapter → this API.

## Request

`POST /api/investigations` — `{"question": str}` → `202 {"id", "status", "execution"}`
One investigation at a time (Redis latch) — `409` with the holder's id otherwise.

`POST /api/investigations/{id}/decision` — `{"decision": "approved"|"rejected"|"deeper", "note": str}`
"deeper" re-plans with the note as guidance (bounded rounds). Decisions route
through the durable Temporal workflow signal when available.

## Result (analytical evidence payload)

`GET /api/investigations/{id}` → the full investigation document:

| Field | Meaning |
|---|---|
| `hypotheses[]` | falsifiable claims per cognitive domain (4+1 model) |
| `queries[]` | executed SQL evidence: `sql`, `columns`, `rows` (sample), `row_count`, `elapsed_ms`, `repairs`, `computed_stats`, `snapshot_object` (MinIO key of the full result) |
| `findings[]` | rule-derived `state` ∈ VERIFIED/REGIME/WEAK/CONTESTED/INSUFFICIENT with `basis` (how the rules decided) and `stats` (effect, n, effect/noise) |
| `interpretations[]` | competing readings; CONTESTED findings always carry ≥2 stances |
| `simulation` | seeded bootstrap projection: `baseline`/`projected`/`delta` at P10/P50/P90, `seed`, `n_runs` |
| `recommendation` | `action`, `rationale`, `confidence` (computed from verification coverage), `coverage`, `caveats` |
| `promotion` | DataHub URNs of promoted findings (query lineage attached in DataHub) |

## Events (NATS `genesis.institutional.events` + JSONL audit)

`investigation.started/completed/incomplete`, `analysis.executed`,
`finding.verified/weak/contested/insufficient`, `simulation.completed`,
`recommendation.created`, `authorization.decided`, `knowledge.promoted`.

## Guarantees

- Every number in a finding traces to an executed SQL query through the
  **official mcp-clickhouse server** (read-only user); full result sets are
  snapshotted to MinIO.
- Verification states and confidence are computed in code — never asserted by
  the model. Contested analyses are preserved, never resolved.
- Substrate failure yields `INCOMPLETE` with a reason — never fabricated data.
