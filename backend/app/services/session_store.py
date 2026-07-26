"""
Session Store — SQLite-backed session persistence (stdlib sqlite3, zero new deps).

Replaces the old in-memory `sessions: dict`:
  - Sessions survive server restarts
  - No unbounded memory growth (data lives on disk)
  - Expired sessions can be reaped by TTL (startup cleanup also deletes the
    matching Chroma vector-store collection)

Database file: backend/candi_sessions.db  (gitignored)

Schema: one row per session — the full session dict (messages, resume_text,
jd_text, prep_data, pdf_path, token_usage) stored as a single JSON blob.
Pydantic models nested inside prep_data (JDInfo/ResumeInfo) are serialised
via model_dump(); they come back as plain dicts, which every current
consumer (prompt context, str(...) fallback) already handles.
"""
import json
import sqlite3
import time
from pathlib import Path
from typing import Optional

from app.utils.logger import get_logger

log = get_logger(__name__)

# This file: backend/app/services/session_store.py  →  parents[2] = backend/
_DB_PATH = Path(__file__).resolve().parents[2] / "candi_sessions.db"


def _json_default(obj):
    """Serialise pydantic models nested inside the session blob."""
    if hasattr(obj, "model_dump"):
        return obj.model_dump()
    raise TypeError(f"Object of type {type(obj).__name__} is not JSON serializable")


class SessionStore:
    """Tiny SQLite key-value store for session state."""

    def __init__(self, db_path: Path = _DB_PATH):
        self._db_path = db_path
        conn = self._connect()
        try:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS sessions (
                    session_id TEXT PRIMARY KEY,
                    data       TEXT NOT NULL,
                    created_at REAL NOT NULL,
                    updated_at REAL NOT NULL
                )
                """
            )
            conn.commit()
        finally:
            conn.close()
        log.info("SessionStore initialised | db=%s", db_path)

    def _connect(self) -> sqlite3.Connection:
        # Fresh short-lived connection per operation — no cross-thread sharing
        # concerns, and negligible cost at localhost scale.
        return sqlite3.connect(self._db_path)

    # ------------------------------------------------------------------
    # CRUD
    # ------------------------------------------------------------------

    def get(self, session_id: str) -> Optional[dict]:
        """Return the session dict, or None if it doesn't exist."""
        conn = self._connect()
        try:
            row = conn.execute(
                "SELECT data FROM sessions WHERE session_id = ?", (session_id,)
            ).fetchone()
        finally:
            conn.close()

        if not row:
            log.debug("Session miss | session_id=%s", session_id)
            return None
        log.debug("Session hit | session_id=%s", session_id)
        return json.loads(row[0])

    def save(self, session_id: str, data: dict) -> None:
        """Insert or update the session blob, preserving created_at."""
        now = time.time()
        payload = json.dumps(data, default=_json_default, ensure_ascii=False)
        conn = self._connect()
        try:
            conn.execute(
                """
                INSERT INTO sessions (session_id, data, created_at, updated_at)
                VALUES (?, ?, ?, ?)
                ON CONFLICT(session_id) DO UPDATE SET
                    data       = excluded.data,
                    updated_at = excluded.updated_at
                """,
                (session_id, payload, now, now),
            )
            conn.commit()
        finally:
            conn.close()
        log.debug("Session saved | session_id=%s | bytes=%d", session_id, len(payload))

    def delete(self, session_id: str) -> bool:
        """Delete a session. Returns True if a row was actually removed."""
        conn = self._connect()
        try:
            cur = conn.execute(
                "DELETE FROM sessions WHERE session_id = ?", (session_id,)
            )
            conn.commit()
            deleted = cur.rowcount > 0
        finally:
            conn.close()
        log.info("Session delete | session_id=%s | existed=%s", session_id, deleted)
        return deleted

    # ------------------------------------------------------------------
    # TTL cleanup
    # ------------------------------------------------------------------

    def cleanup_expired(self, ttl_seconds: int) -> list[str]:
        """
        Delete sessions not updated within ttl_seconds.
        Returns the expired session_ids so the caller can also drop their
        Chroma vector-store collections.
        """
        cutoff = time.time() - ttl_seconds
        conn = self._connect()
        try:
            ids = [
                r[0] for r in conn.execute(
                    "SELECT session_id FROM sessions WHERE updated_at < ?", (cutoff,)
                ).fetchall()
            ]
            if ids:
                conn.execute("DELETE FROM sessions WHERE updated_at < ?", (cutoff,))
                conn.commit()
        finally:
            conn.close()

        if ids:
            log.info("Expired sessions reaped | count=%d | ttl_days=%.1f",
                     len(ids), ttl_seconds / 86400)
        return ids
