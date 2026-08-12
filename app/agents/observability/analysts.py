"""Observability cognition (locked §4): three analysts decompose operational
reality into evidence classes — metrics, logs, traces — plus the alert-rule
scan. All retrieval goes through the Grafana MCP telemetry interface; anomaly
flags are computed against studio thresholds in code.
"""
from __future__ import annotations

from app.config import Thresholds
from app.models.operational import TelemetryEvidence


class MetricsAnalyst:
    name = "Metrics Analyst"
    permissions = ("read", "analyze")

    # Each render farm carries a `site` label — queries are scoped to this
    # system's own site so multiple farms can share one Grafana stack.
    METRICS = [
        ("gpu_utilization_pct", 'avg(studio_gpu_utilization_percent{{site="{site}"}})', "%",
         "gpu_utilization_pct", "GPU utilization across render Worker Pool A"),
        ("render_queue_depth", 'max(studio_render_queue_depth{{site="{site}"}})', "jobs",
         "queue_depth", "Jobs waiting in the render queue"),
        ("render_latency_s", 'avg(studio_render_latency_seconds{{site="{site}"}})', "s",
         "render_latency_s", "Average render job latency"),
        ("worker_error_rate_per_min", 'sum(rate(studio_worker_errors_total{{site="{site}"}}[5m])) * 60',
         "errors/min", "worker_error_rate_per_min", "Worker error rate"),
    ]

    def observe(self, telemetry, thresholds: Thresholds, minutes: int = 30,
                site: str = "local") -> list[TelemetryEvidence]:
        evidence = []
        for name, expr_template, unit, threshold_key, description in self.METRICS:
            expr = expr_template.format(site=site)
            data = telemetry.query_metric(name, expr, minutes)
            threshold = getattr(thresholds, threshold_key)
            latest = data.get("latest")
            anomalous = latest is not None and latest >= threshold
            evidence.append(
                TelemetryEvidence(
                    kind="metric", name=name, query=data.get("query", expr), unit=unit,
                    window_minutes=minutes, latest=latest, average=data.get("average"),
                    slope_per_min=data.get("slope_per_min"),
                    samples=[(round(t, 1), v) for t, v in (data.get("samples") or [])][-40:],
                    anomalous=anomalous,
                    detail=f"{description}: {latest}{unit} (threshold {threshold}{unit}, "
                           f"slope {data.get('slope_per_min')}/min)",
                )
            )
        return evidence


class LogAnalyst:
    name = "Log Analyst"
    permissions = ("read", "analyze")

    LOGQL = '{{job="render-worker", site="{site}"}} |= `error`'

    def observe(self, telemetry, thresholds: Thresholds, minutes: int = 30,
                site: str = "local") -> list[TelemetryEvidence]:
        data = telemetry.query_logs(self.LOGQL.format(site=site), minutes)
        count = data.get("count", 0)
        anomalous = count >= thresholds.log_error_count
        return [
            TelemetryEvidence(
                kind="log", name="worker_error_logs", query=data.get("query", ""),
                window_minutes=minutes, lines=(data.get("lines") or [])[:20],
                latest=float(count), unit="lines", anomalous=anomalous,
                detail=f"{count} error lines from render workers in the window "
                       f"(threshold {thresholds.log_error_count})",
            )
        ]


class TraceAnalyst:
    name = "Trace Analyst"
    permissions = ("read", "analyze")

    def observe(self, telemetry, thresholds: Thresholds, minutes: int = 30,
                site: str = "local") -> list[TelemetryEvidence]:
        # No tracing datasource in this deployment yet. Locked failure philosophy (§15):
        # report the gap honestly instead of fabricating telemetry.
        return [
            TelemetryEvidence(
                kind="trace", name="request_traces", query="(tempo datasource not configured)",
                window_minutes=minutes, anomalous=False,
                detail="Tracing backend not configured in this deployment — trace analysis skipped, "
                       "no telemetry fabricated.",
            )
        ]


class AlertScanner:
    name = "Alert Scanner"
    permissions = ("read", "analyze")

    def observe(self, telemetry) -> list[TelemetryEvidence]:
        alerts = telemetry.list_alerts()
        firing = [a for a in alerts if "firing" in a.lower()]
        return [
            TelemetryEvidence(
                kind="alert", name="alert_rules", query="list_alert_rules", lines=alerts,
                latest=float(len(firing)), unit="firing", anomalous=bool(firing),
                detail=f"{len(firing)} alert rule(s) firing" if firing else "No alert rules firing",
            )
        ]
