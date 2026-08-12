"""End-to-end OBSERVE→…→VERIFY loop in mock mode (clean clone, no keys)."""
from app.models.operational import InvestigationStatus, Severity
from app.workflows.run_investigation import get_runtime, run_investigation, start_investigation


def _run_to_recommendation():
    inv = start_investigation("How is production doing right now?")
    run_investigation(inv.id)
    return get_runtime().working.get(inv.id)


def test_investigation_reaches_authorization_gate():
    inv = _run_to_recommendation()
    assert inv.status == InvestigationStatus.AWAITING_AUTHORIZATION, inv.error

    stage_names = [s.name for s in inv.stages]
    for expected in ("OBSERVE", "CORRELATE", "DIAGNOSE", "PREDICT", "RECOMMEND"):
        assert expected in stage_names

    assert len(inv.evidence) >= 6  # 4 metrics + logs + trace(skip notice) + alerts
    assert len(inv.anomalous_evidence) >= 4
    assert inv.correlation is not None and inv.correlation.validated
    assert len(inv.diagnoses) >= 2  # competing hypotheses, not a single answer
    leading = inv.leading_diagnosis
    assert leading is not None
    assert leading.confidence > 0.7
    assert leading.severity in (Severity.HIGH, Severity.CRITICAL)
    assert inv.diagnoses[1].contradicting_evidence_ids or inv.diagnoses[1].contradiction_notes
    assert inv.projection is not None and inv.projection.eta_minutes and inv.projection.eta_minutes > 0
    assert inv.plan is not None and inv.plan.authorization_required
    assert inv.scope[0] == "Convergence Studios"  # scoped context chain (§11)


def test_approval_acts_and_verifies_improvement():
    inv = _run_to_recommendation()
    runtime = get_runtime()
    runtime.executive.execute_decision(inv, "approved")

    assert inv.status == InvestigationStatus.REMEDIATED
    assert inv.verification is not None and inv.verification.improved
    assert inv.verification.after["gpu_utilization_pct"] < inv.verification.before["gpu_utilization_pct"]
    assert inv.verification.after["render_queue_depth"] < inv.verification.before["render_queue_depth"]

    events = {e["event"] for e in runtime.bus.tail(400)}
    assert {"telemetry.observed", "anomaly.detected", "correlation.formed", "diagnosis.formed",
            "risk.projected", "remediation.recommended", "authorization.decided",
            "remediation.executed", "remediation.verified", "investigation.completed"} <= events


def test_rejection_stops_without_acting():
    inv = _run_to_recommendation()
    runtime = get_runtime()
    runtime.executive.execute_decision(inv, "rejected")
    assert inv.status == InvestigationStatus.REJECTED
    assert inv.verification is None  # nothing was executed
