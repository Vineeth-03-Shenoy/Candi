"""
Research Cache — SQLite-backed TTL cache for expensive research operations (B.9).

Caches web-sourced research results keyed by company+role and per-skill Q&A.
Repeat preparations for the same company or overlapping skillsets hit the cache
instead of re-running searches, scrapes, and LLM synthesis — near-zero marginal
cost per repeat run.

Database file: backend/candi_cache.db  (gitignored)

Schema: key/value with stored_at and ttl_seconds; expired entries are silently
evicted on get() and can be reaped in bulk via clear_expired().
"""
import json
import time
from pathlib import Path
from typing import Optional

from app.utils.logger import get_logger

log = get_logger(__name__)

_DB_PATH = Path(__file__).resolve().parents[2] / "candi_cache.db"


class CacheService:
    """Tiny SQLite key-value cache with per-entry TTL."""

    def __init__(self, db_path: Path = _DB_PATH):
        self._db_path = db_path
        conn = self._connect()
        try:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS cache (
                    key        TEXT PRIMARY KEY,
                    value      TEXT NOT NULL,
                    stored_at  REAL NOT NULL,
                    ttl_seconds INTEGER NOT NULL
                )
                """
            )
            conn.commit()
        finally:
            conn.close()
        log.info("CacheService initialised | db=%s", db_path)

    def _connect(self):
        import sqlite3

        return sqlite3.connect(self._db_path)

    # ------------------------------------------------------------------
    # CRUD
    # ------------------------------------------------------------------

    def get(self, key: str) -> Optional[dict]:
        """
        Return the cached value, or None if missing/expired.
        Expired entries are deleted in-place.
        """
        conn = self._connect()
        try:
            row = conn.execute(
                "SELECT value, stored_at, ttl_seconds FROM cache WHERE key = ?",
                (key,),
            ).fetchone()
        finally:
            conn.close()

        if not row:
            return None

        value, stored_at, ttl_seconds = row
        if time.time() - stored_at > ttl_seconds:
            log.debug("Cache entry expired | key=%s", key)
            self.delete(key)
            return None

        log.debug("Cache hit | key=%s", key)
        return json.loads(value)

    def set(self, key: str, value: dict, ttl_seconds: int = 604800) -> None:
        """Insert or replace a cache entry with the given TTL (default 7 days)."""
        now = time.time()
        payload = json.dumps(value, ensure_ascii=False)
        conn = self._connect()
        try:
            conn.execute(
                """
                INSERT INTO cache (key, value, stored_at, ttl_seconds)
                VALUES (?, ?, ?, ?)
                ON CONFLICT(key) DO UPDATE SET
                    value = excluded.value,
                    stored_at = excluded.stored_at,
                    ttl_seconds = excluded.ttl_seconds
                """,
                (key, payload, now, ttl_seconds),
            )
            conn.commit()
        finally:
            conn.close()
        log.info("Cache set | key=%s | bytes=%d | ttl_days=%.1f",
                 key, len(payload), ttl_seconds / 86400)

    def delete(self, key: str) -> bool:
        """Delete a cache entry. Returns True if a row was removed."""
        conn = self._connect()
        try:
            cur = conn.execute("DELETE FROM cache WHERE key = ?", (key,))
            conn.commit()
            deleted = cur.rowcount > 0
        finally:
            conn.close()
        log.debug("Cache delete | key=%s | existed=%s", key, deleted)
        return deleted

    def clear_expired(self) -> int:
        """Delete all expired entries. Returns count removed."""
        cutoff = time.time()
        conn = self._connect()
        try:
            rows = conn.execute(
                "SELECT key FROM cache WHERE stored_at + ttl_seconds < ?",
                (cutoff,),
            ).fetchall()
            if rows:
                conn.execute(
                    "DELETE FROM cache WHERE stored_at + ttl_seconds < ?",
                    (cutoff,),
                )
                conn.commit()
        finally:
            conn.close()
        if rows:
            log.info("Expired cache entries reaped | count=%d", len(rows))
        return len(rows)
