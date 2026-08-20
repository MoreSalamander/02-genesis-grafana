"""The Phase C mission loop, hermetically: a firing alert opens an
investigation (once), the loop writes its annotation trail, evidence carries
Grafana deep links, and the IRM incident is opened and closed out."""
from __future__ import annotations

import time

import pytest

from app.agents.watch.alert_watch import AlertWatch
from app.tools.grafana.mcp_client import mock_state


AURORA_ALERT = {
    "fingerprint": "fp-aurora-late-1",
    "alertname": "Show projected late",
    "labels": {"title": "aurora-falls", "severity": "critical", "domain": "slate"},
    "summary": "aurora-falls is projected past its delivery date at current farm throughput.",
    "starts_at": "2026-08-20T12:00:00Z",
}


@pytest.fixture()
def runtime(tmp_path, monkeypatch):
    monkeypatch.setenv("GENESIS_MOCK", "1")
    monkeypatch.setenv("GENESIS_DATA_DIR", str(tmp_path))
    from app.workflows import run_investigation as ri

    ri.get_runtime.cache_clear()
    state = mock_state()
    state.remediated = False
    state.firing = []
    state.annotations.clear()
    state.incidents.clear()
    rt = ri.get_runtime()
    yield rt
    ri.get_runtime.cache_clear()


def _drain_latch(rt):
    from app.memory.ephemeral import INVESTIGATION_LATCH

    rt.ephemeral.release_latch(INVESTIGATION_LATCH)


def test_firing_alert_opens_investigation_once(runtime):
    state = mock_state()
    state.firing = [dict(AURORA_ALERT)]
    watch = AlertWatch()

    inv = watch.poll_once(runtime)
    assert inv is not None
    assert inv.trigger["source"] == "grafana-alert"
    assert inv.trigger["alertname"] == "Show projected late"
    assert "aurora-falls" in inv.question
    assert inv.trigger.get("incident_id", "").startswith("mock-incident")
    assert state.incidents and state.incidents[0]["severity"] == "critical"
    # The opening mark went onto the dashboards.
    assert any("investigation-opened" in a["tags"] for a in state.annotations)

    # Same fingerprint, same firing alert: no second investigation.
    _drain_latch(runtime)
    assert watch.poll_once(runtime) is None


def test_foreign_alerts_do_not_open_investigations(runtime):
    state = mock_state()
    state.firing = [{
        "fingerprint": "fp-foreign", "alertname": "SomeInfraAlert",
        "labels": {"severity": "warning"}, "summary": "not ours",
    }]
    assert AlertWatch().poll_once(runtime) is None


def test_latch_defers_when_investigation_active(runtime):
    from app.memory.ephemeral import INVESTIGATION_LATCH

    runtime.ephemeral.acquire_latch(INVESTIGATION_LATCH, "inv_existing", 60)
    state = mock_state()
    state.firing = [dict(AURORA_ALERT)]
    watch = AlertWatch()
    assert watch.poll_once(runtime) is None
    # Not marked seen — the alert gets its investigation on a later poll.
    _drain_latch(runtime)
    assert watch.poll_once(runtime) is not None


def test_loop_writes_annotation_trail_and_deep_links(runtime):
    state = mock_state()
    inv = runtime.executive.investigate(
        __import__("app.models.operational", fromlist=["Investigation"]).Investigation(
            question="ALERT Show projected late: aurora-falls"
        )
    )
    # Deep links on the evidence, pointing at the provisioned dashboards.
    linked = [e for e in inv.evidence if e.link]
    assert linked, "expected evidence to carry Grafana deep links"
    assert any("/d/farm-floor" in e.link for e in linked)
    assert any("viewPanel=" in e.link for e in linked)
    # Root cause annotated during diagnosis.
    assert any("root-cause" in a["tags"] for a in state.annotations)

    # Approve → act → verify writes the rest of the trail.
    runtime.executive.execute_decision(inv, "approved")
    tags = [t for a in state.annotations for t in a["tags"]]
    assert "decision-approved" in tags
    assert "remediation-applied" in tags
    assert "recovery-confirmed" in tags
    assert inv.annotations_written  # the investigation remembers what it wrote


def test_incident_closed_out_on_finalize(runtime):
    from app.models.operational import Investigation

    state = mock_state()
    inv = Investigation(question="ALERT Show projected late: aurora-falls")
    incident_id = runtime.executive.telemetry.create_incident(title="t", severity="critical")
    inv.trigger = {"source": "grafana-alert", "incident_id": incident_id}
    runtime.executive.investigate(inv)
    runtime.executive.execute_decision(inv, "approved")
    assert state.incidents[0]["activities"], "expected a closing activity on the incident"
    assert "REMEDIATED" in state.incidents[0]["activities"][-1]
