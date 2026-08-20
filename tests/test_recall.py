"""The Recall beat, hermetically: episodic memory primes the loop —
priors inform, evidence decides — and the scoreboard folds honestly."""
from __future__ import annotations

import pytest

from app.memory.stores import EpisodicMemory
from app.models.operational import Investigation
from app.tools.grafana.mcp_client import mock_state


@pytest.fixture()
def runtime(tmp_path, monkeypatch):
    monkeypatch.setenv("GENESIS_MOCK", "1")
    monkeypatch.setenv("GENESIS_DATA_DIR", str(tmp_path))
    from app.workflows import run_investigation as ri

    ri.get_runtime.cache_clear()
    state = mock_state()
    state.remediated = False
    state.allow_improvement = True
    state.firing = []
    state.annotations.clear()
    state.incidents.clear()
    rt = ri.get_runtime()
    yield rt
    ri.get_runtime.cache_clear()


def _finish_one(rt, question: str) -> Investigation:
    # A recovered mock farm reads HEALTHY on the next look — reset the world
    # so each loop investigates a real (mock) incident.
    mock_state().remediated = False
    inv = Investigation(question=question)
    rt.executive.investigate(inv)
    rt.executive.execute_decision(inv, "approved")
    return inv


def test_similar_matches_signature_and_skips_undiagnosed(tmp_path):
    mem = EpisodicMemory(tmp_path)
    healthy = Investigation(question="ALERT Render queue overflow risk: queue above 120")
    mem.record(healthy)  # no diagnosis → not experience
    diagnosed = Investigation(question="ALERT Render queue overflow risk: queue above 120")
    from app.models.operational import DiagnosisHypothesis

    d = DiagnosisHypothesis(cause="Worker saturation from VRAM-heavy jobs", confidence=0.9)
    diagnosed.diagnoses = [d]
    diagnosed.leading_diagnosis_id = d.id
    mem.record(diagnosed)

    hits = mem.similar("ALERT Render queue overflow risk: the queue stayed above 120 jobs")
    assert len(hits) == 1
    assert hits[0]["leading_cause"].startswith("Worker saturation")

    assert mem.similar("completely unrelated dailies chatter") == []


def test_second_incident_recalls_the_first(runtime):
    first = _finish_one(runtime, "ALERT Render queue overflow risk: arrivals beating drain")
    assert first.recall == []  # nothing to remember yet

    second = Investigation(question="ALERT Render queue overflow risk: arrivals beating drain again")
    mock_state().remediated = False
    runtime.executive.investigate(second)
    assert second.recall, "expected episodic recall on the second similar incident"
    assert any(s.name == "RECALL" for s in second.stages)
    assert any("recall" in a["tags"] for a in mock_state().annotations)


def test_episodic_record_carries_clocks_and_action(runtime):
    inv = _finish_one(runtime, "ALERT Render queue overflow risk: clocks test")
    episodes = runtime.episodic.list()
    ep = episodes[-1]
    assert ep["action"], "the plan's action should be remembered"
    assert ep["thinking_s"] is not None and ep["thinking_s"] >= 0
    assert ep["fixed_s"] is not None and ep["fixed_s"] >= ep["thinking_s"]
    assert ep["recalled"] in (0, 1, 2, 3, 4)


def test_scoreboard_folds_the_record(runtime):
    from app.api.routes import scoreboard

    before = scoreboard()
    _finish_one(runtime, "ALERT Render queue overflow risk: fold test one")
    _finish_one(runtime, "ALERT Render queue overflow risk: fold test two")
    after = scoreboard()
    # Deltas, because the episodic store is session-shared across tests.
    assert after["resolved"] - before["resolved"] == 2
    assert after["streak"] >= 2  # two fresh verified wins end the record
    assert after["best_fix_s"] is not None
    assert after["recalled_fixes"] - before["recalled_fixes"] >= 1  # the second remembered the first
