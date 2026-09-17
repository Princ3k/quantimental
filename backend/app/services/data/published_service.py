"""
The files the scan publishes, fetched and cached.

`unusual.json` and `signal-desk.json` are written by the scheduled scans and
committed to the repository, the same way `snapshot.json` is. Serving them from
here rather than recomputing matters for one endpoint in particular: the live
`/market/signal-desk` reads a basket of macro instruments from Yahoo and then
calls an LLM, which is fine for a page a human loads occasionally and far too
expensive for something a Discord bot can call on a whim.

So this is deliberately dumb. It fetches a published file, caches it, and hands
it back. No computation, no upstream fan-out, and the wording stays generated
in one place — the scan — rather than being re-derived here and drifting.
"""

from __future__ import annotations

import logging
import os
import threading
import time
from dataclasses import dataclass
from typing import Any, Optional

import httpx

logger = logging.getLogger(__name__)

BASE = os.environ.get(
    "PUBLISHED_BASE",
    "https://raw.githubusercontent.com/Princ3k/quantimental/main/public",
)

# The scans publish hourly at most, so anything shorter is spent re-fetching a
# file that has not changed. Matches snapshot_service.
CACHE_TTL_SECONDS = 300.0
FETCH_TIMEOUT_SECONDS = 10.0


@dataclass
class _Entry:
    payload: dict[str, Any]
    fetched_at: float

    @property
    def age_seconds(self) -> float:
        return time.monotonic() - self.fetched_at


_cache: dict[str, _Entry] = {}
_lock = threading.Lock()


def get(name: str, *, force: bool = False) -> Optional[dict[str, Any]]:
    """One published file, or None when it has never been fetched successfully.

    A failed refresh returns the cached copy rather than nothing — stale beats
    empty for a file that changes hourly. Consumers are expected to read
    `generated_at` and decide for themselves, which is why every published file
    carries one.
    """
    with _lock:
        cached = _cache.get(name)
        if cached and not force and cached.age_seconds < CACHE_TTL_SECONDS:
            return cached.payload

    url = f"{BASE}/{name}"
    try:
        response = httpx.get(url, timeout=FETCH_TIMEOUT_SECONDS)
        response.raise_for_status()
        payload = response.json()
    except Exception as exc:  # noqa: BLE001
        logger.warning("Could not refresh %s: %s", name, exc)
        return cached.payload if cached else None

    if not isinstance(payload, dict):
        logger.warning("%s was not an object; keeping the previous copy.", name)
        return cached.payload if cached else None

    with _lock:
        _cache[name] = _Entry(payload, time.monotonic())
    logger.info("Refreshed %s", name)
    return payload


def reset_cache() -> None:
    """Drop everything cached. For tests."""
    with _lock:
        _cache.clear()
