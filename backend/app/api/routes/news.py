"""
News endpoints.

Serves the archive of scraped articles and their sentiment scores. Entirely
database-backed, so every handler checks availability first and returns an
empty, explained result when Postgres is not configured.
"""

from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from typing import Any, Optional
from urllib.parse import urlparse

from fastapi import APIRouter, HTTPException, Query
from sqlalchemy import desc, select

from app.db.models import NewsArticle, SentimentEvent
from app.db.session import database_available, get_async_session_factory

logger = logging.getLogger(__name__)

router = APIRouter()

_NO_DATABASE_REASON = (
    "The news archive requires a database. Set DATABASE_URL to enable it."
)


def calculate_impact_rating(sentiment_score: float, confidence: float) -> dict[str, Any]:
    """
    Score how much a story is likely to matter.

    Impact is the product of conviction (how far from neutral the sentiment is)
    and confidence (how sure the classifier was). A strongly-worded headline the
    model is unsure about ranks below a moderate one it is certain of.
    """
    if sentiment_score > 0.1:
        sentiment = "bullish"
    elif sentiment_score < -0.1:
        sentiment = "bearish"
    else:
        sentiment = "neutral"

    impact_score = abs(sentiment_score) * confidence * 100
    if impact_score >= 60:
        impact = "high"
    elif impact_score >= 30:
        impact = "medium"
    else:
        impact = "low"

    return {"sentiment": sentiment, "impact": impact, "score": round(impact_score, 1)}


def _source_from(article: Optional[NewsArticle], url: Optional[str]) -> str:
    """Best available publisher name, falling back to the URL's domain."""
    if article and article.source_domain:
        return article.source_domain
    if url:
        netloc = urlparse(url).netloc
        if netloc:
            return netloc.replace("www.", "")
    return "Unknown"


@router.get("/ticker/{ticker}")
async def get_news_for_ticker(
    ticker: str,
    limit: int = Query(3, ge=1, le=25),
    hours: int = Query(24, ge=1, le=720),
) -> dict[str, Any]:
    """
    Recent news for one ticker, with sentiment and an impact rating.

    `hours` bounds how far back to look; the default of 24 keeps a stock card
    showing genuinely current headlines.
    """
    symbol = ticker.upper()

    if not database_available():
        return {
            "ticker": symbol,
            "articles": [],
            "count": 0,
            "available": False,
            "reason": _NO_DATABASE_REASON,
        }

    cutoff = datetime.now(timezone.utc) - timedelta(hours=hours)

    try:
        factory = get_async_session_factory()
        async with factory() as session:
            result = await session.execute(
                select(SentimentEvent, NewsArticle)
                .join(NewsArticle, SentimentEvent.url == NewsArticle.url, isouter=True)
                .where(
                    SentimentEvent.ticker == symbol,
                    SentimentEvent.source == "news",
                    SentimentEvent.timestamp >= cutoff,
                    SentimentEvent.url.isnot(None),
                )
                .order_by(desc(SentimentEvent.timestamp))
                .limit(limit * 3)
            )
            rows = result.all()
    except Exception as exc:
        logger.error("Error fetching news for %s: %s", symbol, exc, exc_info=True)
        return {
            "ticker": symbol,
            "articles": [],
            "count": 0,
            "available": False,
            "reason": "Could not load news right now.",
        }

    articles: list[dict[str, Any]] = []
    seen: set[str] = set()

    for event, article in rows:
        if event.url in seen:
            continue
        seen.add(event.url)

        published = article.published_at if article else event.timestamp

        articles.append(
            {
                # Prefer the NewsArticle id: it is the only one the detail
                # endpoint can resolve to full content.
                "id": article.id if article else event.id,
                "url": event.url,
                "title": article.title if article else (event.text or "")[:200] or "Untitled",
                "source": _source_from(article, event.url),
                "published_at": published.isoformat() if published else None,
                "image_url": article.image_url if article else None,
                "summary": article.summary if article else None,
                "sentiment": {
                    "score": event.sentiment_score,
                    "label": event.sentiment_label,
                    "confidence": event.confidence,
                },
                "impact": calculate_impact_rating(
                    event.sentiment_score or 0.0, event.confidence or 0.5
                ),
                "has_content": bool(article and article.content),
            }
        )
        if len(articles) >= limit:
            break

    return {"ticker": symbol, "articles": articles, "count": len(articles), "available": True}


@router.get("/article/{article_id}")
async def get_article_details(article_id: int) -> dict[str, Any]:
    """Full stored content for one article."""
    if not database_available():
        raise HTTPException(status_code=503, detail=_NO_DATABASE_REASON)

    try:
        factory = get_async_session_factory()
        async with factory() as session:
            article = (
                await session.execute(select(NewsArticle).where(NewsArticle.id == article_id))
            ).scalar_one_or_none()

            if article is None:
                raise HTTPException(status_code=404, detail="Article not found.")

            event = (
                await session.execute(
                    select(SentimentEvent)
                    .where(SentimentEvent.url == article.url)
                    .order_by(desc(SentimentEvent.timestamp))
                    .limit(1)
                )
            ).scalar_one_or_none()

    except HTTPException:
        raise
    except Exception as exc:
        logger.error("Error fetching article %s: %s", article_id, exc, exc_info=True)
        raise HTTPException(status_code=500, detail="Could not load this article.") from exc

    score = event.sentiment_score if event else 0.0
    confidence = event.confidence if event else 0.5

    return {
        "id": article.id,
        "url": article.url,
        "title": article.title,
        "content": article.content,
        "summary": article.summary,
        "author": article.author,
        "source": _source_from(article, article.url),
        "published_at": article.published_at.isoformat() if article.published_at else None,
        "image_url": article.image_url,
        "sentiment": {
            "score": score,
            "label": event.sentiment_label if event else None,
            "confidence": confidence,
        },
        "impact": calculate_impact_rating(score or 0.0, confidence or 0.5),
        "has_content": bool(article.content),
    }
