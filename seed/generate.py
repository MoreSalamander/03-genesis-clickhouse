"""Century-corpus seeder: schema migration, deterministic wipe, dimensions.

Convergence Studios, 1912–2026. This orchestrator owns the corpus lifecycle:

  migrate   v1 (10-year schema) is detected by the absence of `eras` and
            rebuilt in place — every seeder-owned object dropped and recreated
            from schema.sql. `--recreate` / SEED_RECREATE=1 forces the same
            path on demand. NEVER touches ops_events (live ingest data) and
            never drops the database.
  wipe      the idempotent path TRUNCATEs every seeder-owned table INCLUDING
            the materialized-view target tables — the v1 seeder left the MVs
            accumulating across reseeds (financial_monthly reached 2.94× its
            source), which SummingMergeTree then merges into tripled sums.
  dims      eras, cpi_annual, shock_calendar (pure config: seed/eras.py,
            seed/cpi.py, seed/shocks.py); projects + franchises come from
            seed/slate.py; fact expansion runs inside ClickHouse (seed/expand.py).

Writes via clickhouse-connect as the WRITER user — the agents' path is
exclusively the official mcp-clickhouse server (read-only user).

Usage:  .venv/bin/python -m seed.generate               # migrate-if-needed + reseed
        .venv/bin/python -m seed.generate --recreate    # force full schema rebuild
"""
from __future__ import annotations

import argparse
import os
import re
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from seed import cpi, eras, expand, shocks, slate  # noqa: E402

# Seeder-owned objects in drop order: MV wrappers before their targets, facts
# before dims. ops_events is deliberately absent from every list in this file.
MV_WRAPPERS = ("financial_monthly_mv", "audience_monthly_mv")
MV_TARGETS = ("financial_monthly", "audience_monthly")
FACTS = ("production_events", "financial_ledger", "audience_performance", "distribution_events")
DIMS = ("projects", "eras", "cpi_annual", "franchises", "shock_calendar")
SCRATCH_DB = "genesis_seed"


def connect():
    from app.config import settings
    import clickhouse_connect

    client = clickhouse_connect.get_client(
        host=settings.clickhouse_host, port=settings.clickhouse_http_port,
        username=settings.clickhouse_writer_user, password=settings.clickhouse_writer_password,
        database=settings.clickhouse_database,
    )
    print(f"[seed] connected to ClickHouse {settings.clickhouse_host}:{settings.clickhouse_http_port} "
          f"db={settings.clickhouse_database}")
    return client


def schema_statements() -> list[str]:
    """schema.sql split into executable statements (comment-only chunks dropped).

    Statements terminate with a semicolon at end of line — splitting on bare
    ';' would sever COMMENT literals ("inclusive; eras are contiguous") and
    header comments alike.
    """
    text = (Path(__file__).parent / "schema.sql").read_text(encoding="utf-8")
    statements: list[str] = []
    for chunk in re.split(r";\s*\n", text):
        lines = [ln for ln in chunk.splitlines()
                 if ln.strip() and not ln.strip().startswith("--")]
        if lines:
            statements.append("\n".join(lines))
    return statements


def table_exists(client, name: str) -> bool:
    return bool(client.query(
        "SELECT count() FROM system.tables WHERE database = currentDatabase() AND name = {n:String}",
        parameters={"n": name},
    ).result_rows[0][0])


def count(client, table: str) -> int:
    return client.query(f"SELECT count() FROM {table}").result_rows[0][0]


def migrate(client, recreate: bool) -> str:
    """Bring the database to schema v2; return the path taken.

    Drift (no `eras` table) or an explicit --recreate drops every seeder-owned
    object and re-applies schema.sql. Dropping MV_TARGETS by name also removes
    the v1 TO-less materialized views, which shared those names — their hidden
    .inner data goes with them. The idempotent path truncates instead, MV
    targets included (the 2.94× fix).
    """
    drift = not table_exists(client, "eras")
    if drift or recreate:
        for name in (*MV_WRAPPERS, *MV_TARGETS, *FACTS, *DIMS):
            client.command(f"DROP TABLE IF EXISTS {name}")
        for stmt in schema_statements():
            client.command(stmt)
        return "recreated (v1→v2 migration)" if drift else "recreated (--recreate)"
    for name in (*FACTS, *MV_TARGETS, *DIMS):
        client.command(f"TRUNCATE TABLE {name}")
    return "truncated (idempotent reseed, MV targets included)"


def create_era_dictionary(client) -> None:
    """RANGE_HASHED dictionary over the eras table.

    CH 24.8 rejects range conditions inside JOIN ON, so fact-date era
    attribution ("which era was this dollar EARNED in") would need a CROSS
    JOIN + WHERE. dictGetString('era_dict', 'name', 0, at) answers it at hash
    speed instead — a named deep-dive capability, wired for the showcase.
    Created by the seeder because the source clause carries the writer login.
    """
    from app.config import settings

    client.command("DROP DICTIONARY IF EXISTS genesis_institutional.era_dict")
    # constant key + era ranges = pure date→era lookup; ranges as Int64 days
    # because the corpus predates the Date epoch (Date32 → toInt64 is stable)
    client.command(f"""
        CREATE DICTIONARY genesis_institutional.era_dict (
            k UInt64,
            start_d Int64,
            end_d Int64,
            era_id UInt8,
            name String
        )
        PRIMARY KEY k
        SOURCE(CLICKHOUSE(HOST 'localhost' PORT 9000 USER '{settings.clickhouse_writer_user}'
                          PASSWORD '{settings.clickhouse_writer_password}'
                          DB 'genesis_institutional'
                          QUERY 'SELECT toUInt64(0) AS k,
                                        toInt64(start_date) AS start_d, toInt64(end_date) AS end_d,
                                        era_id, name
                                 FROM genesis_institutional.eras'))
        LAYOUT(RANGE_HASHED())
        RANGE(MIN start_d MAX end_d)
        LIFETIME(MIN 0 MAX 0)
    """)
    probe = client.query(
        "SELECT dictGetString('genesis_institutional.era_dict', 'name', "
        "toUInt64(0), toInt64(toDate32('1975-06-20')))").result_rows[0][0]
    assert probe == "blockbuster", f"era_dict probe returned {probe!r}"
    print(f"[seed] era_dict: dictGet('1975-06-20') → {probe!r}")


def seed_dims(client) -> None:
    client.insert("eras", eras.rows(),
                  column_names=["era_id", "name", "start_date", "end_date", "summary"])
    client.insert("cpi_annual", cpi.rows(),
                  column_names=["year", "cpi", "mult_to_2026"])
    client.insert("shock_calendar", shocks.rows(),
                  column_names=["shock_id", "name", "kind", "start_date", "end_date",
                                "production_halt", "cost_mult", "attendance_mult"])
    print(f"[seed] dims: eras={count(client, 'eras')} cpi_annual={count(client, 'cpi_annual')} "
          f"shock_calendar={count(client, 'shock_calendar')}")


def inventory(client) -> None:
    for table in (*DIMS, *FACTS, *MV_TARGETS, "ops_events"):
        print(f"[seed]   verify {table}: {count(client, table):,}")


def main() -> int:
    parser = argparse.ArgumentParser(description="Seed the 1912–2026 institutional corpus")
    parser.add_argument("--recreate", action="store_true",
                        help="drop and recreate every seeder-owned object from schema.sql")
    args = parser.parse_args()
    recreate = args.recreate or os.getenv("SEED_RECREATE") == "1"

    t0 = time.time()
    client = connect()
    ops_before = count(client, "ops_events") if table_exists(client, "ops_events") else None

    print(f"[seed] schema: {migrate(client, recreate)}")
    seed_dims(client)
    create_era_dictionary(client)

    projects, franchise_rows = slate.build()
    client.insert("projects", slate.project_rows(projects),
                  column_names=slate.PROJECT_COLUMNS)
    client.insert("franchises", franchise_rows,
                  column_names=["franchise_id", "name", "cycle_type", "started_year",
                                "ended_year", "n_entries", "notes"])
    released = sum(1 for p in projects if p["released_at"])
    sequels = sum(p["is_sequel"] for p in projects)
    print(f"[seed] projects: {len(projects)} (released={released}, sequels={sequels}, "
          f"franchises={len(franchise_rows)})")

    expand.prepare_scratch(client, projects)
    expand.detach_mv(client, "audience_monthly_mv")
    try:
        expand.expand_audience(client)
    finally:
        expand.attach_mv(client, "audience_monthly_mv")
    expand.backfill_audience_monthly(client)

    expand.prepare_prod_scratch(client, projects)
    expand.expand_production(client, lambda t: count(client, t))
    expand.expand_financial(client, lambda t: count(client, t))

    from seed import channels
    dist_rows = channels.distribution_rows(projects)
    client.insert("distribution_events", dist_rows,
                  column_names=["project_id", "at", "event_type", "platform",
                                "territory", "value"],
                  settings=expand.INSERT_SETTINGS)
    print(f"[seed] distribution_events: {len(dist_rows):,} rows")

    expand.drop_scratch(client)

    if ops_before is not None:
        ops_after = count(client, "ops_events")
        assert ops_after == ops_before, f"ops_events changed: {ops_before} → {ops_after}"
        print(f"[seed] ops_events untouched: {ops_after:,} rows")
    inventory(client)
    print(f"[seed] done in {time.time() - t0:.0f}s")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
