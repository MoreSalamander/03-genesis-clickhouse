"""OpenTelemetry agent observability (preserved-stack responsibility).

Institutional Intelligence exports spans — Gemini cognition calls (with token
usage) and ClickHouse MCP tool calls — to Google Cloud Trace via ambient ADC
credentials (locked §2.7: no Grafana of its own; independence from 02).
"""
from __future__ import annotations

from contextlib import contextmanager

from app.config import Settings

_INITIALIZED = False
_ENABLED = False


def setup_tracing(settings: Settings, service_name: str) -> None:
    global _INITIALIZED, _ENABLED
    if _INITIALIZED:
        return
    _INITIALIZED = True
    if settings.force_mock:
        return
    try:
        from opentelemetry import trace
        from opentelemetry.exporter.cloud_trace import CloudTraceSpanExporter
        from opentelemetry.sdk.resources import Resource
        from opentelemetry.sdk.trace import TracerProvider
        from opentelemetry.sdk.trace.export import BatchSpanProcessor

        project = settings.google_project or None
        provider = TracerProvider(resource=Resource.create({"service.name": service_name}))
        provider.add_span_processor(BatchSpanProcessor(CloudTraceSpanExporter(project_id=project)))
        trace.set_tracer_provider(provider)
        _ENABLED = True
        print(f"[otel] agent tracing → Google Cloud Trace ({project}) as {service_name}")
    except Exception as err:
        print(f"[otel] tracing setup failed ({err}) — DEGRADED: no agent spans")


@contextmanager
def span(name: str, **attributes):
    """No-op safe span context manager."""
    if not _ENABLED:
        yield None
        return
    from opentelemetry import trace

    tracer = trace.get_tracer("genesis")
    with tracer.start_as_current_span(name) as sp:
        for key, value in attributes.items():
            if value is not None:
                sp.set_attribute(key, value)
        yield sp
