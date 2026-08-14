"""Process-wide runtime container: every substrate the locked architecture
assigns to 03, constructed once and shared by the API, the Temporal worker,
and tests (mirrors 01/02's runtime pattern — copied, never imported)."""
from __future__ import annotations

from app.config import Settings, settings as default_settings
from app.events.bus import EventBus
from app.memory.durable import get_store
from app.memory.ephemeral import get_ephemeral
from app.memory.stores import EpisodicMemory, WorkingMemory
from app.knowledge.datahub.emitter import DataHubKnowledge
from app.knowledge.objects.store import ResultObjectStore
from app.tools.clickhouse_mcp.client import get_clickhouse
from app.tools.google.gemini import get_cognition


class InstitutionalRuntime:
    def __init__(self, settings: Settings | None = None):
        self.settings = settings or default_settings
        self.store = get_store(self.settings)
        self.working = WorkingMemory(self.store)
        self.episodic = EpisodicMemory(self.settings.data_dir)
        self.ephemeral = get_ephemeral(self.settings)
        self.bus = EventBus(self.settings.data_dir, nats_url=self.settings.nats_url,
                            subject=self.settings.nats_subject)
        self.clickhouse = get_clickhouse(self.settings)
        self.cognition = get_cognition(self.settings)
        self.datahub = DataHubKnowledge(self.settings)
        self.objects = ResultObjectStore(self.settings)

        from app.agents.query.engineer import QueryEngineer
        from app.agents.simulation.scenario import ScenarioAgent
        from app.agents.verification.statistical import StatisticalVerifier
        from app.agents.executive.institutional_executive import InstitutionalExecutive

        self.engineer = QueryEngineer(self.cognition, self.clickhouse)
        self.verifier = StatisticalVerifier(self.settings.verification)
        self.scenario = ScenarioAgent(self.cognition, self.engineer)
        self.executive = InstitutionalExecutive(self)


_runtime: InstitutionalRuntime | None = None


def get_runtime() -> InstitutionalRuntime:
    global _runtime
    if _runtime is None:
        _runtime = InstitutionalRuntime()
    return _runtime
