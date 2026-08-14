"""Full result-set snapshots — MinIO (preserved-stack responsibility, locked §2.7).

Every executed analytical query's complete result table is stored as an
immutable object under investigation/{id}/query/{id}.json — the untransformed
evidence behind each finding, addressable for audit ("show me exactly what the
database returned").
"""
from __future__ import annotations

import io

from app.config import Settings

BUCKET = "genesis-institutional-evidence"


class ResultObjectStore:
    def __init__(self, settings: Settings):
        self._client = None
        if settings.force_mock:
            return
        try:
            from minio import Minio

            self._client = Minio(
                settings.minio_endpoint,
                access_key=settings.minio_access_key,
                secret_key=settings.minio_secret_key,
                secure=False,
            )
            if not self._client.bucket_exists(BUCKET):
                self._client.make_bucket(BUCKET)
            print(f"[objects] MinIO connected: {settings.minio_endpoint}/{BUCKET}")
        except Exception as err:
            print(f"[objects] MinIO unreachable ({err}) — DEGRADED: result snapshots not stored")
            self._client = None

    @property
    def available(self) -> bool:
        return self._client is not None

    def put_result(self, investigation_id: str, query_id: str, document: bytes) -> str | None:
        if self._client is None:
            return None
        try:
            key = f"investigation/{investigation_id}/query/{query_id}.json"
            self._client.put_object(BUCKET, key, io.BytesIO(document), len(document),
                                    content_type="application/json")
            return key
        except Exception as err:
            print(f"[objects] MinIO put failed: {err}")
            return None
