"""NATS → ClickHouse ingest worker (locked §2.4 `ops_events`).

Consume-only mirror of the studio's event fabrics into institutional memory:
the studio's own operation becomes queryable history. Optional presence — 03
runs fully without 01/02; each source that is down is skipped with a log line.

Sources come from INGEST_SOURCES: comma-separated `nats://host:port=subject`
pairs (e.g. the signal fabric :4223 and the ops fabric :4224), and 03's own
fabric is always included. Writes use the `genesis` WRITER user via
clickhouse-connect — never the MCP path (locked §2.5).

Run:  .venv/bin/python -m ingest.worker
"""
from __future__ import annotations

import asyncio
import json
from datetime import datetime, timezone

from app.config import settings


def _sources() -> list[tuple[str, str, str]]:
    """(url, subject, source_label) triples."""
    triples = [(settings.nats_url, settings.nats_subject, "institutional")]
    for pair in filter(None, (p.strip() for p in settings.ingest_sources.split(","))):
        if "=" not in pair:
            continue
        url, subject = pair.split("=", 1)
        label = "signal" if "signal" in subject else ("ops" if "ops" in subject else subject)
        triples.append((url.strip(), subject.strip(), label))
    return triples


class Ingestor:
    def __init__(self):
        import clickhouse_connect

        self._client = clickhouse_connect.get_client(
            host=settings.clickhouse_host, port=settings.clickhouse_http_port,
            username=settings.clickhouse_writer_user,
            password=settings.clickhouse_writer_password,
            database=settings.clickhouse_database,
        )
        self._buffer: list[list] = []

    def add(self, source: str, payload: bytes) -> None:
        try:
            record = json.loads(payload.decode())
        except json.JSONDecodeError:
            record = {"raw": payload.decode(errors="replace")}
        event = str(record.get("event", "unknown"))
        self._buffer.append([datetime.now(timezone.utc).replace(tzinfo=None), source, event,
                             json.dumps(record, ensure_ascii=False, default=str)[:4000]])
        if len(self._buffer) >= 20:
            self.flush()

    def flush(self) -> None:
        if not self._buffer:
            return
        batch, self._buffer = self._buffer, []
        try:
            self._client.insert("ops_events", batch,
                                column_names=["at", "source", "event", "payload"])
            print(f"[ingest] wrote {len(batch)} events to ops_events")
        except Exception as err:
            print(f"[ingest] insert failed ({err}) — {len(batch)} events dropped")


async def consume(url: str, subject: str, label: str, ingestor: Ingestor) -> None:
    import nats

    while True:
        try:
            nc = await nats.connect(url, connect_timeout=3, max_reconnect_attempts=2)
            sub = await nc.subscribe(subject)
            print(f"[ingest] consuming {subject} from {url} as source={label}")
            async for msg in sub.messages:
                ingestor.add(label, msg.data)
        except Exception as err:
            print(f"[ingest] {url} unavailable ({err}) — retrying in 30s")
            await asyncio.sleep(30)


async def main() -> None:
    ingestor = Ingestor()
    tasks = [consume(url, subject, label, ingestor) for url, subject, label in _sources()]

    async def periodic_flush():
        while True:
            await asyncio.sleep(5)
            ingestor.flush()

    await asyncio.gather(*tasks, periodic_flush())


if __name__ == "__main__":
    asyncio.run(main())
