"""HTTP interface for the incident console (frontend/) and for the eventual
Genesis OS Operational Intelligence Contract adapter. The standalone owns this
API; the federation consumes it — never the reverse.
"""
from __future__ import annotations

from fastapi import APIRouter, BackgroundTasks, HTTPException
from pydantic import BaseModel, Field

from app.governance.authority import AuthorityError, VALID_DECISIONS
from app.models.operational import Investigation
from app.workflows.run_investigation import get_runtime, run_decision, run_investigation, start_investigation

router = APIRouter(prefix="/api")


class InvestigationRequest(BaseModel):
    question: str = Field(min_length=5, max_length=300, default="How is production doing right now?")


class DecisionRequest(BaseModel):
    decision: str  # approved | rejected


def _summary(inv: Investigation) -> dict:
    leading = inv.leading_diagnosis
    return {
        "id": inv.id,
        "question": inv.question,
        "status": inv.status.value,
        "severity": leading.severity.value if leading else None,
        "leading_cause": leading.cause if leading else None,
        "confidence": leading.confidence if leading else None,
        "escalated": inv.escalated,
        "created_at": inv.created_at,
        "updated_at": inv.updated_at,
    }


@router.get("/status")
def status() -> dict:
    runtime = get_runtime()
    return {
        "system": "Genesis OS — Operational Intelligence",
        "banner": runtime.settings.banner(),
        "grafana_live": runtime.settings.grafana_live,
        "gemini_live": runtime.settings.gemini_live,
        "investigations": len(runtime.working.all()),
    }


@router.post("/investigations", status_code=202)
def create_investigation(body: InvestigationRequest, background: BackgroundTasks) -> dict:
    inv = start_investigation(body.question)
    background.add_task(run_investigation, inv.id)
    return {"id": inv.id, "status": inv.status.value}


@router.get("/investigations")
def list_investigations() -> list[dict]:
    return [_summary(i) for i in get_runtime().working.all()]


@router.get("/investigations/{inv_id}")
def get_investigation(inv_id: str) -> dict:
    inv = get_runtime().working.get(inv_id)
    if inv is None:
        raise HTTPException(404, "investigation not found")
    return inv.model_dump(mode="json")


@router.post("/investigations/{inv_id}/decision", status_code=202)
def decide(inv_id: str, body: DecisionRequest, background: BackgroundTasks) -> dict:
    runtime = get_runtime()
    inv = runtime.working.get(inv_id)
    if inv is None:
        raise HTTPException(404, "investigation not found")
    if body.decision not in VALID_DECISIONS:
        raise HTTPException(400, f"decision must be one of {sorted(VALID_DECISIONS)}")
    if inv.plan is None or inv.plan.decision is not None:
        raise HTTPException(400, "no remediation plan awaiting a decision")
    # act + verify can take a while live (telemetry must actually move) — run in background
    background.add_task(run_decision, inv.id, body.decision)
    return {"id": inv.id, "decision": body.decision, "status": "processing"}


@router.get("/events")
def events(limit: int = 150) -> list[dict]:
    return get_runtime().bus.tail(limit)


@router.get("/memory/episodic")
def episodic(limit: int = 50) -> list[dict]:
    return get_runtime().episodic.list(limit)
