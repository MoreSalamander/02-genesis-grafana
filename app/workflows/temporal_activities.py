"""Temporal activities — each locked loop stage as a durable, retryable unit.

Every activity loads the investigation from PostgreSQL, runs exactly one
cognitive stage through the existing executive, and checkpoints the document
back — so a crashed worker resumes from the last completed stage, not from
scratch.
"""
from __future__ import annotations

from temporalio import activity

from app.models.operational import Investigation, InvestigationStatus


def _runtime():
    from app.workflows.run_investigation import get_runtime

    return get_runtime()


def _load(inv_id: str) -> Investigation:
    inv = _runtime().working.get(inv_id)
    if inv is None:
        raise RuntimeError(f"investigation {inv_id} not found in durable state")
    return inv


def _save(inv: Investigation) -> None:
    _runtime().working.put(inv)


@activity.defn(name="ops.observe")
def observe_activity(inv_id: str) -> str:
    rt = _runtime()
    inv = _load(inv_id)
    inv.scope = rt.executive.knowledge.scope_for("render-worker")
    rt.executive._observe(inv)
    if not inv.anomalous_evidence:
        inv.status = InvestigationStatus.HEALTHY
        inv.stage("ALL CLEAR", "No anomalous operational signals in the window")
        rt.bus.emit("investigation.completed", investigation_id=inv.id, outcome="healthy")
        rt.executive._finalize(inv)
    _save(inv)
    return inv.status.value


@activity.defn(name="ops.correlate")
def correlate_activity(inv_id: str) -> str:
    inv = _load(inv_id)
    _runtime().executive._correlate(inv)
    _save(inv)
    return inv.status.value


@activity.defn(name="ops.diagnose")
def diagnose_activity(inv_id: str) -> str:
    inv = _load(inv_id)
    _runtime().executive._diagnose(inv)
    _save(inv)
    return inv.status.value


@activity.defn(name="ops.predict")
def predict_activity(inv_id: str) -> str:
    inv = _load(inv_id)
    _runtime().executive._predict(inv)
    _save(inv)
    return inv.status.value


@activity.defn(name="ops.recommend")
def recommend_activity(inv_id: str) -> str:
    inv = _load(inv_id)
    _runtime().executive._recommend(inv)
    _save(inv)
    return inv.status.value


@activity.defn(name="ops.decide_reject")
def reject_activity(inv_id: str) -> str:
    rt = _runtime()
    inv = _load(inv_id)
    rt.executive.decide(inv, "rejected")
    rt.executive.reject(inv)
    _save(inv)
    return inv.status.value


@activity.defn(name="ops.act")
def act_activity(inv_id: str) -> bool:
    rt = _runtime()
    inv = _load(inv_id)
    rt.executive.decide(inv, "approved")
    ok = rt.executive.act(inv)
    _save(inv)
    return ok


@activity.defn(name="ops.verify")
def verify_activity(inv_id: str) -> str:
    inv = _load(inv_id)
    _runtime().executive.verify_outcome(inv)
    _save(inv)
    return inv.status.value


@activity.defn(name="ops.incomplete")
def incomplete_activity(inv_id: str, reason: str) -> str:
    rt = _runtime()
    inv = _load(inv_id)
    rt.executive._incomplete(inv, reason)
    _save(inv)
    return inv.status.value


@activity.defn(name="ops.escalate_timeout")
def escalate_timeout_activity(inv_id: str) -> str:
    rt = _runtime()
    inv = _load(inv_id)
    inv.escalated = True
    inv.escalation_reason = "Studio Head decision window expired — escalated without action"
    inv.stage("ESCALATED", inv.escalation_reason)
    inv.status = InvestigationStatus.ESCALATED
    rt.bus.emit("escalation.raised", investigation_id=inv.id, reason=inv.escalation_reason)
    rt.executive._finalize(inv)
    _save(inv)
    return inv.status.value


ALL_ACTIVITIES = [
    observe_activity, correlate_activity, diagnose_activity, predict_activity,
    recommend_activity, reject_activity, act_activity, verify_activity,
    incomplete_activity, escalate_timeout_activity,
]
