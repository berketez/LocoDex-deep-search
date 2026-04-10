"""
SQLite-based cache for research results.

Stores completed research results keyed by a SHA-256 hash of the topic
string.  Entries expire after a configurable TTL (default 24 hours).

Usage:
    from utils.research_cache import research_cache

    cached = research_cache.get("quantum computing")
    if cached:
        return cached

    result = await do_expensive_research(...)
    research_cache.set("quantum computing", result)
"""

import hashlib
import json
import os
import sqlite3
import time
import logging

logger = logging.getLogger(__name__)

# Default DB location: next to this file, inside the service directory
_DEFAULT_DB_PATH = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "research_cache.db",
)

# 24 hours in seconds
_DEFAULT_TTL = 24 * 60 * 60


class ResearchCache:
    """Thin SQLite wrapper for caching research results."""

    def __init__(self, db_path: str = _DEFAULT_DB_PATH, ttl: float = _DEFAULT_TTL):
        """
        Args:
            db_path: Path to the SQLite database file.
            ttl:     Time-to-live in seconds for cached entries.
        """
        self.db_path = db_path
        self.ttl = ttl
        self._ensure_table()

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _connect(self) -> sqlite3.Connection:
        return sqlite3.connect(self.db_path)

    def _ensure_table(self) -> None:
        try:
            conn = self._connect()
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS cache (
                    topic_hash  TEXT PRIMARY KEY,
                    topic       TEXT NOT NULL,
                    result      TEXT NOT NULL,
                    created_at  REAL NOT NULL
                )
                """
            )
            conn.commit()
            conn.close()
            logger.info("Research cache initialised at %s", self.db_path)
        except Exception as e:
            logger.error("Failed to initialise research cache: %s", e)

    @staticmethod
    def _hash_topic(topic: str) -> str:
        return hashlib.sha256(topic.strip().lower().encode("utf-8")).hexdigest()

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def get(self, topic: str) -> dict | None:
        """Return the cached result dict for *topic*, or ``None`` if missing / expired."""
        topic_hash = self._hash_topic(topic)
        try:
            conn = self._connect()
            row = conn.execute(
                "SELECT result, created_at FROM cache WHERE topic_hash = ?",
                (topic_hash,),
            ).fetchone()
            conn.close()

            if row is None:
                return None

            result_json, created_at = row
            age = time.time() - created_at
            if age > self.ttl:
                logger.debug("Cache entry for '%s' expired (%.0fs old)", topic, age)
                self.delete(topic)
                return None

            logger.info("Cache HIT for '%s' (%.0fs old)", topic, age)
            return json.loads(result_json)

        except Exception as e:
            logger.error("Cache get error: %s", e)
            return None

    def set(self, topic: str, result: dict) -> None:
        """Store *result* (a JSON-serialisable dict) under *topic*."""
        topic_hash = self._hash_topic(topic)
        try:
            conn = self._connect()
            conn.execute(
                """
                INSERT OR REPLACE INTO cache (topic_hash, topic, result, created_at)
                VALUES (?, ?, ?, ?)
                """,
                (topic_hash, topic.strip(), json.dumps(result, ensure_ascii=False), time.time()),
            )
            conn.commit()
            conn.close()
            logger.info("Cached result for '%s'", topic)
        except Exception as e:
            logger.error("Cache set error: %s", e)

    def delete(self, topic: str) -> None:
        """Remove a single cached entry."""
        topic_hash = self._hash_topic(topic)
        try:
            conn = self._connect()
            conn.execute("DELETE FROM cache WHERE topic_hash = ?", (topic_hash,))
            conn.commit()
            conn.close()
        except Exception as e:
            logger.error("Cache delete error: %s", e)

    def clear(self) -> None:
        """Purge all cached entries."""
        try:
            conn = self._connect()
            conn.execute("DELETE FROM cache")
            conn.commit()
            conn.close()
            logger.info("Research cache cleared")
        except Exception as e:
            logger.error("Cache clear error: %s", e)

    def stats(self) -> dict:
        """Return basic cache statistics."""
        try:
            conn = self._connect()
            total = conn.execute("SELECT COUNT(*) FROM cache").fetchone()[0]
            now = time.time()
            valid = conn.execute(
                "SELECT COUNT(*) FROM cache WHERE (? - created_at) <= ?",
                (now, self.ttl),
            ).fetchone()[0]
            conn.close()
            return {"total_entries": total, "valid_entries": valid, "expired_entries": total - valid}
        except Exception as e:
            logger.error("Cache stats error: %s", e)
            return {"total_entries": 0, "valid_entries": 0, "expired_entries": 0}


# Module-level singleton
research_cache = ResearchCache()
