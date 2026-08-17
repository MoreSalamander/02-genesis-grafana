"""Cognition ledger — what the model was actually asked, and what it said back.

VENDORED, NOT SHARED: copied verbatim into every Genesis system.

The console shows the model's reasoning. That is only worth showing if it is
the real thing, so this records the exact prompt sent and the exact text
returned, at the moment of the call. Nothing here is reconstructed afterwards
from the parsed result — a rendering of "what the AI was thinking" that was
assembled from its output would be a story about the output, and the whole
point of putting it on screen is that a reviewer can check it.

Written as JSONL in the shared data dir rather than held in memory, because the
loop usually runs in a Temporal worker while the console is served by the API.
An in-process ledger would be empty in exactly the process the console asks.

Reads come in two sizes on purpose: `tail` returns summaries with no prompt or
response text, because prompts carry whole telemetry payloads and polling them
every two seconds would move megabytes to draw a list. `get` returns one
complete record when somebody actually opens it.
"""
from __future__ import annotations

import json
import os
import threading
import uuid
from contextlib import contextmanager
from contextvars import ContextVar
from datetime import datetime, timezone
from pathlib import Path

_LOCK = threading.Lock()
_MAX_RECORDS = 400          # trimmed from the front; this is a window, not an archive
_PREVIEW_CHARS = 220

# What the current call is being made *for* — set by whatever is running the
# loop, so a call can be traced back to the investigation that caused it.
_REF: ContextVar[str | None] = ContextVar("cognition_ref", default=None)


@contextmanager
def context(ref: str):
    """Tag every model call made inside this block with what it was for."""
    token = _REF.set(ref)
    try:
        yield
    finally:
        _REF.reset(token)


def set_ref(ref: str) -> None:
    """Tag subsequent calls on this thread.

    For the Temporal path, where activities are separate calls on a worker's
    thread pool and there is no single block to wrap. Each activity sets this
    as it loads its investigation, so the value is always the current run's;
    it is overwritten rather than reset, which is why the block form above
    exists for anything that does have a scope.
    """
    _REF.set(ref)


def _path() -> Path:
    try:
        from app.config import settings

        base = Path(settings.data_dir)
    except Exception:
        base = Path(os.getenv("GENESIS_DATA_DIR", "data"))
    return base / "cognition.jsonl"


def record(
    *,
    role: str,
    model: str,
    live: bool,
    prompt: str,
    raw: str,
    ms: int,
    parsed_ok: bool,
    tokens: dict | None = None,
    error: str = "",
) -> str:
    """Record one model call. Never raises: observing the reasoning must not be
    able to break the reasoning."""
    entry = {
        "id": f"cog_{uuid.uuid4().hex[:12]}",
        "at": datetime.now(timezone.utc).isoformat(),
        "role": role,
        "model": model,
        "live": live,
        "ms": ms,
        "parsed_ok": parsed_ok,
        "tokens": tokens or {},
        "ref": _REF.get(),
        "error": error[:400],
        "prompt": prompt,
        "raw": raw,
    }
    try:
        path = _path()
        path.parent.mkdir(parents=True, exist_ok=True)
        with _LOCK:
            with path.open("a", encoding="utf-8") as fh:
                fh.write(json.dumps(entry, ensure_ascii=False, default=str) + "\n")
            _trim(path)
    except Exception as err:
        print(f"[cognition] could not record {role} call: {err}")
    return entry["id"]


def _trim(path: Path) -> None:
    """Keep the file to a window. Called under the lock."""
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
        if len(lines) <= _MAX_RECORDS:
            return
        path.write_text("\n".join(lines[-_MAX_RECORDS:]) + "\n", encoding="utf-8")
    except Exception:
        pass


def _read() -> list[dict]:
    path = _path()
    if not path.exists():
        return []
    out = []
    try:
        for line in path.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            try:
                out.append(json.loads(line))
            except (ValueError, TypeError):
                continue
    except Exception:
        return []
    return out


def tail(limit: int = 40, ref: str | None = None) -> list[dict]:
    """Newest first, without the heavy text. A short preview of the response is
    included so the list says something without carrying the whole payload."""
    items = _read()
    if ref:
        items = [i for i in items if i.get("ref") == ref]
    items = items[-limit:][::-1]
    summaries = []
    for i in items:
        raw = i.get("raw") or ""
        summaries.append({
            "id": i.get("id"),
            "at": i.get("at"),
            "role": i.get("role"),
            "model": i.get("model"),
            "live": i.get("live"),
            "ms": i.get("ms"),
            "parsed_ok": i.get("parsed_ok"),
            "tokens": i.get("tokens") or {},
            "ref": i.get("ref"),
            "error": i.get("error") or "",
            "prompt_chars": len(i.get("prompt") or ""),
            "raw_chars": len(raw),
            "preview": raw[:_PREVIEW_CHARS],
        })
    return summaries


def get(cog_id: str) -> dict | None:
    """One complete record — the exact prompt and the exact response."""
    for entry in reversed(_read()):
        if entry.get("id") == cog_id:
            return entry
    return None
