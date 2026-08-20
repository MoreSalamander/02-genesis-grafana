"""Saved plays — the agent's highlight clips.

Inside the code the agent is a legend: every verified fix is captured as a
play, titled, badged, and kept for the reel. Outside the code this is just a
program a studio head trusts to keep the render farm healthy — which is why
every field here is copied from the finished investigation and its stage
timestamps, and none of it is invented. A replay renders recorded data; a
record falls only when a faster fix actually happened; a failed remediation
never becomes a play (it breaks the streak on the scoreboard instead).

Same substrate discipline as the cognition ledger and the perception log:
JSONL in the shared data dir, because fixes finish in the Temporal worker
while the console asks the API process.
"""
from __future__ import annotations

import json
import threading
from datetime import datetime, timezone
from pathlib import Path

from app.models.operational import Investigation

_LOCK = threading.Lock()
_MAX_PLAYS = 120


def _path() -> Path:
    from app.config import settings

    return settings.data_dir / "plays.jsonl"


# One keyword→family mapping for the whole system (the scoreboard's bestiary
# imports this too, so a play and the career page can never disagree).
def cause_family(cause: str | None) -> str | None:
    c = (cause or "").lower()
    if not c:
        return None
    if "vram" in c or "memory" in c or "oom" in c:
        return "vram / out of memory"
    if "licen" in c:
        return "licence"
    if "storage" in c or "asset" in c or "fetch" in c:
        return "storage / assets"
    if "thermal" in c or "temperature" in c or "cooling" in c:
        return "thermal"
    if "saturat" in c or "queue" in c or "concurren" in c or "throttl" in c:
        return "saturation / queue"
    return None


_FAMILY_TITLE = {
    "vram / out of memory": "The VRAM Overrun Save",
    "licence": "The Licence Outage Save",
    "storage / assets": "The Asset Stall Save",
    "thermal": "The Thermal Runaway Save",
    "saturation / queue": "The Queue Flood Save",
}


def _stage_seconds(inv: Investigation, *names: str) -> float | None:
    for s in inv.stages:
        if s.name in names:
            return round((s.at - inv.created_at).total_seconds(), 1)
    return None


def capture(inv: Investigation, episodes_before: list[dict]) -> dict | None:
    """Clip a verified fix. `episodes_before` is the episodic record as it
    stood BEFORE this investigation was written to it — records are judged
    against the career that existed when the play was made."""
    if not (inv.verification and inv.verification.improved):
        return None
    try:
        family = cause_family(inv.leading_diagnosis.cause if inv.leading_diagnosis else None)
        title = _FAMILY_TITLE.get(family or "", "The Recovery Save")
        if inv.recall:
            title += " (from memory)"

        thinking_s = _stage_seconds(inv, "RECOMMEND")
        fixed_s = _stage_seconds(inv, "VERIFY")

        prior_fixes = [e for e in episodes_before if e.get("improved")]
        records: list[str] = []
        prior_best_fix = min((e["fixed_s"] for e in prior_fixes
                              if e.get("fixed_s") is not None), default=None)
        if fixed_s is not None and (prior_best_fix is None or fixed_s < prior_best_fix):
            records.append("fastest_fix")
        prior_best_think = min((e["thinking_s"] for e in episodes_before
                                if e.get("thinking_s") is not None), default=None)
        if thinking_s is not None and (prior_best_think is None or thinking_s < prior_best_think):
            records.append("fastest_thinking")
        if inv.recall and not any(e.get("recalled") and e.get("improved") for e in episodes_before):
            records.append("first_memory_win")
        streak = 1
        for e in reversed(episodes_before):
            if e.get("improved") is True:
                streak += 1
            elif e.get("improved") is False:
                break

        play = {
            "id": "play_" + inv.id.split("_", 1)[-1],
            "at": datetime.now(timezone.utc).isoformat(),
            "investigation_id": inv.id,
            "title": title,
            "family": family,
            "from_alert": bool(inv.trigger),
            "alertname": (inv.trigger or {}).get("alertname", ""),
            "thinking_s": thinking_s,
            "fixed_s": fixed_s,
            "recalled": len(inv.recall),
            "leading_cause": inv.leading_diagnosis.cause if inv.leading_diagnosis else None,
            "action": inv.plan.action if inv.plan else None,
            "before": inv.verification.before,
            "after": inv.verification.after,
            "annotations": list(inv.annotations_written),
            "records": records,
            "streak": streak,
            "timeline": [
                {"name": s.name, "at": s.at.isoformat(), "detail": s.detail[:180]}
                for s in inv.stages
            ],
        }
        with _LOCK:
            path = _path()
            path.parent.mkdir(parents=True, exist_ok=True)
            lines = []
            if path.exists():
                lines = path.read_text(encoding="utf-8").splitlines()[-(_MAX_PLAYS - 1):]
            lines.append(json.dumps(play, ensure_ascii=False))
            path.write_text("\n".join(lines) + "\n", encoding="utf-8")
        return play
    except Exception:
        return None  # a broken clip must never break the loop it celebrates


def tail(limit: int = 30) -> list[dict]:
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
        return out[::-1]
    except Exception:
        return []


def get(play_id: str) -> dict | None:
    for p in tail(limit=_MAX_PLAYS):
        if p.get("id") == play_id:
            return p
    return None
