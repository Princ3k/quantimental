"""
Market context endpoints: trending news and Reddit discussion.

Everything here is supplementary — it enriches a signal but never produces one.
All of it is database- or third-party-backed, so each handler degrades to an
empty result with an explanation rather than failing the page.
"""

from __future__ import annotations

import logging
from typing import Any
from urllib.parse import urlparse

from fastapi import APIRouter, BackgroundTasks, Query
from sqlalchemy import desc, select

from app.db.models import NewsArticle, SentimentEvent
from app.db.session import database_available, get_async_session_factory
from app.schemas.api import AnalyzeRequest

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
