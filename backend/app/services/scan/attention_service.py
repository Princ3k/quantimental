"""
Attention measurement — how much is being written about each stock.

The premise, and why this is worth storing
------------------------------------------

Price history is free and reconstructable: anyone can backfill what a stock's
typical range was last March. News history is not. MarketAux does not sell a
deep cheap archive, Reddit's historical API is gone, and Yahoo serves only the
most recent handful. So a record of *how much coverage each stock was getting,
each day* cannot be bought or backfilled — it can only be accumulated, starting
now. That is the one input here that time makes scarce.

What it unlocks is the same trick the price scan already does, applied to
coverage: **this stock is getting four times its normal attention**. That is a
signal nobody else can compute without having kept the same diary.

Measuring within a 10-article cap
---------------------------------

Yahoo returns ten articles per ticker regardless of how much exists, so a raw
count carries no information — every ticker scores ten. The *span* of those ten
carries a great deal. Measured across the S&P 500:

    NVDA   10 articles spanning   1.7 hours
    TSLA   10 articles spanning  20.5 hours
    KO     10 articles spanning  48.3 hours
    AOS    10 articles spanning 998.1 hours

A 600x range. So attention is expressed as **articles per day** — the count
divided by the window it covers — which is well defined under the cap and
comparable across stocks.
"""

from __future__ import annotations

import logging
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import date, datetime, timezone
from typing import Any, Optional

logger = logging.getLogger(__name__)

# Yahoo's page size. Stated as a constant because every derived figure here
# depends on knowing the count is capped rather than complete.
ARTICLES_RETURNED = 10

# Pacing, learned the hard way. Eight workers with no spacing pushed ~30
# requests a second and Yahoo cut us off with YFRateLimitError after about 315
# of 503 tickers — leaving a third of the universe with no reading at all.
#
# This runs on a cron with a six-hour ceiling, so there is no reason to hurry.
# Three workers spaced a third of a second apart is roughly three requests a
# second and completes the universe in about three minutes.
MAX_WORKERS = 3
REQUEST_SPACING_SECONDS = 0.34

# Yahoo's limiter clears on its own, so a refused request is worth retrying —
# but only with real backoff, since retrying into a limiter that just said no
# is what turns a slow minute into a blocked hour.
MAX_RETRIES = 3
BACKOFF_BASE_SECONDS = 5.0

# A span shorter than this is treated as this long. Ten articles inside a few
# minutes is a wire-service burst republishing one story, and dividing by a
# near-zero window turns that into an implausible velocity.
MIN_SPAN_HOURS = 1.0

# Beyond this, coverage is so sparse that the exact figure is noise. Caps the
# denominator so a stock with two articles a year does not dominate the low end.
MAX_SPAN_HOURS = 24.0 * 60


def _parse_time(value: str) -> Optional[datetime]:
    if not value:
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None


class _Pacer:
    """Spaces requests across every worker thread, not per thread."""

    def __init__(self, interval: float) -> None:
        self._interval = interval
        self._last = 0.0
        self._lock = threading.Lock()

    def wait(self) -> None:
        # The lock is held across the sleep on purpose: releasing it first
        # would let every waiting thread decide simultaneously that enough
        # time had passed, which is the burst this exists to prevent.
        with self._lock:
            delay = self._interval - (time.monotonic() - self._last)
            if delay > 0:
                time.sleep(delay)
            self._last = time.monotonic()


def _rotate(tickers: list[str], on: Optional[str] = None) -> list[str]:
    """
    Start each day's sweep at a different point in the universe.

    If a sweep is cut short, whatever is measured is whatever came first. A
    fixed order means the same alphabetical tail is dropped every time and
    those tickers never accumulate any history at all — the archive would be
    complete for A-through-M and empty for the rest. Rotating by day spreads
    any shortfall evenly. Deterministic so a rerun measures the same order.
    """
    if not tickers:
        return tickers
    day = date.fromisoformat(on).toordinal() if on else date.today().toordinal()
    offset = day % len(tickers)
    return tickers[offset:] + tickers[:offset]


def measure_one(ticker: str, pacer: Optional[_Pacer] = None) -> Optional[dict[str, Any]]:
    """
    Measure one ticker's news velocity.

    Returns None when there is too little to measure — fewer than two dated
    articles gives no span, and inventing one would put a fabricated number
    into a historical record whose whole value is that it is real.
    """
    import yfinance as yf

    articles = None
    for attempt in range(MAX_RETRIES):
        if pacer:
            pacer.wait()
        try:
            articles = yf.Ticker(ticker).news or []
            break
        except Exception as exc:  # noqa: BLE001
            if "rate limit" not in str(exc).lower() or attempt == MAX_RETRIES - 1:
                logger.debug("News fetch failed for %s: %s", ticker, exc)
                return None
            time.sleep(BACKOFF_BASE_SECONDS * (2**attempt))

    if articles is None:
        return None

    times: list[datetime] = []
    for article in articles:
        content = article.get("content", article)
        parsed = _parse_time(content.get("pubDate") or content.get("displayTime") or "")
        if parsed:
            times.append(parsed)

    if len(times) < 2:
        return None

    times.sort(reverse=True)
    now = datetime.now(timezone.utc)

    span_hours = (times[0] - times[-1]).total_seconds() / 3600.0
    span_hours = max(MIN_SPAN_HOURS, min(MAX_SPAN_HOURS, span_hours))

    return {
        "velocity": round(len(times) / (span_hours / 24.0), 2),
        "articles": len(times),
        "span_hours": round(span_hours, 1),
        # A plain count anyone can sanity-check against the stock's news tab.
        "last_24h": sum(1 for t in times if (now - t).total_seconds() < 86_400),
        "newest": times[0].isoformat(),
    }


def measure_attention(
    tickers: list[str],
    on: Optional[str] = None,
) -> dict[str, dict[str, Any]]:
    """
    Measure every ticker, paced to stay under Yahoo's limiter.

    Failures are omitted rather than zeroed: a ticker we could not reach and a
    ticker nobody is writing about are different facts, and recording the first
    as the second would corrupt the median this archive exists to compute.
    """
    ordered = _rotate(tickers, on)
    logger.info("Measuring attention for %d tickers", len(ordered))

    pacer = _Pacer(REQUEST_SPACING_SECONDS)
    started = time.monotonic()

    with ThreadPoolExecutor(max_workers=MAX_WORKERS) as pool:
        results = list(pool.map(lambda t: measure_one(t, pacer), ordered))

    measured = {
        ticker: result
        for ticker, result in zip(ordered, results)
        if result is not None
    }

    logger.info(
        "Measured %d of %d tickers in %.0fs",
        len(measured), len(ordered), time.monotonic() - started,
    )
    if len(measured) < len(ordered) * 0.8:
        logger.warning(
            "Only %.0f%% of the universe was measured — likely rate limited. "
            "Tomorrow's sweep starts elsewhere in the list, so the shortfall "
            "does not fall on the same tickers twice.",
            len(measured) / len(ordered) * 100,
        )
    return measured
