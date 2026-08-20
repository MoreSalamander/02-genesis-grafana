"""Remediation Planning cognition (locked §9): a bounded, reversible proposal
with expected effects and risk. Diagnosis does not equal execution — the plan
always requires Studio Head authorization (locked §10).
"""
from __future__ import annotations

from app.events.bus import EventBus
from app.models.operational import Investigation, RemediationPlan, Severity
from app.tools.google.gemini import Cognition


class RemediationAgent:
    name = "Remediation Planning Agent"
    permissions = ("read", "analyze", "recommend")  # execute: restricted (§16)

    def __init__(self, cognition: Cognition, bus: EventBus):
        self.cognition = cognition
        self.bus = bus

    def plan(self, inv: Investigation) -> None:
        leading = inv.leading_diagnosis
        payload = {
            "leading_cause": leading.cause if leading else "unknown",
            "severity": leading.severity.value if leading else "MEDIUM",
            "projection": inv.projection.model_dump() if inv.projection else None,
            "signals": [
                {"name": e.name, "latest": e.latest, "anomalous": e.anomalous} for e in inv.evidence
            ],
        }
        if inv.recall:
            payload["prior_cases"] = [
                {"cause": p.get("leading_cause"), "action": p.get("action"),
                 "improved": p.get("improved")}
                for p in inv.recall
            ]
        result = self.cognition.generate_json("remediation_plan", payload)
        try:
            risk = Severity(str(result.get("risk", "MEDIUM")).upper())
        except ValueError:
            risk = Severity.MEDIUM
        actuation = result.get("actuation") or {}
        if actuation.get("type") != "concurrency":
            actuation = {"type": "concurrency", "factor": 0.8}
        actuation["factor"] = max(0.5, min(1.0, float(actuation.get("factor", 0.8))))
        inv.plan = RemediationPlan(
            action=str(result.get("action", "Reduce render concurrency")),
            expected_effects=[str(x) for x in result.get("expected_effects", [])],
            risk=risk,
            actuation=actuation,
            authorization_required=True,  # never optional (§10)
        )
        self.bus.emit("remediation.recommended", investigation_id=inv.id, action=inv.plan.action,
                      risk=risk.value, actuation=actuation)
