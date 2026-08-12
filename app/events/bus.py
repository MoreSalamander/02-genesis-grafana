"""Operational event contract (designed now for the Genesis OS federation;
transport stays a local JSONL log in the standalone MVP)."""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

EVENT_NAMES = {
    "telemetry.observed",
    "anomaly.detected",
    "correlation.formed",
    "diagnosis.formed",
    "risk.projected",
    "remediation.recommended",
    "authorization.decided",
    "remediation.executed",
    "remediation.verified",
    "remediation.failed",
    "escalation.raised",
    "investigation.completed",
    "investigation.incomplete",
}


class EventBus:
    def __init__(self, data_dir: Path):
        self.path = data_dir / "events.jsonl"

    def emit(self, name: str, **payload) -> None:
        if name not in EVENT_NAMES:
            raise ValueError(f"Unknown event '{name}' — extend the contract first")
        # payload first — the event name and timestamp can never be clobbered by kwargs
        record = {**payload, "event": name, "at": datetime.now(timezone.utc).isoformat()}
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.path.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(record, ensure_ascii=False, default=str) + "\n")

    def tail(self, limit: int = 100) -> list[dict]:
        if not self.path.exists():
            return []
        lines = self.path.read_text(encoding="utf-8").splitlines()[-limit:]
        return [json.loads(line) for line in lines]
