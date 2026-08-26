"""Export the durable document store for the hosted (PostgreSQL-less) legs.

Writes data/hosted-snapshot/documents.jsonl — one row per document:
{kind, id, status, escalated, doc}. app/memory/durable.py seeds a fresh
in-memory store from it when no PostgreSQL is configured, so a Cloud Run
deployment carries the studio's record exactly as it stood at export.

Run from the repo root with the venv python:  .venv/bin/python ops/export_snapshot.py
"""
from __future__ import annotations

import json
from pathlib import Path

from app.config import settings


def main() -> None:
    import psycopg

    out = settings.data_dir / "hosted-snapshot" / "documents.jsonl"
    out.parent.mkdir(parents=True, exist_ok=True)
    with psycopg.connect(settings.postgres_dsn, connect_timeout=4) as conn:
        rows = conn.execute(
            "SELECT kind, id, status, escalated, doc FROM documents ORDER BY updated_at"
        ).fetchall()
    with out.open("w", encoding="utf-8") as fh:
        for kind, doc_id, status, escalated, doc in rows:
            fh.write(json.dumps({
                "kind": kind, "id": doc_id, "status": status or "",
                "escalated": bool(escalated), "doc": doc,
            }, default=str) + "\n")
    print(f"exported {len(rows)} documents → {out}")


if __name__ == "__main__":
    main()
