"""Durable structured state — PostgreSQL (preserved-stack responsibility).

Investigations survive process restarts and instance recycling: the working
memory is a write-through cache over this store. The in-memory implementation
exists for tests/mock mode only; the default configuration includes PostgreSQL
(ops/docker-compose.yml → localhost:5434).
"""
from __future__ import annotations

import json
import threading
from typing import Any, Optional, Protocol

from app.config import Settings

_SCHEMA = """
CREATE TABLE IF NOT EXISTS documents (
    kind        text NOT NULL,
    id          text NOT NULL,
    status      text,
    escalated   boolean DEFAULT false,
    updated_at  timestamptz NOT NULL DEFAULT now(),
    doc         jsonb NOT NULL,
    PRIMARY KEY (kind, id)
);
"""


class DocumentStore(Protocol):
    def upsert(self, kind: str, doc_id: str, status: str, escalated: bool, doc: dict) -> None: ...
    def fetch(self, kind: str, doc_id: str) -> Optional[dict]: ...
    def list(self, kind: str, limit: int = 100) -> list[dict]: ...


class InMemoryStore:
    """Tests / forced-mock only."""

    def __init__(self):
        self._docs: dict[tuple[str, str], dict] = {}
        self._order: list[tuple[str, str]] = []
        self._lock = threading.Lock()

    def upsert(self, kind: str, doc_id: str, status: str, escalated: bool, doc: dict) -> None:
        with self._lock:
            key = (kind, doc_id)
            if key not in self._docs:
                self._order.append(key)
            self._docs[key] = doc

    def fetch(self, kind: str, doc_id: str) -> Optional[dict]:
        with self._lock:
            return self._docs.get((kind, doc_id))

    def list(self, kind: str, limit: int = 100) -> list[dict]:
        with self._lock:
            keys = [k for k in reversed(self._order) if k[0] == kind][:limit]
            return [self._docs[k] for k in keys]


class PostgresStore:
    def __init__(self, dsn: str):
        import psycopg

        self._psycopg = psycopg
        self._dsn = dsn
        self._lock = threading.Lock()
        self._conn = None
        self._connect()
        print(f"[state] PostgreSQL connected: {dsn.rsplit('@', 1)[-1]}")

    def _connect(self) -> None:
        self._conn = self._psycopg.connect(self._dsn, autocommit=True, connect_timeout=4)
        with self._conn.cursor() as cur:
            cur.execute(_SCHEMA)

    def _execute(self, query: str, params: tuple = ()) -> list[tuple]:
        with self._lock:
            for attempt in (1, 2):
                try:
                    with self._conn.cursor() as cur:
                        cur.execute(query, params)
                        if cur.description:
                            return cur.fetchall()
                        return []
                except Exception:
                    if attempt == 2:
                        raise
                    self._connect()  # one reconnect attempt
        return []

    def upsert(self, kind: str, doc_id: str, status: str, escalated: bool, doc: dict) -> None:
        self._execute(
            """
            INSERT INTO documents (kind, id, status, escalated, updated_at, doc)
            VALUES (%s, %s, %s, %s, now(), %s::jsonb)
            ON CONFLICT (kind, id) DO UPDATE
              SET status = EXCLUDED.status,
                  escalated = EXCLUDED.escalated,
                  updated_at = now(),
                  doc = EXCLUDED.doc
            """,
            (kind, doc_id, status, escalated, json.dumps(doc, default=str)),
        )

    def fetch(self, kind: str, doc_id: str) -> Optional[dict]:
        rows = self._execute("SELECT doc FROM documents WHERE kind=%s AND id=%s", (kind, doc_id))
        return rows[0][0] if rows else None

    def list(self, kind: str, limit: int = 100) -> list[dict]:
        rows = self._execute(
            "SELECT doc FROM documents WHERE kind=%s ORDER BY updated_at DESC LIMIT %s", (kind, limit)
        )
        return [r[0] for r in rows]


def get_store(settings: Settings) -> DocumentStore:
    if settings.force_mock or not settings.postgres_dsn:
        return InMemoryStore()
    try:
        return PostgresStore(settings.postgres_dsn)
    except Exception as err:  # resilience fallback — surfaced, never silent
        print(f"[state] PostgreSQL unreachable ({err}) — DEGRADED: in-memory state only")
        return InMemoryStore()
