"""The runtime-proof ledger is the one thing a reviewer is asked to trust, so
its precedence rules get tested directly.

The rule under test: an *observation* (LIVE/DEGRADED — something was actually
used) outranks a *declaration* (IDLE/MOCK — something is merely configured),
no matter which process made it. The loop normally runs in a Temporal worker
while /status is served by the API, so this has to hold across processes.
"""
from __future__ import annotations

import json

import pytest

from app import runtime_proof


class FakeRedis:
    """Stands in for the shared ledger — this is about precedence, not Redis."""

    def __init__(self) -> None:
        self.store: dict[str, bytes] = {}

    def setex(self, key: str, _ttl: int, value: str) -> None:
        self.store[key] = value.encode()

    def get(self, key: str) -> bytes | None:
        return self.store.get(key)


@pytest.fixture
def shared(monkeypatch) -> FakeRedis:
    fake = FakeRedis()
    runtime_proof.reset()
    monkeypatch.setattr(runtime_proof, "_client", lambda: fake)
    yield fake
    runtime_proof.reset()


def test_declaration_never_overwrites_another_process_observation(shared):
    """The regression: a worker earns LIVE, then the API starts up and declares
    IDLE. _current only consulted this process's local ledger, so the API's own
    IDLE was all the guard ever saw and it wrote IDLE over the worker's LIVE."""
    runtime_proof.record("datahub", "LIVE", "worker emitted an entity")

    runtime_proof.reset()  # a separate process: empty local ledger
    runtime_proof.declare("datahub", "IDLE", "configured — not contacted yet")

    assert json.loads(shared.store["genesis:proof:datahub"])["state"] == "LIVE"


def test_status_prefers_a_shared_observation_over_a_local_declaration(shared):
    """Even once the API holds its own local IDLE, /status must report the LIVE
    the worker earned — otherwise the footer calls a substrate untouched while
    it is actively in use."""
    runtime_proof.record("datahub", "LIVE", "worker emitted an entity")
    runtime_proof.reset()
    runtime_proof.declare("datahub", "IDLE", "configured — not contacted yet")

    snap = runtime_proof.snapshot({"datahub": ("IDLE", "configured default")})
    assert snap["datahub"]["state"] == "LIVE"
    assert snap["datahub"]["note"] == "worker emitted an entity"


def test_a_failure_is_still_reported_over_a_later_declaration(shared):
    """DEGRADED is an observation too: a substrate that was tried and failed
    must not be laundered back to IDLE by a restart."""
    runtime_proof.record("datahub", "DEGRADED", "emission failed (connection refused)")
    runtime_proof.reset()
    runtime_proof.declare("datahub", "IDLE", "configured — not contacted yet")

    assert runtime_proof.snapshot({"datahub": ("IDLE", "d")})["datahub"]["state"] == "DEGRADED"


def test_configuration_shows_through_when_nothing_was_observed(shared):
    """A configured-but-untouched substrate reads IDLE, never LIVE."""
    snap = runtime_proof.snapshot({"datahub": ("IDLE", "configured at localhost:8080")})
    assert snap["datahub"]["state"] == "IDLE"


def test_an_observation_still_replaces_an_earlier_declaration(shared):
    """The guard must not freeze a substrate at IDLE — record() is first-hand
    and always wins."""
    runtime_proof.declare("datahub", "IDLE", "configured — not contacted yet")
    runtime_proof.record("datahub", "LIVE", "knowledge entity emitted")

    assert runtime_proof.snapshot({"datahub": ("IDLE", "d")})["datahub"]["state"] == "LIVE"
