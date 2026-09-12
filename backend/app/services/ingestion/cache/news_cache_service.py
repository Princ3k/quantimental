"""
News Caching Service

Manages 6-hour caching of NewsAPI articles to minimize API calls.
Articles are fetched once per 6-hour window and served from cache until expiration.
"""

import logging
from datetime import datetime, timedelta
from typing import List, Optional
from sqlalchemy import select, delete
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import CachedNewsArticle
from app.services.ingestion.sentiment.sentiment_data_fetcher import (
    fetch_market_news,
    fetch_newsapi_news
)

logger = logging.getLogger(__name__)

# 6-hour cache duration (aligned with batch orchestration)
CACHE_DURATION_HOURS = 6


def get_current_batch_timestamp() -> datetime:
    """
    Get the current 6-hour batch timestamp.
    Batches start at: 12 AM, 6 AM, 12 PM, 6 PM
    """
    now = datetime.utcnow()
    hour = now.hour

    # Determine which 6-hour window we're in
    if 0 <= hour < 6:
        batch_start_hour = 0
    elif 6 <= hour < 12:
        batch_start_hour = 6
    elif 12 <= hour < 18:
        batch_start_hour = 12
    else:  # 18-24
        batch_start_hour = 18

    return now.replace(hour=batch_start_hour, minute=0, second=0, microsecond=0)


async def get_cached_trending_articles(
    db: AsyncSession,
    limit: int = 4
) -> Optional[List[dict]]:
    """
    Get cached trending articles if they're still fresh.
    Returns None if cache is expired or empty.
    """
    current_batch = get_current_batch_timestamp()

    query = select(CachedNewsArticle).where(
        CachedNewsArticle.article_type == 'trending',
        CachedNewsArticle.batch_timestamp == current_batch,
        CachedNewsArticle.cache_expires_at > datetime.utcnow()
    ).limit(limit)

    result = await db.execute(query)
    cached_articles = result.scalars().all()

    if not cached_articles:
        logger.info(f"No cached trending articles found for batch {current_batch}")
        return None

    logger.info(f"Retrieved {len(cached_articles)} cached trending articles")

    return [
        {
            "ticker": None,
            "title": article.title,
            "description": article.description,
            "url": article.url,
            "source": article.source,
            "published_at": article.published_at.isoformat() if article.published_at else "",
            "image_url": article.image_url,
            "author": article.author,
            "is_market_news": True,
        }
        for article in cached_articles
    ]


async def get_cached_ticker_news(
    db: AsyncSession,
    ticker: str,
    limit: int = 3
) -> Optional[List[dict]]:
    """
    Get cached ticker-specific news if it's still fresh.
    Returns None if cache is expired or empty.
    """
    current_batch = get_current_batch_timestamp()

    query = select(CachedNewsArticle).where(
        CachedNewsArticle.article_type == 'ticker',
        CachedNewsArticle.ticker == ticker.upper(),
        CachedNewsArticle.batch_timestamp == current_batch,
        CachedNewsArticle.cache_expires_at > datetime.utcnow()
    ).limit(limit)

    result = await db.execute(query)
    cached_articles = result.scalars().all()

    if not cached_articles:
        logger.info(f"No cached news found for {ticker} in batch {current_batch}")
        return None

    logger.info(f"Retrieved {len(cached_articles)} cached articles for {ticker}")

    return [
        {
            "ticker": article.ticker,
            "title": article.title,
            "description": article.description,
            "url": article.url,
            "source": article.source,
            "published_at": article.published_at.isoformat() if article.published_at else "",
            "image_url": article.image_url,
            "author": article.author,
        }
        for article in cached_articles
    ]


async def cache_trending_articles(
    db: AsyncSession,
    articles: List[dict]
) -> int:
    """
    Cache trending articles for the current 6-hour window.
    Deletes old cache for this batch first.
    """
    current_batch = get_current_batch_timestamp()
    cache_expires = current_batch + timedelta(hours=CACHE_DURATION_HOURS)

    # Delete old cache for this batch
    await db.execute(
        delete(CachedNewsArticle).where(
            CachedNewsArticle.article_type == 'trending',
            CachedNewsArticle.batch_timestamp == current_batch
        )
    )

    # Insert new cache
    cached_count = 0
    for article in articles:
        try:
            published_at = None
            if article.get("published_at"):
                try:
                    published_at = datetime.fromisoformat(article["published_at"].replace('Z', '+00:00'))
                except:
                    pass

            cached_article = CachedNewsArticle(
                article_type='trending',
                ticker=None,
                url=article.get("url", ""),
                title=article.get("title", ""),
                description=article.get("description"),
                source=article.get("news_source") or article.get("source", ""),
                published_at=published_at,
                image_url=article.get("image_url"),
                author=article.get("author"),
                batch_timestamp=current_batch,
                cache_expires_at=cache_expires
            )
            db.add(cached_article)
            cached_count += 1
        except Exception as e:
            logger.warning(f"Failed to cache article {article.get('url')}: {e}")

    await db.commit()
    logger.info(f"Cached {cached_count} trending articles for batch {current_batch}")
    return cached_count


async def cache_ticker_news(
    db: AsyncSession,
    ticker: str,
    articles: List[dict]
) -> int:
    """
    Cache ticker-specific news for the current 6-hour window.
    Deletes old cache for this ticker/batch first.
    """
    current_batch = get_current_batch_timestamp()
    cache_expires = current_batch + timedelta(hours=CACHE_DURATION_HOURS)

    # Delete old cache for this ticker/batch
    await db.execute(
        delete(CachedNewsArticle).where(
            CachedNewsArticle.article_type == 'ticker',
            CachedNewsArticle.ticker == ticker.upper(),
            CachedNewsArticle.batch_timestamp == current_batch
        )
    )

    # Insert new cache
    cached_count = 0
    for article in articles:
        try:
            published_at = None
            if article.get("published_at"):
                try:
                    published_at = datetime.fromisoformat(article["published_at"].replace('Z', '+00:00'))
                except:
                    pass

            cached_article = CachedNewsArticle(
                article_type='ticker',
                ticker=ticker.upper(),
                url=article.get("url", ""),
                title=article.get("title", ""),
                description=article.get("description"),
                source=article.get("news_source") or article.get("source", ""),
                published_at=published_at,
                image_url=article.get("image_url"),
                author=article.get("author"),
                batch_timestamp=current_batch,
                cache_expires_at=cache_expires
            )
            db.add(cached_article)
            cached_count += 1
        except Exception as e:
            logger.warning(f"Failed to cache article {article.get('url')} for {ticker}: {e}")

    await db.commit()
    logger.info(f"Cached {cached_count} articles for {ticker} in batch {current_batch}")
    return cached_count


async def fetch_and_cache_trending_articles(
    db: AsyncSession,
    limit: int = 10
) -> List[dict]:
    """
    Fetch trending articles from NewsAPI and cache them.
    Returns the fetched articles.
    """
    try:
        logger.info("Fetching trending articles from NewsAPI...")
        articles = await fetch_market_news(limit=limit, skip_full_text=True)

        logger.info(f"🔍 DEBUG: fetch_market_news returned {len(articles)} articles")

        if isinstance(articles, Exception):
            logger.error(f"Failed to fetch trending articles: {articles}")
            return []

        if not articles:
            logger.warning("No articles returned from fetch_market_news")
            return []

        # Cache the articles
        await cache_trending_articles(db, articles)

        return articles
    except Exception as e:
        logger.error(f"Error fetching and caching trending articles: {e}", exc_info=True)
        return []


async def fetch_and_cache_ticker_news(
    db: AsyncSession,
    ticker: str,
    limit: int = 3
) -> List[dict]:
    """
    Fetch ticker-specific news from NewsAPI and cache it.
    Returns the fetched articles.
    """
    try:
        logger.info(f"Fetching news for {ticker} from NewsAPI...")
        articles = await fetch_newsapi_news(ticker, limit=limit, skip_full_text=True)

        if isinstance(articles, Exception):
            logger.error(f"Failed to fetch news for {ticker}: {articles}")
            return []

        # Cache the articles
        await cache_ticker_news(db, ticker, articles)

        return articles
    except Exception as e:
        logger.error(f"Error fetching and caching news for {ticker}: {e}", exc_info=True)
        return []


async def cleanup_expired_cache(db: AsyncSession) -> int:
    """
    Remove expired cache entries.
    Returns number of entries deleted.
    """
    result = await db.execute(
        delete(CachedNewsArticle).where(
            CachedNewsArticle.cache_expires_at < datetime.utcnow()
        )
    )
    await db.commit()

    deleted_count = result.rowcount
    if deleted_count > 0:
        logger.info(f"Cleaned up {deleted_count} expired cache entries")

    return deleted_count