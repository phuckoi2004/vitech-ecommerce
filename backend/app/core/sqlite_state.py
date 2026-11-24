"""Durable auth state for local development; production continues to require Redis."""
from __future__ import annotations

import json
import math
import sqlite3
import threading
import time
from contextlib import contextmanager
from pathlib import Path

from .errors import StateUnavailable


class SQLiteStateStore:
    def __init__(self, path, *, now=time.time):
        self.path = Path(path).resolve()
        self._now = now
        self._local = threading.local()
        self._operation_lock = threading.RLock()
        try:
            self.path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
            with self._connection() as connection:
                connection.execute("PRAGMA journal_mode=WAL")
                connection.execute("CREATE TABLE IF NOT EXISTS auth_state ("
                                   "key TEXT PRIMARY KEY, value TEXT NOT NULL, expires_at REAL NOT NULL)")
                connection.execute("CREATE INDEX IF NOT EXISTS auth_state_expiry ON auth_state(expires_at)")
        except (OSError, sqlite3.Error):
            raise StateUnavailable() from None

    @contextmanager
    def _connection(self):
        existing = getattr(self._local, "connection", None)
        if existing is not None:
            yield existing
            return
        connection = None
        try:
            connection = sqlite3.connect(self.path, timeout=3, isolation_level=None)
            yield connection
        except sqlite3.Error:
            raise StateUnavailable() from None
        finally:
            if connection is not None:
                connection.close()

    def get(self, key):
        with self._connection() as connection:
            row = connection.execute("SELECT value, expires_at FROM auth_state WHERE key = ?", (key,)).fetchone()
            if row is None:
                return None
            if row[1] <= self._now():
                connection.execute("DELETE FROM auth_state WHERE key = ? AND expires_at <= ?", (key, self._now()))
                return None
            try:
                value = json.loads(row[0])
                if not isinstance(value, dict):
                    raise ValueError()
                return value
            except (ValueError, TypeError):
                raise StateUnavailable() from None

    def put(self, key, value, ttl):
        try:
            encoded = json.dumps(value)
        except (ValueError, TypeError):
            raise StateUnavailable() from None
        with self._connection() as connection:
            now = self._now()
            connection.execute("DELETE FROM auth_state WHERE expires_at <= ?", (now,))
            connection.execute("INSERT INTO auth_state(key, value, expires_at) VALUES (?, ?, ?) "
                               "ON CONFLICT(key) DO UPDATE SET value = excluded.value, expires_at = excluded.expires_at",
                               (key, encoded, now + max(1, math.ceil(ttl))))

    def delete(self, key):
        with self._connection() as connection:
            connection.execute("DELETE FROM auth_state WHERE key = ?", (key,))

    @contextmanager
    def lock(self, key):
        # Serialize nested user/session locks across threads and reload processes. Like Memory/Redis stores,
        # security updates (failed attempts, replay revocation) must survive an AuthError from the caller.
        with self._operation_lock:
            if getattr(self._local, "connection", None) is not None:
                yield
                return
            with self._connection() as connection:
                connection.execute("BEGIN IMMEDIATE")
                self._local.connection = connection
                try:
                    yield
                finally:
                    try:
                        connection.commit()
                    finally:
                        self._local.connection = None
