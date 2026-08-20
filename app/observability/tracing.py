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
        return

    # AI Observability (the track's second direction: observe the agent you
    # build). OpenLIT auto-instruments the google-genai SDK with gen_ai.*
    # semantic conventions — model, latency, token usage, cost — and rides the
    # same OTLP pipeline. Local Tempo receives the spans by default; metrics
    # export stays off unless a metrics-capable endpoint (the Grafana Cloud
    # OTLP gateway) is configured, because Tempo accepts traces only and a
    # rejected exporter would spam the log with noise that looks like faults.
    if not settings.ai_obs:
        return
    try:
        import openlit

        endpoint = settings.ai_obs_otlp_endpoint or settings.otlp_endpoint
        cloud = bool(settings.ai_obs_otlp_endpoint)
        kwargs = {
            "otlp_endpoint": endpoint,
            "application_name": service_name + "-cognition",
            "environment": settings.site,
            "capture_message_content": False,  # spans carry shape and cost, not transcripts
            "disable_metrics": not cloud,
        }
        if settings.ai_obs_otlp_headers:
            kwargs["otlp_headers"] = settings.ai_obs_otlp_headers
        openlit.init(**kwargs)
        print(f"[ai-obs] OpenLIT gen_ai instrumentation → {endpoint}"
              + (" (metrics on)" if cloud else " (traces only — local Tempo)"))
    except Exception as err:
        print(f"[ai-obs] OpenLIT init failed ({err}) — DEGRADED: no gen_ai spans")


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
