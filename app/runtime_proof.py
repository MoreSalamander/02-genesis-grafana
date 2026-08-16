"""Runtime-proof ledger — what this process has actually exercised.

VENDORED, NOT SHARED: copied verbatim into every Genesis system.

The console footer (UX-IMPROVEMENTS #3) renders this so a Stage One reviewer
can see partner usage without going hunting for it. The whole point is that
the claim is checkable, so the states are deliberately narrow:

    LIVE      the substrate was actually used, successfully, in this process
    DEGRADED  it was configured and tried, and the attempt failed (we fell back)
    MOCK      deliberately not live — no credential, or GENESIS_MOCK is set
    IDLE      configured and ready, but nothing has exercised it yet

A configured-but-untouched substrate reads IDLE, never LIVE. Nothing in the
UI may upgrade a state on its own; it renders exactly what lands here.
"""
from __future__ import annotations

import threading

STATES = ("LIVE", "DEGRADED", "MOCK", "IDLE")

_lock = threading.Lock()
_observed: dict[str, tuple[str, str]] = {}


def record(substrate: str, state: str, note: str) -> None:
    """Record a first-hand observation. Call this at the moment of truth —
    where a dispatch returns, where an emit succeeds or raises."""
    if state not in STATES:
        raise ValueError(f"unknown runtime state {state!r}")
    with _lock:
        _observed[substrate] = (state, note[:200])


def observed(substrate: str) -> tuple[str, str] | None:
    with _lock:
        return _observed.get(substrate)


def snapshot(configured: dict[str, tuple[str, str]]) -> dict[str, dict[str, str]]:
    """Merge configuration-derived defaults with anything actually observed.

    `configured` maps substrate -> (state, note) describing what the process is
    set up to do. Observations always win: they are first-hand.
    """
    with _lock:
        merged: dict[str, dict[str, str]] = {}
        for name, (state, note) in configured.items():
            seen = _observed.get(name)
            if seen is not None:
                merged[name] = {"state": seen[0], "note": seen[1]}
            else:
                merged[name] = {"state": state, "note": note}
        return merged


def reset() -> None:
    """Tests only."""
    with _lock:
        _observed.clear()
