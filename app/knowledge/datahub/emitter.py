"""DataHub — durable knowledge/context/provenance substrate (locked §2.7).

Two responsibilities:
1. bootstrap(): register the ClickHouse analytical tables as DataHub datasets
   (platform `clickhouse`) so institutional analytics are first-class metadata.
2. promote(): approved investigations emit their VERIFIED findings as knowledge
   entities with UpstreamLineage back to the ClickHouse tables their SQL read —
   the promotion path in the locked loop (finding → institutional knowledge).

DataHub outages degrade to log lines and never fail an investigation.
"""
from __future__ import annotations

import re

from app.config import Settings
from app.models.institutional import Investigation, VerificationState

TABLES = ["projects", "production_events", "financial_ledger",
          "audience_performance", "distribution_events", "ops_events"]


class DataHubKnowledge:
    def __init__(self, settings: Settings):
        self.settings = settings
        self._emitter = None
        if settings.datahub_gms_url and not settings.force_mock:
            try:
                from datahub.emitter.rest_emitter import DatahubRestEmitter

                self._emitter = DatahubRestEmitter(gms_server=settings.datahub_gms_url)
            except ImportError:
                print("[knowledge] acryl-datahub not importable — DataHub promotion disabled")

    @property
    def available(self) -> bool:
        return self._emitter is not None

    def _table_urn(self, table: str) -> str:
        from datahub.emitter.mce_builder import make_dataset_urn

        return make_dataset_urn(platform="clickhouse",
                                name=f"{self.settings.clickhouse_database}.{table}", env="PROD")

    def bootstrap(self) -> int:
        """Register the analytical tables as datasets. Returns how many emitted."""
        if self._emitter is None:
            return 0
        emitted = 0
        try:
            from datahub.emitter.mcp import MetadataChangeProposalWrapper
            from datahub.metadata.schema_classes import DatasetPropertiesClass

            for table in TABLES:
                self._emitter.emit(MetadataChangeProposalWrapper(
                    entityUrn=self._table_urn(table),
                    aspect=DatasetPropertiesClass(
                        name=table,
                        description=f"Genesis OS institutional corpus table `{table}` "
                                    "(ClickHouse, genesis_institutional).",
                        customProperties={"system": "genesis-institutional-intelligence",
                                          "substrate": "clickhouse"},
                    ),
                ))
                emitted += 1
        except Exception as err:
            print(f"[knowledge] DataHub bootstrap failed: {err}")
        return emitted

    def scope_for(self, question: str) -> dict:
        """Runtime context read: which registered analytical datasets exist.
        (Graph read keeps DataHub in the loop as the context substrate.)"""
        if self._emitter is None:
            return {"datahub": "unavailable", "datasets": []}
        return {"datahub": self.settings.datahub_gms_url,
                "datasets": [f"clickhouse:{self.settings.clickhouse_database}.{t}" for t in TABLES]}

    def promote(self, inv: Investigation) -> list[str]:
        """Emit VERIFIED (and preserved CONTESTED) findings with query lineage."""
        if self._emitter is None:
            return []
        urns: list[str] = []
        try:
            from datahub.emitter.mce_builder import make_dataset_urn
            from datahub.emitter.mcp import MetadataChangeProposalWrapper
            from datahub.metadata.schema_classes import (
                DatasetLineageTypeClass,
                DatasetPropertiesClass,
                UpstreamClass,
                UpstreamLineageClass,
            )

            promotable = [f for f in inv.findings
                          if f.state in (VerificationState.VERIFIED, VerificationState.CONTESTED)]
            for finding in promotable:
                urn = make_dataset_urn(platform="genesis-studio",
                                       name=f"institutional_finding.{finding.id}", env="PROD")
                sqls = []
                upstream_tables: set[str] = set()
                for qid in finding.evidence_query_ids:
                    query = inv.query_by_id(qid)
                    if query is None:
                        continue
                    sqls.append(query.sql)
                    for table in TABLES:
                        if re.search(rf"\b{table}\b", query.sql):
                            upstream_tables.add(table)
                self._emitter.emit(MetadataChangeProposalWrapper(
                    entityUrn=urn,
                    aspect=DatasetPropertiesClass(
                        name=f"[{finding.state.value}] {finding.statement[:120]}",
                        description=(f"Institutional finding from investigation {inv.id} "
                                     f"('{inv.question[:200]}'). Basis: {finding.basis}"),
                        customProperties={
                            "verification_state": finding.state.value,
                            "domain": finding.domain,
                            "stats": str(finding.stats)[:900],
                            "sql": " || ".join(sqls)[:900],
                            "investigation": inv.id,
                        },
                    ),
                ))
                if upstream_tables:
                    self._emitter.emit(MetadataChangeProposalWrapper(
                        entityUrn=urn,
                        aspect=UpstreamLineageClass(upstreams=[
                            UpstreamClass(dataset=self._table_urn(t),
                                          type=DatasetLineageTypeClass.TRANSFORMED)
                            for t in sorted(upstream_tables)
                        ]),
                    ))
                urns.append(urn)
        except Exception as err:  # outage must not fail the investigation
            print(f"[knowledge] DataHub promotion failed: {err}")
        return urns
