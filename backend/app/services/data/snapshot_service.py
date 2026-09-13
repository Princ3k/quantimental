"""
The published snapshot, read back.

The evening scan writes `snapshot.json` — every measured ticker with its move,
its context sentence and its coverage — and the website reads it straight from
the CDN. This module reads the same file so the API can answer from it.

Reading the published file rather than recomputing is the point, not a
shortcut. A licensee embedding "why did this move" copy beside a position needs
the sentence to be *the same sentence* the rest of the product is showing, and
recomputing on request would mean a Yahoo call per lookup, a different answer
depending on when you asked, and a rate limiter between them and their page.
The file is one scan, one set of numbers, identical for everyone who asks.

The cost is freshness: answers are as recent as the last scan, which runs
hourly through the session. Every response says so — `as_of` is the session
measured and `generated_at` is when the scan ran — because a consumer of this
needs to be able to tell a stale answer from a current one.
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

SNAPSHOT_URL = (
    os.environ.get("SNAPSHOT_URL")
    or "https://raw.githubusercontent.com/Princ3k/quantimental/main/public/snapshot.json"
)

# The scan publishes hourly at most, so anything shorter is spent re-fetching a
# file that has not changed.
CACHE_TTL_SECONDS = 300.0

FETCH_TIMEOUT_SECONDS = 10.0


@dataclass
class Snapshot:
    """One published scan, indexed for lookup."""

    rows: dict[str, dict[str, Any]]
    as_of: Optional[str]
    generated_at: Optional[str]
    fetched_at: float

    @property
    def age_seconds(self) -> float:
        return time.monotonic() - self.fetched_at


_cache: Optional[Snapshot] = None
_lock = threading.Lock()


def _parse(payload: dict[str, Any]) -> Snapshot:
    stocks = payload.get("stocks") or []
    return Snapshot(
        rows={row["t"]: row for row in stocks if row.get("t")},
        as_of=payload.get("as_of"),
        generated_at=payload.get("generated_at"),
        fetched_at=time.monotonic(),
    )


def get_snapshot(force: bool = False) -> Optional[Snapshot]:
    """
    The most recent published scan, or None if one has never been fetched.

    A failed refresh returns the cached copy rather than nothing. The file is
    published by a scheduled job and served from a CDN, so a fetch failing is
    almost always a transient blip at one of those — and a stale sentence with
    an honest `as_of` on it is worth far more to somebody rendering a page than
    a 502 is.
    """
    global _cache

    with _lock:
        cached = _cache
        if cached and not force and cached.age_seconds < CACHE_TTL_SECONDS:
            return cached

    try:
        response = httpx.get(SNAPSHOT_URL, timeout=FETCH_TIMEOUT_SECONDS)
        response.raise_for_status()
        fresh = _parse(response.json())
    except Exception as exc:  # noqa: BLE001
        logger.warning("Could not refresh the snapshot: %s", exc)
        return cached

    if not fresh.rows:
        # A valid document with no stocks in it is a bad publish, not an empty
        # market. Keeping the previous scan is the safer read.
        logger.warning("Published snapshot held no stocks; keeping the previous one.")
        return cached

    with _lock:
        _cache = fresh
    logger.info("Snapshot refreshed: %d tickers, as of %s", len(fresh.rows), fresh.as_of)
    return fresh


def reset_cache() -> None:
    """Drop the cached snapshot. For tests."""
    global _cache
    with _lock:
        _cache = None
