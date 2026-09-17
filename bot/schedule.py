"""
When the daily post goes out.

Not on a clock. The sentences the bot posts are not computed when it asks for
them — they are baked into the published snapshot by the scan that runs in CI,
and the API serves a cached copy of that. A bot posting at a fixed time would
therefore sometimes repeat the previous session's wording, with no way to tell
from its own side that it had.

So the rule is by session, not by hour: post once per guild per `as_of`, the
first time a scan for a session that has closed becomes visible. A missed slot
self-heals — the next poll sees the same unposted session and sends it — and a
scan that publishes twice for one session cannot produce two posts.
"""

from __future__ import annotations

from datetime import datetime, time, timezone
from typing import Optional
from zoneinfo import ZoneInfo

MARKET = ZoneInfo("America/New_York")

# US equities close at 16:00 ET. The post-close scan runs at 21:43 UTC, and
# the figures it publishes are the ones worth posting, so nothing is sent for a
# session until the market that session describes has actually closed.
CLOSE = time(16, 0)

# How long after the close to keep waiting for a scan before giving up on the
# session entirely. Past this the data is tomorrow's problem, and posting a
# day-old digest as if it were today's is worse than posting nothing.
ABANDON_AFTER_HOURS = 20.0


def session_has_closed(as_of: str, *, now: Optional[datetime] = None) -> bool:
    """Whether the trading session `as_of` describes is over."""
    try:
        day = datetime.strptime(as_of[:10], "%Y-%m-%d").date()
    except (ValueError, TypeError):
        return False
    closed_at = datetime.combine(day, CLOSE, tzinfo=MARKET)
    return (now or datetime.now(timezone.utc)) >= closed_at


def hours_since_close(as_of: str, *, now: Optional[datetime] = None) -> Optional[float]:
    try:
        day = datetime.strptime(as_of[:10], "%Y-%m-%d").date()
    except (ValueError, TypeError):
        return None
    closed_at = datetime.combine(day, CLOSE, tzinfo=MARKET)
    return ((now or datetime.now(timezone.utc)) - closed_at).total_seconds() / 3600.0


def should_post(
    as_of: Optional[str],
    last_posted: Optional[str],
    *,
    now: Optional[datetime] = None,
) -> bool:
    """Whether this guild should receive a digest for `as_of` right now."""
    if not as_of:
        return False
    if last_posted == as_of:
        return False          # already sent for this session
    if not session_has_closed(as_of, now=now):
        return False          # the session is still trading
    elapsed = hours_since_close(as_of, now=now)
    if elapsed is None or elapsed > ABANDON_AFTER_HOURS:
        return False          # too late to be today's news
    return True
