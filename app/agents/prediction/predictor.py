"""Risk / Prediction cognition (locked §8): current state + trend + capacity =
operational risk assessment. The trend math (time-to-threshold) is computed here
from retrieved telemetry; Gemini writes the projection narrative from those
numbers only — no invented forecasting.
"""
from __future__ import annotations

from app.config import Thresholds
from app.events.bus import EventBus
from app.models.operational import Investigation, RiskProjection
from app.tools.google.gemini import Cognition


class PredictionAgent:
    name = "Risk / Prediction Agent"
    permissions = ("read", "analyze", "recommend")

    def __init__(self, cognition: Cognition, bus: EventBus, thresholds: Thresholds):
        self.cognition = cognition
        self.bus = bus
        self.thresholds = thresholds

    def project(self, inv: Investigation) -> None:
        queue = next((e for e in inv.evidence if e.name == "render_queue_depth"), None)
        if queue is None or queue.latest is None:
            return
        breached = queue.latest >= self.thresholds.queue_capacity
        eta_minutes = None
        if not breached and queue.slope_per_min and queue.slope_per_min > 0:
            eta_minutes = max(0.0, (self.thresholds.queue_capacity - queue.latest) / queue.slope_per_min)
            eta_minutes = round(min(eta_minutes, 240.0), 1)
        payload = {
            "current": queue.latest,
            "slope_per_min": queue.slope_per_min,
            "capacity": self.thresholds.queue_capacity,
            "eta_minutes": eta_minutes,
            "breached": breached,
            "at_risk_jobs": f"{int(queue.latest)} queued jobs",
        }
        result = self.cognition.generate_json("risk_projection", payload)
        inv.projection = RiskProjection(
            event=str(result.get("event", "Capacity threshold breach")),
            eta_minutes=eta_minutes,
            at_risk=str(result.get("at_risk", payload["at_risk_jobs"])),
            basis=str(result.get("basis", "")),
        )
        self.bus.emit("risk.projected", investigation_id=inv.id, projected=inv.projection.event,
                      eta_minutes=eta_minutes)
