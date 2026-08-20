# Demo video script — Genesis OS: Institutional Intelligence (ClickHouse track)

**Target ≤ 3:00.** Record the workbench (localhost:3020 until the hosted pass). The arc
below is the exact live-verified investigation (decisions.md 2026-08-13): real Gemini SQL,
real mcp-clickhouse, rule-derived verification, a preserved contested finding, a deeper
round, and promotion.

**Setup:** stack up (`ops/ docker compose up -d`), corpus seeded, API + worker running.
Clear old investigations for a clean ledger if desired (fresh PG volume or new question).

| Time | On screen | Say |
|---|---|---|
| 0:00–0:15 | Masthead + corpus strip: **91M audience rows, 12.6M production events, 4,632 projects, ten eras since 1912**. LIVE badges. | "A century of a film studio's history — a hundred and four million rows of it, from silent serials to the streaming wars — and one question every studio gets wrong: what does our own past actually prove? This is Institutional Intelligence, built for the ClickHouse track." |
| 0:15–0:35 | Type: **"Should we greenlight 'Nebula Frontier 2' at $45M for a Q2 release?"** → OPEN INVESTIGATION. Stage rail starts moving. | "The Studio Head asks a greenlight question. Watch what it does NOT do: it doesn't chat with a database. It plans hypotheses across four analytical domains and goes to work." |
| 0:35–1:05 | Query ledger filling: expand one row — **Gemini-written SQL**, row counts, latency, a **repair(s)** tag. | "Gemini writes every query, grounded in the live schema, and runs it through the official ClickHouse MCP server as a read-only user. When SQL fails, it repairs itself — bounded, on the record. Fourteen queries, every number auditable." |
| 1:05–1:40 | Findings: **✓ VERIFIED** (re-capture n and effect/noise from a fresh live run) and **⚠ CONTESTED** sequel economics; the era hypothesis shows the **overrun U-shape since 1912**; the seasonality finding lands **◐ REGIME — true within: blockbuster era** (summer premiums did not exist before June 1975, and the system says so). | "Now the part no chatbot does: verification is computed in code, never asserted by the model. A century of ledger history says the studio-system factory was our most disciplined era — that's VERIFIED. Sequel economics? A hundred and fourteen years disagree with themselves — sequels open bigger AND their tails die faster — so the system says CONTESTED and preserves both readings." |
| 1:40–2:00 | Competing interpretations side-by-side (PRO-GREENLIGHT vs ANTI-GREENLIGHT cards). Simulation panel: Q2 vs Q4, P10/P50/P90. | "Both readings reach the Studio Head as competing interpretations. And a seeded simulation re-runs history under the changed assumption — shift the release window, project the cohort." |
| 2:00–2:25 | Recommendation card: confidence + coverage chips. Type a note, click **REQUEST DEEPER ANALYSIS**. **ROUND 2** flag appears; new queries stream. | "Confidence is a function of verification coverage — arithmetic, not vibes. And the Studio Head has a third option beyond yes and no: demand deeper analysis. The durable workflow loops back with that guidance. This survived us killing the worker mid-decision." |
| 2:25–2:45 | Round-2 recommendation. Click **APPROVE & PROMOTE** → status **PROMOTED**; promoted-note appears; flash DataHub entity with lineage. | "Round two answers. Approved — and the verified and contested findings are promoted to DataHub as institutional knowledge, carrying their SQL and their lineage back to the tables." |
| 2:45–3:00 | Event fabric feed; repo README runtime-proof table. | "ClickHouse holds the memory, Gemini does the reasoning, the rules do the judging, and a human owns the decision. Genesis OS — Institutional Intelligence." |

**Recording notes**
- A full round takes ~2–4 min live; start recording at launch and time-compress with cuts,
  or pre-run round 1 and record from the findings onward.
- The deeper-round beat can reuse the note: *"Test at least one hypothesis on high-volume
  ledger or daily audience rows, and probe sequel economics with two slicings that could disagree."*
- DataHub shot: GMS UI → search "institutional_finding" (needs the quickstart healthy).
