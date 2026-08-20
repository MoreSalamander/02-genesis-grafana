"""Operational cognition models (locked System-02 V2).

Telemetry is evidence (§5): every conclusion traces back to retrieved signals.
Diagnoses are competing hypotheses with supporting AND contradicting signals
(§7). Remediation never follows automatically from diagnosis (§9), and action
submission is never treated as outcome (§15) — verification is its own stage.
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone
from enum import Enum
from typing import Optional

from pydantic import BaseModel, Field


def new_id(prefix: str) -> str:
    return f"{prefix}_{uuid.uuid4().hex[:12]}"


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


class Severity(str, Enum):
    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"
    CRITICAL = "CRITICAL"


class InvestigationStatus(str, Enum):
    OBSERVING = "OBSERVING"
    CORRELATING = "CORRELATING"
    DIAGNOSING = "DIAGNOSING"
    PREDICTING = "PREDICTING"
    AWAITING_AUTHORIZATION = "AWAITING_AUTHORIZATION"
    REJECTED = "REJECTED"
    ACTING = "ACTING"
    VERIFYING = "VERIFYING"
    REMEDIATED = "REMEDIATED"
    REMEDIATION_FAILED = "REMEDIATION_FAILED"
    ESCALATED = "ESCALATED"
    INCOMPLETE = "INCOMPLETE"
    HEALTHY = "HEALTHY"


class TelemetryEvidence(BaseModel):
    """One retrieved operational signal — metric series, log scan, or alert state."""

    id: str = Field(default_factory=lambda: new_id("tel"))
    kind: str  # metric | log | alert | trace
    name: str
    query: str
    window_minutes: int = 30
    unit: str = ""
    latest: Optional[float] = None
    average: Optional[float] = None
    slope_per_min: Optional[float] = None
    samples: list[tuple[float, float]] = Field(default_factory=list)  # (epoch_s, value)
    lines: list[str] = Field(default_factory=list)  # log/alert lines
    anomalous: bool = False
    detail: str = ""
    source: str = "grafana-mcp"
    link: str = ""  # deep link back to the Grafana panel this signal lives on
    retrieved_at: datetime = Field(default_factory=utcnow)


class CausalHypothesis(BaseModel):
    id: str = Field(default_factory=lambda: new_id("cor"))
    chain: list[str] = Field(default_factory=list)
    rationale: str = ""
    related: bool = False
    validated: bool = False
    validation_notes: str = ""


class DiagnosisHypothesis(BaseModel):
    id: str = Field(default_factory=lambda: new_id("dgn"))
    cause: str
    confidence: float
    supporting_evidence_ids: list[str] = Field(default_factory=list)
    contradicting_evidence_ids: list[str] = Field(default_factory=list)
    contradiction_notes: str = ""
    severity: Severity = Severity.MEDIUM
    affected: str = ""


class RiskProjection(BaseModel):
    id: str = Field(default_factory=lambda: new_id("rsk"))
    event: str
    eta_minutes: Optional[float] = None
    at_risk: str = ""
    basis: str = ""


class RemediationPlan(BaseModel):
    id: str = Field(default_factory=lambda: new_id("rem"))
    action: str
    expected_effects: list[str] = Field(default_factory=list)
    risk: Severity = Severity.MEDIUM
    actuation: dict = Field(default_factory=dict)
    authorization_required: bool = True
    decision: Optional[str] = None  # approved | rejected
    decided_at: Optional[datetime] = None


class VerificationResult(BaseModel):
    improved: bool
    before: dict[str, float] = Field(default_factory=dict)
    after: dict[str, float] = Field(default_factory=dict)
    notes: str = ""


class Stage(BaseModel):
    name: str
    detail: str = ""
    at: datetime = Field(default_factory=utcnow)


class Investigation(BaseModel):
    """Working memory for one operational investigation (scoped context §11)."""

    id: str = Field(default_factory=lambda: new_id("inv"))
    question: str
    scope: list[str] = Field(default_factory=list)  # Studio → Operations → … → Incident
    status: InvestigationStatus = InvestigationStatus.OBSERVING
    stages: list[Stage] = Field(default_factory=list)
    evidence: list[TelemetryEvidence] = Field(default_factory=list)
    correlation: Optional[CausalHypothesis] = None
    diagnoses: list[DiagnosisHypothesis] = Field(default_factory=list)
    leading_diagnosis_id: Optional[str] = None
    projection: Optional[RiskProjection] = None
    plan: Optional[RemediationPlan] = None
    act_snapshot: dict[str, float] = Field(default_factory=dict)  # live baseline captured at actuation
    verification: Optional[VerificationResult] = None
    escalated: bool = False
    escalation_reason: str = ""
    error: str = ""
    # When a firing alert opened this investigation (the Phase C loop), the
    # alert rides along: name, labels, fingerprint, and — when IRM accepted
    # one — the incident id the loop reports back into.
    trigger: Optional[dict] = None
    annotations_written: list[str] = Field(default_factory=list)
    # Episodic recall (the DataHub layer earning its keep): similar past
    # incidents retrieved before observation. Priors inform; evidence decides.
    recall: list[dict] = Field(default_factory=list)
    created_at: datetime = Field(default_factory=utcnow)
    updated_at: datetime = Field(default_factory=utcnow)

    def stage(self, name: str, detail: str = "") -> None:
        self.stages.append(Stage(name=name, detail=detail))
        self.updated_at = utcnow()

    @property
    def leading_diagnosis(self) -> Optional[DiagnosisHypothesis]:
        for d in self.diagnoses:
            if d.id == self.leading_diagnosis_id:
                return d
        return None

    @property
    def anomalous_evidence(self) -> list[TelemetryEvidence]:
        return [e for e in self.evidence if e.anomalous]
