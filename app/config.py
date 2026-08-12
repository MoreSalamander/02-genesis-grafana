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
