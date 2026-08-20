-- Genesis OS — Institutional Intelligence: the century schema (1912–2026).
-- Convergence Studios, founded 1912. Applied automatically on first ClickHouse
-- boot (docker-entrypoint-initdb.d); on an existing stack seed/generate.py
-- re-applies it statement-by-statement during --recreate migration.
--
-- Facts partition BY YEAR (114 partitions across the corpus — the right grain
-- for era/decade analytics); ops_events keeps its original monthly grain (live
-- ingest data, never reseeded). All money columns are NOMINAL dollars of their
-- year — join cpi_annual (mult_to_2026) to compare across eras.

CREATE DATABASE IF NOT EXISTS genesis_institutional;

-- ── dimensions ──────────────────────────────────────────────────────────────

CREATE TABLE IF NOT EXISTS genesis_institutional.eras (
    era_id     UInt8   COMMENT 'chronological 1..10',
    name       LowCardinality(String) COMMENT 'silent | sound_depression | golden_age | decree_tv | conglomerate | blockbuster | home_video | dvd_peak | streaming_transition | streaming_wars_covid',
    start_date Date32  COMMENT 'inclusive; eras are contiguous, no gaps',
    end_date   Date32  COMMENT 'inclusive',
    summary    String  COMMENT 'one-line economic character of the era'
) ENGINE = MergeTree ORDER BY era_id
  COMMENT 'The ten industry eras 1912-2026. Join facts on at BETWEEN start_date AND end_date for era splits — a finding stable across eras is institutional truth; one era only is a regime.';

CREATE TABLE IF NOT EXISTS genesis_institutional.cpi_annual (
    year         UInt16  COMMENT '1912..2026',
    cpi          Float64 COMMENT 'US CPI-U annual average (1982-84 = 100)',
    mult_to_2026 Float64 COMMENT 'multiply a nominal amount of this year by this to get 2026 dollars (~33.9x from 1912)'
) ENGINE = MergeTree ORDER BY year
  COMMENT 'Annual deflator. ALL money in this corpus is nominal — cross-era money comparisons are meaningless without this join.';

CREATE TABLE IF NOT EXISTS genesis_institutional.franchises (
    franchise_id String  COMMENT 'fr-... stable id',
    name         String,
    cycle_type   LowCardinality(String) COMMENT 'serial | monster_cycle | b_franchise | numbered_sequel | franchise_premium | legacy_revival — sequel economics are era-dependent BY DESIGN',
    started_year UInt16,
    ended_year   Nullable(UInt16) COMMENT 'NULL while the cycle is alive',
    n_entries    UInt8,
    notes        String
) ENGINE = MergeTree ORDER BY franchise_id
  COMMENT 'Franchises and cycles across the century. The monster cycle (1931-48) carries the complete fatigue curve; modern cycles open bigger and die faster — both readings are in the data.';

CREATE TABLE IF NOT EXISTS genesis_institutional.shock_calendar (
    shock_id        String  COMMENT 'e.g. covid_halt, wga_1988',
    name            String,
    kind            LowCardinality(String) COMMENT 'pandemic | depression | war | strike | recession | regulation | corporate',
    start_date      Date32,
    end_date        Date32,
    production_halt UInt8   COMMENT '1 = no shooting inside the window',
    cost_mult       Float32 COMMENT 'multiplier on production costs inside the window',
    attendance_mult Float32 COMMENT 'multiplier on theatrical demand inside the window (COVID: 0.12; WWII boom: 1.25)'
) ENGINE = MergeTree ORDER BY start_date
  COMMENT 'The century''s weather: influenza 1918, Depression + receivership, wartime caps and boom, the strike calendar through 2023, COVID. Joins explain the dents.';

CREATE TABLE IF NOT EXISTS genesis_institutional.projects (
    project_id         String  COMMENT 'prj-00001.., zero-padded, chronological by greenlight',
    title              String,
    project_type       LowCardinality(String) COMMENT 'feature | short | serial | tv_movie | streaming_original',
    division           LowCardinality(String) COMMENT 'features | shorts | serials | television | streaming | specialty',
    genre              LowCardinality(String) COMMENT 'century vocabulary: westerns die ~1970, noir is 40s-50s, musicals boom with sound',
    era_id             UInt8   COMMENT 'era of release (join eras)',
    budget_class       LowCardinality(String) COMMENT 'indie | mid | tentpole — PERCENTILE WITHIN A ROLLING DECADE (era-relative), never absolute dollars',
    budget_usd         Float64 COMMENT 'NOMINAL dollars of its year — deflate via cpi_annual for cross-era comparison',
    greenlit_at        Date32,
    released_at        Nullable(Date32) COMMENT 'NULL while in production or cancelled',
    release_window     LowCardinality(String) COMMENT 'Q1..Q4 — NOTE: summer only matters after 1975-06-20',
    is_sequel          UInt8   COMMENT '1 when entry_number > 1',
    franchise          LowCardinality(String) COMMENT 'franchise NAME, empty for standalone (kept for compatibility)',
    franchise_id       String  COMMENT 'join franchises; empty for standalone',
    entry_number       UInt8   COMMENT '1 = original / first chapter; 0 = standalone',
    sound_format       LowCardinality(String) COMMENT 'silent | mono | stereo | digital',
    color_format       LowCardinality(String) COMMENT 'bw | technicolor | color',
    aspect             LowCardinality(String) COMMENT 'academy | widescreen | scope',
    shoot_days_planned UInt16,
    shoot_days_actual  UInt16  COMMENT 'Leviathan (1975): planned 55, shot 159',
    status             LowCardinality(String) COMMENT 'released | in_production | cancelled'
) ENGINE = MergeTree ORDER BY project_id
  COMMENT '~4,600 productions of Convergence Studios, founded 1912 — features, shorts, serials, TV movies, streaming originals.';

-- ── facts (PARTITION BY YEAR — 114 partitions across the century) ───────────

CREATE TABLE IF NOT EXISTS genesis_institutional.production_events (
    project_id String   COMMENT 'join projects',
    at         DateTime64(0) COMMENT 'DateTime64: the corpus starts in 1912, before the DateTime epoch',
    dept       LowCardinality(String) COMMENT 'production | camera | art | post | sound | marketing | distribution | vfx (vfx only exists from the 1980s)',
    event_type LowCardinality(String) COMMENT 'daily_burn | crew_hours | render_farm | schedule_slip | strike_pause',
    metric     LowCardinality(String) COMMENT 'usd | hours | gpu_hours | days',
    value      Float64
) ENGINE = MergeTree PARTITION BY toYear(at) ORDER BY (project_id, at)
  COMMENT 'Shoot-window telemetry per project per day. Strike windows and the COVID halt appear as gaps and strike_pause events. Slips co-move with overruns.';

CREATE TABLE IF NOT EXISTS genesis_institutional.financial_ledger (
    project_id  String   COMMENT 'join projects',
    at          Date32   COMMENT 'monthly lines through the production window',
    cost_center LowCardinality(String) COMMENT 'era vocabulary: studio_overhead is a studio-system line (25-35%%, 1912-62); p_and_a explodes post-1975; covid_protocols exists 2020-22; vfx from the 1980s',
    category    LowCardinality(String) COMMENT 'spend',
    planned     Float64  COMMENT 'NOMINAL dollars',
    actual      Float64  COMMENT 'NOMINAL dollars — actual/planned is the overrun; the golden age (1934-48) is the century minimum'
) ENGINE = MergeTree PARTITION BY toYear(at) ORDER BY (project_id, at)
  COMMENT 'Planned vs actual per cost center per month, 1912-2026, nominal dollars (join cpi_annual to compare eras).';

CREATE TABLE IF NOT EXISTS genesis_institutional.audience_performance (
    project_id String   COMMENT 'join projects',
    title      LowCardinality(String) COMMENT 'display only — join on project_id',
    at         Date32   COMMENT 'cadence varies by channel: theatrical WEEKLY, tv_licensing QUARTERLY, home_video MONTHLY, streaming DAILY',
    channel    LowCardinality(String) COMMENT 'theatrical | theatrical_reissue | tv_licensing | syndication | pay_cable | home_video | ppv_vod | est | pvod | streaming_licensed | streaming_own — era-gated: each channel exists only after its birth year (tv 1955, video 1980, streaming_own 2020-07)',
    platform   LowCardinality(String) COMMENT 'outlet detail: first_run | reissue | broadcast | basic_cable | premium_cable | vhs | dvd | bluray | ppv | est_store | convergence_plus | partner_svod',
    territory  LowCardinality(String) COMMENT 'domestic | uk_ireland | europe | latam | asia_pacific | row',
    views      UInt64   COMMENT 'admissions (theatrical) / units (video) / streams (streaming) / 0 for pure licensing lines',
    completion Nullable(Float32) COMMENT 'STREAMING CHANNELS ONLY (2015+); NULL everywhere else — the corpus cannot answer completion questions before streaming existed',
    revenue    Float64  COMMENT 'NOMINAL dollars of the row''s year'
) ENGINE = MergeTree PARTITION BY toYear(at) ORDER BY (project_id, channel, at)
  COMMENT 'Revenue and consumption by channel/territory across the century. Home video EXCEEDS theatrical from ~1986; DVD peaks 2004 then collapses; 2020 theatrical craters; Convergence+ launches 2020-07 with the whole vault.';

CREATE TABLE IF NOT EXISTS genesis_institutional.distribution_events (
    project_id String   COMMENT 'join projects',
    at         Date32,
    event_type LowCardinality(String) COMMENT 'deal | theatrical_open | window_open | tv_license_deal | video_release | platform_launch | reissue | festival | strike_delay',
    platform   LowCardinality(String),
    territory  LowCardinality(String),
    value      Float64  COMMENT 'deal value where applicable, NOMINAL'
) ENGINE = MergeTree PARTITION BY toYear(at) ORDER BY (project_id, at)
  COMMENT 'Deals, openings, window events, and release moves (the 2023 double strike moved tentpoles by most of a year).';

-- Live mirror of the studio's own operation (NATS fabrics via ingest/ worker).
-- Optional presence: 03 runs fully without 01/02. NEVER reseeded or truncated.
CREATE TABLE IF NOT EXISTS genesis_institutional.ops_events (
    at      DateTime,
    source  LowCardinality(String)   COMMENT 'signal | ops | institutional',
    event   LowCardinality(String),
    payload String
) ENGINE = MergeTree PARTITION BY toYYYYMM(at) ORDER BY (source, at)
  COMMENT 'Live operational mirror — institutional memory growing from the studio actually running. Not part of the seeded corpus.';

-- ── monthly rollups (TO-table MVs: truncatable, detachable for bulk loads) ──

CREATE TABLE IF NOT EXISTS genesis_institutional.financial_monthly (
    project_id  String,
    month       Date32,
    cost_center LowCardinality(String),
    planned     Float64,
    actual      Float64
) ENGINE = SummingMergeTree ORDER BY (project_id, month, cost_center)
  COMMENT 'Monthly ledger rollup (target table of financial_monthly_mv). Prefer this to full financial_ledger sweeps for trend scans.';

CREATE MATERIALIZED VIEW IF NOT EXISTS genesis_institutional.financial_monthly_mv
TO genesis_institutional.financial_monthly AS
SELECT project_id, at - toIntervalDay(toDayOfMonth(at) - 1) AS month, cost_center,
       sum(planned) AS planned, sum(actual) AS actual
FROM genesis_institutional.financial_ledger
GROUP BY project_id, month, cost_center;

CREATE TABLE IF NOT EXISTS genesis_institutional.audience_monthly (
    project_id     String,
    month          Date32,
    channel        LowCardinality(String),
    views          UInt64,
    revenue        Float64,
    completion_sum Float64 COMMENT 'sum of non-NULL completions (streaming only)',
    completion_n   UInt64  COMMENT 'count of non-NULL completions — divide for the mean'
) ENGINE = SummingMergeTree ORDER BY (project_id, month, channel)
  COMMENT 'Monthly audience rollup by channel (target table of audience_monthly_mv). A century of trend questions belongs here, not on 76M daily rows.';

CREATE MATERIALIZED VIEW IF NOT EXISTS genesis_institutional.audience_monthly_mv
TO genesis_institutional.audience_monthly AS
SELECT project_id, at - toIntervalDay(toDayOfMonth(at) - 1) AS month, channel,
       sum(views) AS views, sum(revenue) AS revenue,
       sum(assumeNotNull(completion)) AS completion_sum,
       countIf(isNotNull(completion)) AS completion_n
FROM genesis_institutional.audience_performance
GROUP BY project_id, month, channel;
