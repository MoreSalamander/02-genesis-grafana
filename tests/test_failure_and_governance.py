"""Locked failure philosophy (§15): action submission ≠ outcome; failed
verification escalates. Governance (§10/§16): decisions are gated and single-use."""
import pytest

from app.governance.authority import AuthorityError, record_decision
from app.models.operational import Investigation, InvestigationStatus
from app.tools.grafana.mcp_client import mock_state
from app.workflows.run_investigation import get_runtime, run_investigation, start_investigation


def _run_to_recommendation():
    inv = start_investigation("How is production doing right now?")
    run_investigation(inv.id)
    return get_runtime().working.get(inv.id)


def test_failed_verification_escalates():
    mock_state().allow_improvement = False  # actuation lands but telemetry never improves
    inv = _run_to_recommendation()
    runtime = get_runtime()
    runtime.executive.execute_decision(inv, "approved")

    assert inv.status == InvestigationStatus.REMEDIATION_FAILED
    assert inv.escalated
    assert inv.verification is not None and not inv.verification.improved
    events = {e["event"] for e in runtime.bus.tail(400)}
    assert "remediation.failed" in events
    assert "escalation.raised" in events


def test_decision_guards():
    runtime = get_runtime()
    no_plan = Investigation(question="q?")
    with pytest.raises(AuthorityError):
        record_decision(no_plan, "approved", runtime.bus)

    inv = _run_to_recommendation()
    with pytest.raises(AuthorityError):
        record_decision(inv, "escalate_to_board", runtime.bus)  # not a valid decision
    record_decision(inv, "rejected", runtime.bus)
    with pytest.raises(AuthorityError):
        record_decision(inv, "approved", runtime.bus)  # single-use


def test_prediction_math_uses_real_slope():
    inv = _run_to_recommendation()
    queue = next(e for e in inv.evidence if e.name == "render_queue_depth")
    expected_eta = (100.0 - queue.latest) / queue.slope_per_min
    assert inv.projection is not None
    assert abs(inv.projection.eta_minutes - round(min(max(expected_eta, 0), 240), 1)) < 0.51
