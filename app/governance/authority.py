"""Permission hierarchy and human boundary (locked §10/§16).

READ TELEMETRY → ANALYZE → RECOMMEND → REQUEST AUTHORIZATION → EXECUTE.
Analysts read+analyze; Correlation/Diagnosis/Prediction add recommend;
Remediation's execute permission is restricted — it plans, and execution
happens only after the Studio Head approves.
"""
from __future__ import annotations

from datetime import datetime, timezone

from app.events.bus import EventBus
from app.models.operational import Investigation

PERMISSION_TIERS = {
    "Metrics Analyst": ("read", "analyze"),
    "Log Analyst": ("read", "analyze"),
    "Trace Analyst": ("read", "analyze"),
    "Alert Scanner": ("read", "analyze"),
    "Correlation Agent": ("read", "analyze", "recommend"),
    "Incident Diagnosis Agent": ("read", "analyze", "recommend"),
    "Risk / Prediction Agent": ("read", "analyze", "recommend"),
    "Remediation Planning Agent": ("read", "analyze", "recommend", "execute:restricted"),
    "Operational Executive": ("read", "analyze", "recommend", "execute:approval-only"),
}

VALID_DECISIONS = {"approved", "rejected"}


class AuthorityError(PermissionError):
    pass


def record_decision(inv: Investigation, decision: str, bus: EventBus) -> None:
    if inv.plan is None:
        raise AuthorityError("No remediation plan awaiting a decision on this investigation")
    if inv.plan.decision is not None:
        raise AuthorityError(f"Decision already recorded: {inv.plan.decision}")
    if decision not in VALID_DECISIONS:
        raise AuthorityError(f"Decision must be one of {sorted(VALID_DECISIONS)}")
    inv.plan.decision = decision
    inv.plan.decided_at = datetime.now(timezone.utc)
    inv.stage("STUDIO HEAD DECISION", decision.upper())
    bus.emit("authorization.decided", investigation_id=inv.id, decision=decision, action=inv.plan.action)
