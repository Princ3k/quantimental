"""A minimal thread-safe TTL cache, shared by the services that need one."""

from __future__ import annotations

import threading
import time
from typing import Any, Optional


class TTLCache:
    """Minimal thread-safe TTL cache. Small enough not to warrant a dependency."""

    def __init__(self, ttl_seconds: float) -> None:
        self._ttl = ttl_seconds
        self._entries: dict[str, tuple[float, Any]] = {}
        self._lock = threading.Lock()

    def get(self, key: str) -> Optional[Any]:
        with self._lock:
            entry = self._entries.get(key)
            if entry is None:
                return None
            expires_at, value = entry
            if time.monotonic() > expires_at:
                del self._entries[key]
                return None
            return value

    def set(self, key: str, value: Any) -> None:
        with self._lock:
            self._entries[key] = (time.monotonic() + self._ttl, value)

    def clear(self) -> None:
        with self._lock:
            self._entries.clear()
