"""Correlation cognition (locked §6): observation → hypothesis → evidence →
validation. Cognition proposes the causal chain; validation is rule-based —
a chain is only validated when enough independent signals are actually
anomalous in the window.
"""
from __future__ import annotations

from app.events.bus import EventBus
from app.models.operational import CausalHypothesis, Investigation
from app.tools.google.gemini import Cognition


class CorrelationAgent:
    name = "Correlation Agent"
    permissions = ("read", "analyze", "recommend")

    def __init__(self, cognition: Cognition, bus: EventBus):
        self.cognition = cognition
        self.bus = bus

    def correlate(self, inv: Investigation) -> None:
        signals = [
            {"id": e.id, "name": e.name, "latest": e.latest, "slope_per_min": e.slope_per_min,
             "anomalous": e.anomalous}
            for e in inv.evidence
        ]
        result = self.cognition.generate_json("correlation_hypothesis", {"signals": signals})
        anomalous_count = sum(1 for s in signals if s["anomalous"])
        related = bool(result.get("related")) and anomalous_count >= 3
        hypothesis = CausalHypothesis(
            chain=[str(step) for step in result.get("chain", [])],
            rationale=result.get("rationale", ""),
            related=related,
            validated=related,
            validation_notes=(
                f"{anomalous_count} independent anomalous signals support the chain"
                if related else f"only {anomalous_count} anomalous signals — chain not validated"
            ),
        )
        inv.correlation = hypothesis
        self.bus.emit("correlation.formed", investigation_id=inv.id, related=hypothesis.related,
                      chain=hypothesis.chain, validated=hypothesis.validated)
