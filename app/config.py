"""Runtime configuration for Genesis OS — Institutional Intelligence."""
from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()


def _truthy(value: str | None) -> bool:
    return (value or "").strip().lower() in {"1", "true", "yes", "on"}


@dataclass(frozen=True)
class VerificationPolicy:
    """Statistical thresholds behind the rule-derived verification states (locked §2.3).

    These are studio analytical policy, applied in code — never asserted by the model.
    """

    min_cohort_n: int = 30          # observations of the COMPARED UNIT (titles when the
                                    # SQL counted them; annotated row-grain fallback)
    effect_over_noise: float = 0.10 # effect size vs POOLED dispersion (Cohen's-d shaped,
                                    # scale-free — n cannot buy significance). Calibrated
                                    # against the corpus: observational effects here run
                                    # d 0.1-0.3, and the ERA GATE carries the rigor —
                                    # small-but-stable-for-a-century beats large-and-lucky
    min_stable_eras: int = 3        # eras agreeing -> VERIFIED; fewer WITH DATA -> REGIME


@dataclass(frozen=True)
class Settings:
    clickhouse_mcp_url: str = field(
        default_factory=lambda: os.getenv("CLICKHOUSE_MCP_URL", "").strip()
    )
    clickhouse_mcp_token: str = field(
        default_factory=lambda: os.getenv("CLICKHOUSE_MCP_TOKEN", "").strip()
    )
    clickhouse_database: str = field(
        default_factory=lambda: os.getenv("CLICKHOUSE_DATABASE", "genesis_institutional").strip()
    )
    # Writer path (seed/ + ingest/ only — agents go exclusively through MCP)
    clickhouse_host: str = field(default_factory=lambda: os.getenv("CLICKHOUSE_HOST", "localhost").strip())
    clickhouse_http_port: int = field(
        default_factory=lambda: int(os.getenv("CLICKHOUSE_HTTP_PORT", "8123"))
    )
    clickhouse_writer_user: str = field(
        default_factory=lambda: os.getenv("CLICKHOUSE_WRITER_USER", "genesis").strip()
    )
    clickhouse_writer_password: str = field(
        default_factory=lambda: os.getenv("CLICKHOUSE_WRITER_PASSWORD", "genesis-institutional").strip()
    )
    google_api_key: str = field(
        default_factory=lambda: (os.getenv("GOOGLE_API_KEY") or os.getenv("GEMINI_API_KEY") or "").strip()
    )
    use_vertex: bool = field(default_factory=lambda: _truthy(os.getenv("GOOGLE_GENAI_USE_VERTEXAI")))
    google_project: str = field(default_factory=lambda: os.getenv("GOOGLE_CLOUD_PROJECT", "").strip())
    gemini_model: str = field(default_factory=lambda: os.getenv("GEMINI_MODEL", "gemini-flash-latest").strip())
    data_dir: Path = field(default_factory=lambda: Path(os.getenv("GENESIS_DATA_DIR", "./data")))
    force_mock: bool = field(default_factory=lambda: _truthy(os.getenv("GENESIS_MOCK")))
    site: str = field(default_factory=lambda: os.getenv("GENESIS_SITE", "local").strip())
    datahub_gms_url: str = field(
        default_factory=lambda: os.getenv("DATAHUB_GMS_URL", "http://localhost:8080").strip()
    )
    postgres_dsn: str = field(
        default_factory=lambda: os.getenv(
            "POSTGRES_DSN", "postgresql://genesis:genesis@localhost:5435/genesis_institutional"
        ).strip()
    )
    nats_url: str = field(default_factory=lambda: os.getenv("NATS_URL", "nats://localhost:4225").strip())
    nats_subject: str = field(
        default_factory=lambda: os.getenv("NATS_SUBJECT", "genesis.institutional.events").strip()
    )
    temporal_address: str = field(
        default_factory=lambda: os.getenv("TEMPORAL_ADDRESS", "localhost:7235").strip()
    )
    temporal_task_queue: str = field(
        default_factory=lambda: os.getenv("TEMPORAL_TASK_QUEUE", "genesis-institutional-investigations").strip()
    )
    redis_url: str = field(default_factory=lambda: os.getenv("REDIS_URL", "redis://localhost:6382/0").strip())
    minio_endpoint: str = field(default_factory=lambda: os.getenv("MINIO_ENDPOINT", "localhost:9010").strip())
    minio_access_key: str = field(default_factory=lambda: os.getenv("MINIO_ACCESS_KEY", "minioadmin").strip())
    minio_secret_key: str = field(default_factory=lambda: os.getenv("MINIO_SECRET_KEY", "minioadmin").strip())
    ingest_sources: str = field(default_factory=lambda: os.getenv("INGEST_SOURCES", "").strip())
    verification: VerificationPolicy = field(default_factory=VerificationPolicy)
    # The corpus: Convergence Studios, founded 1912 — ~4,600 titles, ten eras,
    # ~100M fact rows. Seed-side knobs (volume dials, era config) live in seed/config.py.
    corpus_start_year: int = 1912
    corpus_horizon_year: int = 2026

    @property
    def clickhouse_live(self) -> bool:
        return bool(self.clickhouse_mcp_url) and not self.force_mock

    @property
    def gemini_live(self) -> bool:
        if self.force_mock:
            return False
        return bool(self.google_api_key) or (self.use_vertex and bool(self.google_project))

    def banner(self) -> str:
        return (
            "Genesis OS — Institutional Intelligence | "
            f"ClickHouse MCP: {'LIVE ' + self.clickhouse_mcp_url if self.clickhouse_live else 'MOCK'} | "
            f"Gemini({self.gemini_model}): {'LIVE' if self.gemini_live else 'MOCK'}"
        )


settings = Settings()
settings.data_dir.mkdir(parents=True, exist_ok=True)
