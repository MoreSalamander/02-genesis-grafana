"""Ephemeral high-speed state — Redis (preserved-stack responsibility).

Used for short-lived cross-process coordination, never as a knowledge layer:
here, the investigation latch that prevents two investigations from racing the
same operational reality (the exact failure mode concurrent console approvals
produced before durable state landed).
"""
from __future__ import annotations

import threading
import time

from app.config import Settings


class InProcEphemeral:
    """Tests / forced-mock fallback."""

    def __init__(self):
        self._data: dict[str, tuple[str, float]] = {}
        self._lock = threading.Lock()

    def acquire_latch(self, key: str, value: str, ttl_s: int) -> str | None:
        with self._lock:
            existing = self._data.get(key)
            now = time.time()
            if existing and existing[1] > now:
                return existing[0]
            self._data[key] = (value, now + ttl_s)
            return None

    def release_latch(self, key: str) -> None:
        with self._lock:
            self._data.pop(key, None)


class RedisEphemeral:
    def __init__(self, url: str):
        import redis

        self._redis = redis.Redis.from_url(url, socket_connect_timeout=3, socket_timeout=3)
        self._redis.ping()
        print(f"[ephemeral] Redis connected: {url}")

    def acquire_latch(self, key: str, value: str, ttl_s: int) -> str | None:
        """Returns None when acquired; otherwise the current holder's value."""
        if self._redis.set(key, value, nx=True, ex=ttl_s):
            return None
        holder = self._redis.get(key)
        return holder.decode() if holder else "unknown"

    def release_latch(self, key: str) -> None:
        self._redis.delete(key)


def get_ephemeral(settings: Settings):
    if settings.force_mock or not settings.redis_url:
        return InProcEphemeral()
    try:
        return RedisEphemeral(settings.redis_url)
    except Exception as err:
        print(f"[ephemeral] Redis unreachable ({err}) — DEGRADED: in-process latches only")
        return InProcEphemeral()


INVESTIGATION_LATCH = "genesis:ops:investigation:active"
LATCH_TTL_S = 900
