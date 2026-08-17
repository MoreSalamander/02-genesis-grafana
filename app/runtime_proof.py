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

import json
import os
import threading

STATES = ("LIVE", "DEGRADED", "MOCK", "IDLE")

# Observations must outlive the process that made them. The loop usually runs
# in a Temporal worker while /status is served by the API, so a purely
# in-process ledger reported IDLE for substrates the worker had just used —
# the footer went dark exactly when the durable architecture was working.
# Redis is already a dependency of every system here, so proof is shared
# through it and falls back to in-process when it is absent.
_PREFIX = "genesis:proof:"
_TTL_S = 6 * 3600          # proof ages out; a LIVE from yesterday proves nothing

_lock = threading.Lock()
_observed: dict[str, tuple[str, str]] = {}
_redis = None
_redis_tried = False
_warned = False


def _client():
    """Best-effort shared backend. Never raises: proof reporting must not be
    able to break a mission."""
    global _redis, _redis_tried
    if _redis_tried:
        return _redis
    _redis_tried = True
    # Read the resolved setting, not the raw env var: REDIS_URL is usually a
    # default in Settings rather than something exported, so os.getenv came back
    # empty and silently disabled sharing altogether.
    try:
        from app.config import settings

        url = (settings.redis_url or "").strip()
        mocked = settings.force_mock
    except Exception:
        url = os.getenv("REDIS_URL", "").strip()
        mocked = os.getenv("GENESIS_MOCK", "").strip().lower() in {"1", "true", "yes", "on"}
    if not url or mocked:
        return None
    try:
        import redis

        client = redis.Redis.from_url(url, socket_connect_timeout=2, socket_timeout=2)
        client.ping()
        _redis = client
    except Exception as err:
        print(f"[proof] shared ledger unavailable ({err}) — per-process proof only")
    return _redis


def record(substrate: str, state: str, note: str) -> None:
    """Record a first-hand observation. Call this at the moment of truth —
    where a dispatch returns, where an emit succeeds or raises."""
    if state not in STATES:
        raise ValueError(f"unknown runtime state {state!r}")
    note = note[:200]
    with _lock:
        _observed[substrate] = (state, note)
    client = _client()
    if client is not None:
        try:
            client.setex(_PREFIX + substrate, _TTL_S, json.dumps({"state": state, "note": note}))
        except Exception as err:
            # A degraded ledger must never degrade the mission, but swallowing
            # this silently made an earlier failure invisible for hours. Warn
            # once, then stay quiet.
            global _warned
            if not _warned:
                _warned = True
                print(f"[proof] shared write failed ({err}) — proof stays per-process")


def declare(substrate: str, state: str, note: str) -> None:
    """Record what this process is *configured* to do — not what it has done.

    Constructing a client says nothing about whether the substrate was used, so
    a declaration must never overwrite a first-hand observation. Without this,
    restarting the API wrote IDLE over the LIVE a worker had just earned, and
    the footer went dark on a substrate that was demonstrably in use.
    """
    if state not in STATES:
        raise ValueError(f"unknown runtime state {state!r}")
    existing = _current(substrate)
    if existing in ("LIVE", "DEGRADED"):
        return
    record(substrate, state, note)


def _shared(substrate: str) -> str | None:
    client = _client()
    if client is None:
        return None
    try:
        raw = client.get(_PREFIX + substrate)
    except Exception:
        return None
    if not raw:
        return None
    try:
        return json.loads(raw).get("state")
    except (ValueError, TypeError):
        return None


def _current(substrate: str) -> str | None:
    """The strongest state known for this substrate, local or shared.

    This used to return the local value whenever one existed and never consult
    the shared ledger, which quietly defeated declare() across processes: the
    API declares IDLE for a substrate at startup, so its own local IDLE was all
    declare() ever saw, and each later declaration wrote that IDLE over the LIVE
    a Temporal worker had genuinely earned. The footer then reported a substrate
    as untouched while the worker was actively using it.

    An observation outranks a declaration no matter which process made it, so
    both sides are checked and the first-hand one wins.
    """
    with _lock:
        local = _observed.get(substrate)
    local_state = local[0] if local is not None else None
    if local_state in ("LIVE", "DEGRADED"):
        return local_state
    shared_state = _shared(substrate)
    if shared_state in ("LIVE", "DEGRADED"):
        return shared_state
    return local_state or shared_state


def observed(substrate: str) -> tuple[str, str] | None:
    with _lock:
        return _observed.get(substrate)


def snapshot(configured: dict[str, tuple[str, str]]) -> dict[str, dict[str, str]]:
    """Merge configuration-derived defaults with anything actually observed.

    `configured` maps substrate -> (state, note) describing what the process is
    set up to do. Observations always win: they are first-hand.
    """
    merged: dict[str, dict[str, str]] = {}
    for name, (state, note) in configured.items():
        with _lock:
            local = _observed.get(name)

        shared: tuple[str, str] | None = None
        client = _client()
        if client is not None:
            try:
                raw = client.get(_PREFIX + name)
            except Exception:
                raw = None
            if raw:
                try:
                    payload = json.loads(raw)
                except (ValueError, TypeError):
                    payload = None
                if payload and payload.get("state") in STATES:
                    shared = (payload["state"], payload.get("note", ""))

        # A first-hand observation outranks a declaration whichever process made
        # it. This loop previously skipped the shared ledger entirely whenever
        # this process held any local value, so the API's own startup IDLE hid
        # the LIVE a Temporal worker had earned doing the actual work.
        for candidate in (local, shared):
            if candidate is not None and candidate[0] in ("LIVE", "DEGRADED"):
                merged[name] = {"state": candidate[0], "note": candidate[1]}
                break
        else:
            chosen = local or shared or (state, note)
            merged[name] = {"state": chosen[0], "note": chosen[1]}
    return merged


def reset() -> None:
    """Tests only."""
    with _lock:
        _observed.clear()
