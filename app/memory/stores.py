"""Working memory (active investigations, in-process) and episodic memory
(completed investigations, persistent) — persistent incident state and
historical operational memory belong to the production architecture (§18)."""
from __future__ import annotations

import json
import threading
from datetime import datetime, timezone
from pathlib import Path

from app.models.operational import Investigation


def _newest(a: Investigation | None, b: Investigation | None) -> Investigation | None:
    if a is None:
        return b
    if b is None:
        return a
    return a if a.updated_at >= b.updated_at else b


class WorkingMemory:
    """Write-through cache over the durable document store (PostgreSQL)."""

    def __init__(self, store):
        self._store = store
        self._items: dict[str, Investigation] = {}
        self._lock = threading.Lock()

    def put(self, inv: Investigation) -> None:
        with self._lock:
            self._items[inv.id] = inv
        try:
            self._store.upsert("investigation", inv.id, inv.status.value, inv.escalated,
                               inv.model_dump(mode="json"))
        except Exception as err:
            print(f"[state] durable persist failed for {inv.id}: {err}")

    def get(self, inv_id: str) -> Investigation | None:
        """Newest copy wins: a Temporal worker may have advanced the durable
        document past this process's cached object (and vice versa for the
        in-process execution path)."""
        with self._lock:
            cached = self._items.get(inv_id)
        doc = self._store.fetch("investigation", inv_id)
        stored = None
        if doc is not None:
            try:
                stored = Investigation.model_validate(doc)
            except Exception:
                stored = None
        winner = _newest(cached, stored)
        if winner is stored and stored is not None:
            with self._lock:
                self._items[inv_id] = stored
        return winner

    def drop(self, inv_id: str) -> bool:
        """Forget an investigation entirely.

        Both sides have to go. all() merges the cache over the durable store,
        so clearing only one of them means the survivor is merged straight back
        in on the next poll and the entry reappears — which is exactly how a
        deleted item came back from the dead in the sibling system.
        """
        with self._lock:
            had = self._items.pop(inv_id, None) is not None
        try:
            self._store.delete("investigation", inv_id)
        except Exception as err:
            print(f"[state] durable delete failed for {inv_id}: {err}")
            return had
        return True

    def all(self) -> list[Investigation]:
        merged: dict[str, Investigation] = {}
        for doc in self._store.list("investigation", limit=100):
            try:
                inv = Investigation.model_validate(doc)
                merged[inv.id] = inv
            except Exception:
                continue
        with self._lock:
            for inv_id, cached in self._items.items():
                merged[inv_id] = _newest(cached, merged.get(inv_id)) or cached
        return sorted(merged.values(), key=lambda i: i.created_at, reverse=True)


class EpisodicMemory:
    def __init__(self, data_dir: Path):
        self.path = data_dir / "episodic_investigations.jsonl"

    def record(self, inv: Investigation) -> None:
        summary = {
            "investigation_id": inv.id,
            "question": inv.question,
            "status": inv.status.value,
            "leading_cause": inv.leading_diagnosis.cause if inv.leading_diagnosis else None,
            "escalated": inv.escalated,
            "improved": inv.verification.improved if inv.verification else None,
            "at": datetime.now(timezone.utc).isoformat(),
        }
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.path.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(summary, ensure_ascii=False) + "\n")

    def list(self, limit: int = 50) -> list[dict]:
        if not self.path.exists():
            return []
        lines = self.path.read_text(encoding="utf-8").splitlines()[-limit:]
        return [json.loads(line) for line in lines]
