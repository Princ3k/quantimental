"""
Rate limiting for the public API.

The API is unauthenticated by design — the frontend calls it from the browser
with no key, and a per-stock page is meant to be shareable. That makes it
trivially loopable: `/signals/batch` accepts 60 tickers a call, and each one
fans out to Yahoo. A single scraper could spend the month's Railway credit and
get our IP rate-limited by every upstream we depend on, in an afternoon.

Two properties this needs, which a plain requests-per-minute counter does not
have:

**Cost, not calls.** A batch of 60 tickers is sixty times the work of a batch
of one, and a full-depth analyse hits Reddit, MarketAux and an LLM. Counting
both as "one request" prices the expensive paths at zero. Callers spend from a
budget denominated in work.

**Refill, not windows.** A fixed window lets someone burn the entire budget in
its first second and then hammer a closed door, and it resets on a clock edge
everyone can synchronise to. A token bucket refills continuously, so a normal
user who pauses is never punished and a loop is throttled to the refill rate
rather than being allowed to sprint.

State is in-process. That is correct for one Railway instance and wrong for
several; if this ever runs replicated, the buckets need to move to Redis, and
until then each replica would enforce its own share. The limits below are set
well above what the app itself does, so the ceiling is only reachable by
something that is not a person using the site.
"""

from __future__ import annotations

import logging
import threading
import time
from dataclasses import dataclass, field
from typing import Optional

logger = logging.getLogger(__name__)

# Units are "work", where one unit is roughly one upstream ticker fetch.
#
# Sized against the heaviest *legitimate* user, not the average one: someone
# following the full 60-ticker watchlist, refreshing every two minutes, spends
# 60 x 30 = 1,800 units an hour before a single deep dive. An earlier 2,000
# ceiling put that user one refresh from a 429, which is the failure mode worth
# avoiding — a limiter that throttles real use is worse than none, because it
# breaks the product quietly and only for the most engaged people.
#
# 6,000 still bounds the worst case hard. Unmetered, a loop issues thousands of
# ticker fetches a minute; this caps sustained abuse at about a hundred.
HOURLY_BUDGET = 6_000.0

# Ten full 60-ticker batches back to back before any refill is needed, which
# covers a page reload storm without covering a script.
BURST_BUDGET = 600.0

# What each endpoint costs. A deep analyse is expensive in a way that is
# invisible from the request size: it fetches news and social posts per ticker
# and may call an LLM.
COST_PER_TICKER = 1.0
COST_DEEP_ANALYSIS = 25.0
COST_DEFAULT = 1.0

# Paths that never cost anything: uptime checks and the docs.
EXEMPT_PREFIXES = ("/health", "/docs", "/redoc", "/openapi.json", "/")

# Bucket entries are dropped once idle for this long, so the table tracks
# active callers rather than growing forever.
IDLE_EVICTION_SECONDS = 3_600.0
MAX_TRACKED_CLIENTS = 10_000


@dataclass
class _Bucket:
    """A token bucket. Starts full, so a first-time caller is never throttled."""

    tokens: float = BURST_BUDGET
    # Resolved through the module attribute at call time, not captured at class
    # definition. `default_factory=time.monotonic` binds the function object
    # itself, so the field and `take` below can end up reading two different
    # clocks — which makes elapsed time meaningless and the bucket untestable.
    updated: float = field(default_factory=lambda: time.monotonic())

    def take(self, cost: float, refill_per_second: float, capacity: float) -> tuple[bool, float]:
        """
        Spend `cost` if the budget allows.

        Returns (allowed, retry_after_seconds). The retry hint is computed from
        the actual refill rate rather than guessed, so a client that honours it
        succeeds on its next attempt instead of backing off blindly.
        """
        now = time.monotonic()
        self.tokens = min(capacity, self.tokens + (now - self.updated) * refill_per_second)
        self.updated = now

        if self.tokens >= cost:
            self.tokens -= cost
            return True, 0.0

        shortfall = cost - self.tokens
        return False, shortfall / refill_per_second


class RateLimiter:
    """Token buckets keyed by client, with periodic eviction of idle ones."""

    def __init__(
        self,
        hourly_budget: float = HOURLY_BUDGET,
        burst: float = BURST_BUDGET,
    ) -> None:
        self._refill_per_second = hourly_budget / 3_600.0
        self._capacity = burst
        self._buckets: dict[str, _Bucket] = {}
        self._lock = threading.Lock()
        self._last_eviction = time.monotonic()

    def check(self, client: str, cost: float) -> tuple[bool, float]:
        """Spend `cost` on this client's budget. Returns (allowed, retry_after)."""
        with self._lock:
            self._maybe_evict()
            bucket = self._buckets.get(client)
            if bucket is None:
                bucket = _Bucket(tokens=self._capacity)
                self._buckets[client] = bucket
            return bucket.take(cost, self._refill_per_second, self._capacity)

    def _maybe_evict(self) -> None:
        """
        Drop buckets nobody has used in an hour.

        Called under the lock from `check`, so eviction costs a caller nothing
        on all but one request an hour. A bucket at full tokens is
        indistinguishable from a fresh one, so dropping it grants no advantage.
        """
        now = time.monotonic()
        if now - self._last_eviction < 300.0 and len(self._buckets) < MAX_TRACKED_CLIENTS:
            return

        self._last_eviction = now
        cutoff = now - IDLE_EVICTION_SECONDS
        stale = [key for key, bucket in self._buckets.items() if bucket.updated < cutoff]
        for key in stale:
            del self._buckets[key]

        if len(self._buckets) >= MAX_TRACKED_CLIENTS:
            # Pathological case: more distinct clients than we will track. Drop
            # the least recently seen rather than letting the table grow without
            # bound, which is the failure mode an attacker would aim for.
            ordered = sorted(self._buckets.items(), key=lambda kv: kv[1].updated)
            for key, _ in ordered[: len(ordered) // 2]:
                del self._buckets[key]
            logger.warning("Rate limiter table trimmed to %d clients", len(self._buckets))

    def reset(self) -> None:
        """Drop all state. For tests."""
        with self._lock:
            self._buckets.clear()


def client_key(
    forwarded_for: Optional[str],
    real_ip: Optional[str],
    peer: Optional[str],
) -> str:
    """
    Identify the caller behind Railway's proxy.

    `X-Forwarded-For` is a client-controlled header: anyone can send
    `X-Forwarded-For: 1.2.3.4` and, if we trusted the *first* entry, give
    themselves a fresh budget on every request. The proxy appends the real peer
    to the end of the chain, so the **last** entry is the only one it wrote and
    the only one worth trusting.
    """
    if forwarded_for:
        parts = [part.strip() for part in forwarded_for.split(",") if part.strip()]
        if parts:
            return parts[-1]
    if real_ip:
        return real_ip.strip()
    return peer or "unknown"


def request_cost(path: str, ticker_count: int = 1) -> float:
    """What a request to `path` costs, in units of roughly one ticker fetch."""
    if path.endswith("/analyze"):
        return COST_DEEP_ANALYSIS
    if path.endswith("/batch"):
        return max(COST_PER_TICKER, ticker_count * COST_PER_TICKER)
    return COST_DEFAULT


def is_exempt(path: str) -> bool:
    """Uptime checks and docs are free; everything under /api is not."""
    if path.startswith("/api/"):
        return False
    return path == "/" or any(path.startswith(prefix) for prefix in EXEMPT_PREFIXES)


rate_limiter = RateLimiter()
