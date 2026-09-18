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

# When the scans run: weekdays, hourly from 14:13 UTC, plus the post-close
# sweep at 21:43. Outside this, no scan is due — so data from the last session
# is the current answer however many hours ago it was published, and warning
# about its age would mean warning every night and all weekend.
SCAN_WINDOW_OPENS = time(14, 0)
SCAN_WINDOW_CLOSES = time(22, 0)


def scan_expected(now: Optional[datetime] = None) -> bool:
    """Whether a scan should have run recently."""
    moment = (now or datetime.now(timezone.utc)).astimezone(timezone.utc)
    if moment.weekday() >= 5:        # Saturday, Sunday
        return False
    return SCAN_WINDOW_OPENS <= moment.time() < SCAN_WINDOW_CLOSES


def _closed_at(as_of: str) -> Optional[datetime]:
    """The moment the session `as_of` names stopped trading."""
    try:
        day = datetime.strptime(as_of[:10], "%Y-%m-%d").date()
    except (ValueError, TypeError):
        return None
    return datetime.combine(day, CLOSE, tzinfo=MARKET)


def session_has_closed(as_of: str, *, now: Optional[datetime] = None) -> bool:
    """Whether the trading session `as_of` describes is over."""
    closed_at = _closed_at(as_of)
    if closed_at is None:
        return False
    return (now or datetime.now(timezone.utc)) >= closed_at


def scan_ran_after_close(as_of: str, generated_at: Optional[str]) -> bool:
    """Whether the scan behind these figures ran after the session closed.

    The session being over is not enough. The hourly scans run at :13 past,
    from 14:13 to 21:13 UTC, and the market closes at 20:00 UTC — so at the
    moment the session ends, the most recent published scan is 19:13's, and
    its prices are intraday. Posting those under the session's date would put
    a number in someone's channel that is not the close and does not match any
    chart they can check it against.

    Requiring the scan itself to postdate the close means the earliest digest
    uses 20:13's run, which is final.
    """
    closed_at = _closed_at(as_of)
    if closed_at is None or not generated_at:
        return False
    try:
        when = datetime.fromisoformat(generated_at)
    except ValueError:
        return False
    if when.tzinfo is None:
        when = when.replace(tzinfo=timezone.utc)
    return when >= closed_at


def hours_since_close(as_of: str, *, now: Optional[datetime] = None) -> Optional[float]:
    closed_at = _closed_at(as_of)
    if closed_at is None:
        return None
    return ((now or datetime.now(timezone.utc)) - closed_at).total_seconds() / 3600.0


def should_post(
    as_of: Optional[str],
    generated_at: Optional[str],
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
    if not scan_ran_after_close(as_of, generated_at):
        return False          # the figures are intraday, not the close
    elapsed = hours_since_close(as_of, now=now)
    if elapsed is None or elapsed > ABANDON_AFTER_HOURS:
        return False          # too late to be today's news
    return True
