"""Runtime configuration for Genesis OS — Operational Intelligence."""
from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()


def _truthy(value: str | None) -> bool:
    return (value or "").strip().lower() in {"1", "true", "yes", "on"}


@dataclass(frozen=True)
class Thresholds:
    """Anomaly + capacity thresholds for the render pipeline (studio ops policy)."""

    gpu_utilization_pct: float = 90.0
    queue_depth: float = 60.0
    render_latency_s: float = 6.0
    worker_error_rate_per_min: float = 3.0
    queue_capacity: float = 100.0
    log_error_count: int = 8
    # Some signals are anomalous when they fall, not when they rise. Workers
    # sitting idle is only interesting when there is work waiting for them —
    # that pairing is what separates "blocked" from "quiet", and it is the
    # only thing that distinguishes a licence outage from ordinary slowness.
    workers_rendering_min: float = 4.0
    gpu_temperature_c: float = 85.0


@dataclass(frozen=True)
class Settings:
    grafana_mcp_url: str = field(default_factory=lambda: os.getenv("GRAFANA_MCP_URL", "").strip())
    grafana_mcp_token: str = field(default_factory=lambda: os.getenv("GRAFANA_MCP_TOKEN", "").strip())
    prometheus_uid: str = field(default_factory=lambda: os.getenv("GRAFANA_PROMETHEUS_UID", "").strip())
    loki_uid: str = field(default_factory=lambda: os.getenv("GRAFANA_LOKI_UID", "").strip())
    simulator_control_url: str = field(
        default_factory=lambda: os.getenv("SIMULATOR_CONTROL_URL", "http://localhost:9105").strip()
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
            "POSTGRES_DSN", "postgresql://genesis:genesis@localhost:5434/genesis_ops"
        ).strip()
    )
    nats_url: str = field(default_factory=lambda: os.getenv("NATS_URL", "nats://localhost:4224").strip())
    nats_subject: str = field(default_factory=lambda: os.getenv("NATS_SUBJECT", "genesis.ops.events").strip())
    temporal_address: str = field(
        default_factory=lambda: os.getenv("TEMPORAL_ADDRESS", "localhost:7234").strip()
    )
    temporal_task_queue: str = field(
        default_factory=lambda: os.getenv("TEMPORAL_TASK_QUEUE", "genesis-ops-investigations").strip()
    )
    redis_url: str = field(default_factory=lambda: os.getenv("REDIS_URL", "redis://localhost:6381/0").strip())
    otlp_endpoint: str = field(
        default_factory=lambda: os.getenv("OTEL_EXPORTER_OTLP_ENDPOINT", "http://localhost:4318").strip()
    )
    # The mission loop (Phase C): investigations start from firing alerts read
    # through the MCP server, and the agent writes its audit trail back onto
    # the dashboards as annotations. Both honest-degrade when unavailable.
    alert_watch: bool = field(default_factory=lambda: _truthy(os.getenv("ALERT_WATCH", "on")))
    alert_watch_interval_s: float = field(
        default_factory=lambda: float(os.getenv("ALERT_WATCH_INTERVAL_S", "45"))
    )
    grafana_public_url: str = field(
        default_factory=lambda: os.getenv("GRAFANA_PUBLIC_URL", "http://localhost:3001").strip().rstrip("/")
    )
    local_grafana_url: str = field(
        default_factory=lambda: os.getenv("LOCAL_GRAFANA_URL", "http://localhost:3001").strip().rstrip("/")
    )
    local_grafana_auth: str = field(
        default_factory=lambda: os.getenv("LOCAL_GRAFANA_AUTH", "admin:genesis").strip()
    )
    irm_incidents: bool = field(default_factory=lambda: _truthy(os.getenv("IRM_INCIDENTS", "on")))
    thresholds: Thresholds = field(default_factory=Thresholds)

    @property
    def grafana_live(self) -> bool:
        return bool(self.grafana_mcp_url) and not self.force_mock

    @property
    def gemini_live(self) -> bool:
        if self.force_mock:
            return False
        return bool(self.google_api_key) or (self.use_vertex and bool(self.google_project))

    def banner(self) -> str:
        return (
            "Genesis OS — Operational Intelligence | "
            f"Grafana MCP: {'LIVE ' + self.grafana_mcp_url if self.grafana_live else 'MOCK'} | "
            f"Gemini({self.gemini_model}): {'LIVE' if self.gemini_live else 'MOCK'}"
        )


settings = Settings()
settings.data_dir.mkdir(parents=True, exist_ok=True)
