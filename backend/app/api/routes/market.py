"""
Market context endpoints: trending news and Reddit discussion.

Everything here is supplementary — it enriches a signal but never produces one.
All of it is database- or third-party-backed, so each handler degrades to an
empty result with an explanation rather than failing the page.
"""

from __future__ import annotations

import asyncio
import logging
from typing import Any
from urllib.parse import urlparse

from fastapi import APIRouter, BackgroundTasks, Query
from sqlalchemy import desc, select

from app.db.models import NewsArticle, SentimentEvent
from app.db.session import database_available, get_async_session_factory
from app.schemas.api import AnalyzeRequest
from app.services.data.macro_signal_service import macro_signal_service
from app.services.data.market_data_service import market_data_service
from app.services.data.narrative_service import narrative_service
from app.services.data import published_service, snapshot_service

logger = logging.getLogger(__name__)

router = APIRouter()

_NO_DATABASE = {
    "available": False,
    "reason": "The news archive requires a database. Set DATABASE_URL to enable it.",
}


def _classify(sentiment_score: float, confidence: float) -> tuple[str, str]:
    """Turn a raw sentiment score into (direction, impact) labels."""
    if sentiment_score > 0.1:
        direction = "bullish"
    elif sentiment_score < -0.1:
        direction = "bearish"
    else:
        direction = "neutral"

    impact_score = abs(sentiment_score) * confidence * 100
    if impact_score >= 60:
        impact = "high"
    elif impact_score >= 30:
        impact = "medium"
    else:
        impact = "low"
    return direction, impact


@router.get("/history/{ticker}")
async def price_history(
    ticker: str,
    range_: str = Query("1y", alias="range", pattern="^(1m|3m|6m|1y)$"),
) -> dict[str, Any]:
    """
    Dated closing prices for one stock.

    Separate from the signal payload on purpose. A year of dated points is
    around 5KB, which is nothing for one stock and 300KB for a sixty-ticker
    dashboard batch — so the cards keep their thirty undated closes and only a
    chart somebody is actually looking at pays for the rest.

    Ranges are served by slicing one cached year rather than re-fetching, so
    switching between them costs no upstream request.
    """
    symbol = ticker.upper().strip()

    try:
        frame = await asyncio.to_thread(market_data_service.get_historical_data, symbol)
    except Exception as exc:  # noqa: BLE001
        logger.warning("History fetch failed for %s: %s", symbol, exc)
        return {"ticker": symbol, "available": False, "reason": "Price history is unavailable."}

    if frame is None or frame.empty or "Close" not in frame:
        return {
            "ticker": symbol,
            "available": False,
            "reason": f"No price history for {symbol}.",
        }

    frame = frame.dropna(subset=["Close"])

    # Trading days, not calendar days: a month is ~21 sessions.
    sessions = {"1m": 21, "3m": 63, "6m": 126, "1y": len(frame)}[range_]
    window = frame.tail(sessions)

    return {
        "ticker": symbol,
        "available": True,
        "range": range_,
        "points": [
            {"d": index.strftime("%Y-%m-%d"), "c": round(float(close), 2)}
            for index, close in zip(window.index, window["Close"])
        ],
    }


@router.get("/trending-articles")
async def get_trending_articles(limit: int = Query(10, ge=1, le=50)) -> dict[str, Any]:
    """
    Recent financial news with sentiment, newest first.

    Deduplicated by URL, because the same story routinely arrives from several
    tickers' feeds at once.
    """
    if not database_available():
        return {"articles": [], "total": 0, **_NO_DATABASE}

    try:
        factory = get_async_session_factory()
        async with factory() as session:
            result = await session.execute(
                select(SentimentEvent, NewsArticle)
                .join(NewsArticle, SentimentEvent.url == NewsArticle.url, isouter=True)
                .where(SentimentEvent.source == "news", SentimentEvent.url.isnot(None))
                .order_by(desc(SentimentEvent.timestamp))
                # Over-fetch so dedupe still leaves a full page.
                .limit(limit * 3)
            )
            rows = result.all()

        articles: list[dict[str, Any]] = []
        seen: set[str] = set()

        for event, article in rows:
            if event.url in seen:
                continue
            seen.add(event.url)

            source = "Unknown"
            if article and article.source_domain:
                source = article.source_domain
            elif event.url:
                netloc = urlparse(event.url).netloc
                source = netloc.replace("www.", "") if netloc else "Unknown"

            direction, impact = _classify(event.sentiment_score or 0.0, event.confidence or 0.5)
            published = article.published_at if article else event.timestamp

            articles.append(
                {
                    "id": article.id if article else event.id,
                    "title": article.title if article else (event.text or "")[:200] or "Untitled",
                    "source": source,
                    "url": event.url,
                    "published_at": published.isoformat() if published else None,
                    "sentiment": direction,
                    "impact": impact,
                    "tickers": [event.ticker] if event.ticker else [],
                    "summary": article.summary if article else None,
                    "image_url": article.image_url if article else None,
                }
            )
            if len(articles) >= limit:
                break

        return {"articles": articles, "total": len(articles), "available": True}

    except Exception as exc:
        logger.error("Error fetching trending articles: %s", exc, exc_info=True)
        return {
            "articles": [],
            "total": 0,
            "available": False,
            "reason": "Could not load news right now.",
        }


@router.get("/reddit/{ticker}")
async def get_reddit_posts(
    ticker: str,
    limit: int = Query(10, ge=1, le=50),
    timeframe: str = Query("week", pattern="^(hour|day|week|month|year|all)$"),
) -> dict[str, Any]:
    """
    Reddit discussion about a ticker, served from a 6-hour cache.

    The cache exists to stay inside Reddit's rate limits; `is_cached` tells the
    caller whether this response came from it.
    """
    symbol = ticker.upper()

    if not database_available():
        return {
            "ticker": symbol,
            "posts": [],
            "total": 0,
            "is_cached": False,
            "available": False,
            "reason": "Reddit discussion requires a database for caching. Set DATABASE_URL to enable it.",
        }

    try:
        from app.services.ingestion.cache.reddit_cache_service import get_reddit_posts_with_cache

        factory = get_async_session_factory()
        async with factory() as session:
            posts, is_cached = await get_reddit_posts_with_cache(
                db=session, ticker=symbol, limit=limit, timeframe=timeframe
            )

        return {
            "ticker": symbol,
            "posts": posts,
            "total": len(posts),
            "is_cached": is_cached,
            "available": True,
        }

    except Exception as exc:
        logger.error("Error fetching Reddit posts for %s: %s", symbol, exc, exc_info=True)
        return {
            "ticker": symbol,
            "posts": [],
            "total": 0,
            "is_cached": False,
            "available": False,
            "reason": "Could not load Reddit discussion right now.",
        }


@router.post("/ingest/{ticker}")
async def trigger_ingestion(ticker: str, background_tasks: BackgroundTasks) -> dict[str, Any]:
    """
    Kick off sentiment ingestion for a ticker in the background.

    Returns immediately; the Kafka pipeline does the work. Requires Kafka and
    the sentiment workers to be running.
    """
    symbol = AnalyzeRequest(ticker=ticker).ticker

    async def _run() -> None:
        try:
            from app.services.ingestion.sentiment.producer import SentimentIngestionService

            await SentimentIngestionService().run([symbol])
        except Exception as exc:
            logger.error("Background ingestion failed for %s: %s", symbol, exc, exc_info=True)

    background_tasks.add_task(_run)
    return {"ticker": symbol, "status": "started", "message": f"Sentiment ingestion started for {symbol}."}


@router.get("/signal-desk")
async def get_signal_desk() -> dict[str, Any]:
    """
    The market-wide Signal Desk: what moved, how unusual it was, and what it
    adds up to in plain English.

    Unlike the per-stock endpoints this needs no ticker — it reads a fixed
    basket of rates, credit, currency, commodity, volatility and sector
    instruments and reports the state of the market as a whole.

    Everything here describes what has *already* happened. Nothing forecasts.
    """
    # Both calls are blocking (network, then optionally an LLM), so keep them
    # off the event loop.
    desk = await asyncio.to_thread(macro_signal_service.get_desk)

    if not desk.get("available"):
        return desk

    desk["narrative"] = await asyncio.to_thread(narrative_service.generate, desk)
    return desk


# The disclosure that rides on /explain, repeated here for the same reason: a
# consumer embedding these somewhere needs it to travel with the text.
PUBLISHED_DISCLOSURE = "Descriptive only. Not investment advice, and not a forecast."


@router.get("/unusual")
async def get_unusual(limit: int = Query(10, ge=1, le=50)) -> dict[str, Any]:
    """
    Today's unusual moves: stocks that moved far relative to their own normal.

    "Unusual" is measured, not asserted. A move qualifies by exceeding a
    multiple of that stock's own typical daily range, so a 3% day counts for a
    utility and does not for a small-cap biotech. The threshold used is
    returned alongside, because a reader cannot judge the list without it.

    Served from the file the scan publishes, so the wording here is the wording
    everywhere else. `biggest` is carried separately and is explicitly *not* a
    list of unusual moves — on a quiet day `movers` is empty and that is the
    honest answer, not a prompt to promote the largest ordinary move.
    """
    feed = await asyncio.to_thread(published_service.get, "unusual.json")
    if not feed or not feed.get("available"):
        return {"available": False, "reason": "No published scan is available."}

    return {
        "available": True,
        "as_of": feed.get("as_of"),
        "generated_at": feed.get("generated_at"),
        "scanned": feed.get("scanned"),
        "threshold": feed.get("threshold"),
        "count": feed.get("unusual_count", 0),
        "rising": feed.get("rising"),
        "falling": feed.get("falling"),
        "movers": (feed.get("movers") or [])[:limit],
        "biggest": (feed.get("biggest") or [])[:limit],
        "disclosure": PUBLISHED_DISCLOSURE,
    }


@router.get("/desk")
async def get_published_desk() -> dict[str, Any]:
    """
    The Signal Desk as the scan last published it.

    Distinct from `/signal-desk` above, which recomputes: that one reads a
    basket of macro instruments from Yahoo and then calls an LLM, which is the
    right shape for a page a person loads and the wrong shape for anything that
    might be called in a loop. This reads the published file and costs nothing.
    """
    desk = await asyncio.to_thread(published_service.get, "signal-desk.json")
    if not desk or not desk.get("available"):
        return {"available": False, "reason": "No published desk is available."}
    desk = dict(desk)
    desk["disclosure"] = PUBLISHED_DISCLOSURE
    return desk


@router.get("/filings")
async def get_filings(limit: int = Query(25, ge=1, le=100)) -> dict[str, Any]:
    """
    The 8-Ks companies filed for this session.

    A fact about a document, not an explanation of a move. The filing and the
    price happened on the same day; both are reported and the reader is left to
    judge, which is why every row carries the same note the per-stock endpoint
    does and why nothing here is sorted by how far the stock moved — ordering
    filings by price action is a causal claim made with a sort key.

    Ordered by the item code instead, most notable first, which is the scan's
    own judgement of which disclosures matter and is about the document alone.
    """
    snapshot = await asyncio.to_thread(snapshot_service.get_snapshot)
    if not snapshot:
        return {"available": False, "reason": "No published scan is available."}

    filed = [row for row in snapshot.rows.values() if row.get("f")]
    filed.sort(key=lambda r: (r["f"].get("i") or ["99"])[0])

    return {
        "available": True,
        "as_of": snapshot.as_of,
        "generated_at": snapshot.generated_at,
        "count": len(filed),
        "filings": [
            {
                "ticker": row["t"],
                "company": row.get("n"),
                "sector": row.get("s"),
                "items": row["f"].get("i") or [],
                "reported": row["f"].get("p"),
                "accepted_at": row["f"].get("a"),
                "url": row["f"].get("u"),
                "note": "Filed on the same session. Same-day is adjacency, not cause.",
            }
            for row in filed[:limit]
        ],
        "disclosure": PUBLISHED_DISCLOSURE,
    }
