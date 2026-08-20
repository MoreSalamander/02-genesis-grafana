"""Perception log — what the system actually saw, call by call.

The console's rebuilt board shows two minds: the agent thinking (the cognition
ledger) and the system seeing (this). Every Grafana MCP tool call is recorded
here at the moment it returns — tool, duration, ok, and a one-line note of
what came back — so "what the agent saw to make its decision" is the real
retrieval trail, not a story assembled from its conclusions afterwards.

Same design as the cognition ledger, for the same reason: JSONL in the shared
data dir, because the retrievals happen in the Temporal worker while the
console asks the API process.
"""
from __future__ import annotations

import json
import threading
from datetime import datetime, timezone
from pathlib import Path

_LOCK = threading.Lock()
_MAX_RECORDS = 400


def _path() -> Path:
    from app.config import settings

    return settings.data_dir / "perception.jsonl"


def record(tool: str, ms: int, ok: bool, note: str = "", ref: str | None = None) -> None:
    """One retrieval, as it happened. Never raises — a broken log must not
    take down the call it is describing."""
    try:
        from app import cognition_ledger

        entry = {
            "at": datetime.now(timezone.utc).isoformat(),
            "tool": tool,
            "ms": ms,
            "ok": ok,
            "note": note[:200],
            "ref": ref or cognition_ledger.current_ref() or "",
        }
        with _LOCK:
            path = _path()
            path.parent.mkdir(parents=True, exist_ok=True)
            lines = []
            if path.exists():
                lines = path.read_text(encoding="utf-8").splitlines()[-(_MAX_RECORDS - 1):]
            lines.append(json.dumps(entry, ensure_ascii=False))
            path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    except Exception:
        pass


def tail(limit: int = 60) -> list[dict]:
    try:
        path = _path()
        if not path.exists():
            return []
        out = []
        for line in path.read_text(encoding="utf-8").splitlines()[-limit:]:
            try:
                out.append(json.loads(line))
            except json.JSONDecodeError:
                continue
        return out[::-1]  # newest first
    except Exception:
        return []
