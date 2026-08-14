-- Genesis OS — Institutional Intelligence: analytical schema (locked §2.4).
-- Applied automatically on first ClickHouse boot (docker-entrypoint-initdb.d).
-- Dimensions + MergeTree facts partitioned by month, ordered for cohort scans.

CREATE DATABASE IF NOT EXISTS genesis_institutional;

CREATE TABLE IF NOT EXISTS genesis_institutional.projects (
    project_id     String,
    title          String,
    type           LowCardinality(String),   -- feature | series | short
    genre          LowCardinality(String),
    budget_class   LowCardinality(String),   -- indie | mid | tentpole
    budget_usd     Float64,
    greenlit_at    Date,
    released_at    Nullable(Date),
    release_window LowCardinality(String),   -- Q1..Q4
    is_sequel      UInt8,
    franchise      LowCardinality(String),
    status         LowCardinality(String)    -- released | in_production | cancelled
) ENGINE = MergeTree ORDER BY project_id;

CREATE TABLE IF NOT EXISTS genesis_institutional.production_events (
    project_id String,
    at         DateTime,
    dept       LowCardinality(String),
    event_type LowCardinality(String),
    metric     LowCardinality(String),
    value      Float64
) ENGINE = MergeTree PARTITION BY toYYYYMM(at) ORDER BY (project_id, at);

CREATE TABLE IF NOT EXISTS genesis_institutional.financial_ledger (
    project_id  String,
    at          Date,
    cost_center LowCardinality(String),
    category    LowCardinality(String),
    planned     Float64,
    actual      Float64
) ENGINE = MergeTree PARTITION BY toYYYYMM(at) ORDER BY (project_id, at);

CREATE TABLE IF NOT EXISTS genesis_institutional.audience_performance (
    project_id String,
    title      String,
    at         Date,
    platform   LowCardinality(String),   -- theatrical | svod | avod | est | tv
    territory  LowCardinality(String),
    views      UInt64,
    completion Float32,
    revenue    Float64
) ENGINE = MergeTree PARTITION BY toYYYYMM(at) ORDER BY (title, at);

CREATE TABLE IF NOT EXISTS genesis_institutional.distribution_events (
    project_id String,
    at         Date,
    event_type LowCardinality(String),   -- deal | theatrical_open | window_open | festival
    platform   LowCardinality(String),
    territory  LowCardinality(String),
    value      Float64
) ENGINE = MergeTree PARTITION BY toYYYYMM(at) ORDER BY (project_id, at);

-- Live mirror of the studio's own operation (NATS fabrics via ingest/ worker).
-- Optional presence: 03 runs fully without 01/02.
CREATE TABLE IF NOT EXISTS genesis_institutional.ops_events (
    at      DateTime,
    source  LowCardinality(String),   -- signal | ops | institutional
    event   LowCardinality(String),
    payload String
) ENGINE = MergeTree PARTITION BY toYYYYMM(at) ORDER BY (source, at);

-- Monthly rollups (materialized at insert time; the Query Engineer may target
-- these for trend scans instead of full fact sweeps).
CREATE MATERIALIZED VIEW IF NOT EXISTS genesis_institutional.financial_monthly
ENGINE = SummingMergeTree ORDER BY (project_id, month, cost_center)
AS SELECT project_id, toStartOfMonth(at) AS month, cost_center,
          sum(planned) AS planned, sum(actual) AS actual
   FROM genesis_institutional.financial_ledger
   GROUP BY project_id, month, cost_center;

CREATE MATERIALIZED VIEW IF NOT EXISTS genesis_institutional.audience_monthly
ENGINE = SummingMergeTree ORDER BY (project_id, month, platform)
AS SELECT project_id, toStartOfMonth(at) AS month, platform,
          sum(views) AS views, sum(revenue) AS revenue,
          sum(completion) AS completion_sum, count() AS samples
   FROM genesis_institutional.audience_performance
   GROUP BY project_id, month, platform;
