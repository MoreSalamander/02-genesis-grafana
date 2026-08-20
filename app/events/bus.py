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
    # An operator ended and removed a run. Recorded because the audit trail
    # should show that it was cleared deliberately, rather than leaving a run
    # that simply stops appearing with no explanation.
    "investigation.cleared",
    # A firing Grafana alert opened an investigation on its own (the Phase C
    # mission loop). The trigger is on the record because "the system noticed"
    # and "someone asked" are different provenances for the same question.
    "alert.triggered",
    # Episodic memory surfaced similar past incidents before observation —
    # the knowledge layer priming the loop. Priors inform; evidence decides.
    "memory.recalled",
}


class EventBus:
    """Event fabric: NATS publish (genesis.ops.events) + local JSONL audit trail.

    NATS is part of the deployed stack (ops/docker-compose.yml). Publish failures
    degrade to audit-log-only and are surfaced once — never silent, never fatal.
    """

    def __init__(self, data_dir: Path, nats_url: str = "", subject: str = "genesis.ops.events"):
        self.path = data_dir / "events.jsonl"
        self._nats_url = nats_url
        self._subject = subject
        self._nats_warned = False

    def emit(self, name: str, **payload) -> None:
        if name not in EVENT_NAMES:
            raise ValueError(f"Unknown event '{name}' — extend the contract first")
        # payload first — the event name and timestamp can never be clobbered by kwargs
        record = {**payload, "event": name, "at": datetime.now(timezone.utc).isoformat()}
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.path.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(record, ensure_ascii=False, default=str) + "\n")
        self._publish(record)

    def _publish(self, record: dict) -> None:
        if not self._nats_url:
            return
        try:
            import asyncio

            import nats

            async def _pub():
                nc = await nats.connect(self._nats_url, connect_timeout=2, max_reconnect_attempts=1)
                await nc.publish(self._subject, json.dumps(record, ensure_ascii=False, default=str).encode())
                await nc.flush(timeout=2)
                await nc.close()

            asyncio.run(_pub())
        except Exception as err:
            if not self._nats_warned:
                print(f"[events] NATS publish failed ({err}) — DEGRADED: audit log only")
                self._nats_warned = True

    def tail(self, limit: int = 100) -> list[dict]:
        if not self.path.exists():
            return []
        lines = self.path.read_text(encoding="utf-8").splitlines()[-limit:]
        return [json.loads(line) for line in lines]
