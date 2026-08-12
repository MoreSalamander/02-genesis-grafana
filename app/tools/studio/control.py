"""Studio actuation boundary. Executing an authorized remediation means calling
the studio's own control plane (the render-farm simulator's control endpoint) —
never anything outside the studio. Mock mode flips the shared scenario state so
telemetry genuinely improves afterwards, exactly like the real simulator would.
"""
from __future__ import annotations

import httpx

from app.config import Settings
from app.tools.grafana.mcp_client import MockOpsState, mock_state


class StudioControl:
    def __init__(self, settings: Settings, state: MockOpsState | None = None):
        self.settings = settings
        self.state = state or mock_state()
        self.live = settings.grafana_live  # actuation goes live alongside telemetry

    def apply(self, actuation: dict) -> tuple[bool, str]:
        if not self.live:
            self.state.remediated = True
            return True, "mock actuation applied to scenario state"
        try:
            response = httpx.post(
                f"{self.settings.simulator_control_url}/control/concurrency",
                json={"factor": float(actuation.get("factor", 0.8))},
                timeout=5.0,
            )
            response.raise_for_status()
            return True, f"simulator accepted concurrency change: {response.json()}"
        except Exception as err:
            return False, f"actuation failed: {err}"
