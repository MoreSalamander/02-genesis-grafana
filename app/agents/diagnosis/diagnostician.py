"""Incident Diagnosis cognition (locked §7): competing root-cause hypotheses,
each carrying supporting AND contradicting evidence with confidence and
severity. When top hypotheses are too close to call, the disagreement is
escalated to the human, not silently resolved (locked §15).
"""
from __future__ import annotations

from app.events.bus import EventBus
from app.models.operational import DiagnosisHypothesis, Investigation, Severity
from app.tools.google.gemini import Cognition

DISAGREEMENT_MARGIN = 0.15


class DiagnosisAgent:
    name = "Incident Diagnosis Agent"
    permissions = ("read", "analyze", "recommend")

    def __init__(self, cognition: Cognition, bus: EventBus):
        self.cognition = cognition
        self.bus = bus

    def diagnose(self, inv: Investigation) -> None:
        signals = [
            {"id": e.id, "name": e.name, "latest": e.latest, "slope_per_min": e.slope_per_min,
             "anomalous": e.anomalous, "detail": e.detail}
            for e in inv.evidence
        ]
        log_evidence = next((e for e in inv.evidence if e.kind == "log"), None)
        payload = {
            "signals": signals,
            "log_summary": (log_evidence.lines[:6] if log_evidence else []),
        }
        if inv.recall:
            payload["prior_cases"] = [
                {"cause": p.get("leading_cause"), "improved": p.get("improved"),
                 "status": p.get("status")}
                for p in inv.recall
            ]
        result = self.cognition.generate_json("diagnosis", payload)

        valid_ids = {e.id for e in inv.evidence}
        hypotheses: list[DiagnosisHypothesis] = []
        for item in result.get("hypotheses", []):
            try:
                severity = Severity(str(item.get("severity", "MEDIUM")).upper())
            except ValueError:
                severity = Severity.MEDIUM
            hypotheses.append(
                DiagnosisHypothesis(
                    cause=str(item.get("cause", "unknown")),
                    confidence=max(0.0, min(1.0, float(item.get("confidence", 0.0)))),
                    supporting_evidence_ids=[i for i in item.get("supporting_ids", []) if i in valid_ids],
                    contradicting_evidence_ids=[i for i in item.get("contradicting_ids", []) if i in valid_ids],
                    contradiction_notes=str(item.get("contradiction_notes", "")),
                    severity=severity,
                    affected=str(item.get("affected", "")),
                )
            )
        hypotheses.sort(key=lambda h: h.confidence, reverse=True)
        inv.diagnoses = hypotheses
        if hypotheses:
            inv.leading_diagnosis_id = hypotheses[0].id
            self.bus.emit("diagnosis.formed", investigation_id=inv.id, cause=hypotheses[0].cause,
                          confidence=hypotheses[0].confidence, severity=hypotheses[0].severity.value,
                          competing=len(hypotheses))
            if len(hypotheses) >= 2 and hypotheses[0].confidence - hypotheses[1].confidence < DISAGREEMENT_MARGIN:
                inv.escalated = True
                inv.escalation_reason = (
                    f"Competing diagnoses too close to call: '{hypotheses[0].cause}' "
                    f"({hypotheses[0].confidence:.2f}) vs '{hypotheses[1].cause}' "
                    f"({hypotheses[1].confidence:.2f}) — human review required"
                )
                self.bus.emit("escalation.raised", investigation_id=inv.id, reason=inv.escalation_reason)
