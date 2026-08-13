"""OpenTelemetry agent observability (preserved-stack responsibility).

Every Gemini call, Grafana MCP tool call, and actuation emits spans to the
system's own Tempo (OTLP HTTP :4318), queryable in Grafana next to the studio
telemetry — the system observes its own cognition with the same stack it uses
to observe the studio.
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
    if settings.force_mock or not settings.otlp_endpoint:
        return
    try:
        from opentelemetry import trace
        from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter
        from opentelemetry.sdk.resources import Resource
        from opentelemetry.sdk.trace import TracerProvider
        from opentelemetry.sdk.trace.export import BatchSpanProcessor

        provider = TracerProvider(resource=Resource.create({"service.name": service_name}))
        provider.add_span_processor(
            BatchSpanProcessor(OTLPSpanExporter(endpoint=f"{settings.otlp_endpoint}/v1/traces"))
        )
        trace.set_tracer_provider(provider)
        _ENABLED = True
        print(f"[otel] agent tracing → {settings.otlp_endpoint} as {service_name}")
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
