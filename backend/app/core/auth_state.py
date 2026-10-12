from __future__ import annotations

import copy
import json
import math
import threading
import time
from contextlib import contextmanager
from functools import lru_cache
from typing import Callable, Iterator, Protocol

from .config import AuthSettings
from .errors import StateUnavailable


class StateStore(Protocol):
    def get(self, key: str) -> dict | None: ...
    def put(self, key: str, value: dict, ttl: int) -> None: ...
    def delete(self, key: str) -> None: ...
    def lock(self, key: str): ...


class MemoryStateStore:
    """Single-process store for development/test; never a production fallback."""

    def __init__(self, now: Callable[[], float] = time.monotonic):
        self._now = now
        self._values: dict[str, tuple[float, dict]] = {}
        self._data_lock = threading.RLock()
        # A reentrant operation lock makes nested challenge/session locks safe in
        # development without accumulating one permanent lock per identity.
        self._operation_lock = threading.RLock()

    def get(self, key: str) -> dict | None:
        with self._data_lock:
            entry = self._values.get(key)
            if entry is None:
                return None
            deadline, value = entry
            if deadline <= self._now():
                self._values.pop(key, None)
                return None
            return copy.deepcopy(value)

    def put(self, key: str, value: dict, ttl: int) -> None:
        with self._data_lock:
            # Prune expired entries so untouched expired challenges do not accumulate.
            now = self._now()
            for expired_key in [k for k, (deadline, _) in self._values.items() if deadline <= now]:
                self._values.pop(expired_key, None)
            self._values[key] = (now + max(1, math.ceil(ttl)), copy.deepcopy(value))

    def delete(self, key: str) -> None:
        with self._data_lock:
            self._values.pop(key, None)

    @contextmanager
    def lock(self, key: str) -> Iterator[None]:
        with self._operation_lock:
            yield


class RedisStateStore:
    """Redis operations fail closed, including lock acquisition/release failures."""

    def __init__(self, url: str):
        import redis

        self._redis_errors = redis.exceptions.RedisError
        try:
            self._client = redis.Redis.from_url(
                url, decode_responses=True, socket_timeout=3, socket_connect_timeout=3,
            )
            self._client.ping()
        except (self._redis_errors, ValueError, TypeError):
            raise StateUnavailable() from None

    @staticmethod
    def _key(key: str) -> str:
        return f"vietech:auth:{key}"

    def get(self, key: str) -> dict | None:
        try:
            raw = self._client.get(self._key(key))
            if raw is None:
                return None
            value = json.loads(raw)
            if not isinstance(value, dict):
                raise ValueError()
            return value
        except (self._redis_errors, ValueError, TypeError):
            raise StateUnavailable() from None

    def put(self, key: str, value: dict, ttl: int) -> None:
        try:
            self._client.set(self._key(key), json.dumps(value), ex=max(1, math.ceil(ttl)))
        except (self._redis_errors, ValueError, TypeError):
            raise StateUnavailable() from None

    def delete(self, key: str) -> None:
        try:
            self._client.delete(self._key(key))
        except self._redis_errors:
            raise StateUnavailable() from None

    @contextmanager
    def lock(self, key: str) -> Iterator[None]:
        # These locks protect short auth-state operations, not long business transactions.
        try:
            with self._client.lock(self._key(f"lock:{key}"), timeout=30, blocking_timeout=3):
                yield
        except self._redis_errors:
            raise StateUnavailable() from None


@lru_cache(maxsize=8)
def get_auth_state(settings: AuthSettings) -> StateStore:
    if settings.state_backend == "redis":
        return RedisStateStore(settings.redis_url)
    if settings.app_env not in {"development", "test"}:
        raise StateUnavailable()
    return MemoryStateStore()
