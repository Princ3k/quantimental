"""
Reddit Post Caching Service

Implements 6-hour caching for Reddit posts to minimize API calls.
Cache windows align with batch orchestration: 12 AM, 6 AM, 12 PM, 6 PM UTC.
"""

import logging
from datetime import datetime, timedelta
from typing import List, Dict, Optional
from sqlalchemy import select, delete
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import CachedRedditPost
from app.services.ingestion.sentiment.reddit_post_fetcher import (
    fetch_reddit_posts_for_ticker,
    get_post_sentiment_score,
)

logger = logging.getLogger(__name__)


def get_current_batch_timestamp() -> datetime:
    """
    Get the current 6-hour batch timestamp.
    Returns the start time of the current 6-hour window (12 AM, 6 AM, 12 PM, 6 PM UTC).
    """
    now = datetime.utcnow()
    hour = now.hour

    if 0 <= hour < 6:
        batch_start_hour = 0
    elif 6 <= hour < 12:
        batch_start_hour = 6
    elif 12 <= hour < 18:
        batch_start_hour = 12
    else:
        batch_start_hour = 18

    return now.replace(hour=batch_start_hour, minute=0, second=0, microsecond=0)


async def get_cached_reddit_posts(
    db: AsyncSession,
    ticker: str,
    limit: int = 10
) -> Optional[List[Dict]]:
    """
    Get cached Reddit posts for a ticker if they're still fresh.

    Args:
        db: Database session
        ticker: Stock ticker
        limit: Max posts to return

    Returns:
        List of post dictionaries if cache is fresh, None if expired
    """
    current_batch = get_current_batch_timestamp()
    ticker_upper = ticker.upper()

    try:
        # Query cached posts for this ticker and batch
        query = select(CachedRedditPost).where(
            CachedRedditPost.ticker == ticker_upper,
            CachedRedditPost.batch_timestamp == current_batch,
            CachedRedditPost.cache_expires_at > datetime.utcnow()
        ).order_by(
            CachedRedditPost.score.desc()  # Order by upvotes
        ).limit(limit)

        result = await db.execute(query)
        cached_posts = result.scalars().all()

        if not cached_posts:
            logger.info(f"Cache miss for {ticker} Reddit posts")
            return None

        # Format for API response
        formatted_posts = []
        for post in cached_posts:
            formatted_posts.append({
                "ticker": post.ticker,
                "title": post.title,
                "url": post.url,
                "selftext": post.selftext,
                "score": post.score,
                "num_comments": post.num_comments,
                "author": post.author,
                "subreddit": post.subreddit,
                "created_utc": post.created_utc,
                "permalink": post.permalink,
                "sentiment_score": post.sentiment_score,
                "source": "reddit",
            })

        logger.info(f"✅ Serving {len(formatted_posts)} Reddit posts for {ticker} from cache")
        return formatted_posts

    except Exception as e:
        logger.error(f"Error retrieving cached Reddit posts for {ticker}: {e}")
        return None


async def cache_reddit_posts(
    db: AsyncSession,
    ticker: str,
    posts: List[Dict]
) -> None:
    """
    Cache Reddit posts for a ticker in the current 6-hour batch.

    Args:
        db: Database session
        ticker: Stock ticker
        posts: List of post dictionaries from reddit_post_fetcher
    """
    if not posts:
        logger.warning(f"No posts to cache for {ticker}")
        return

    current_batch = get_current_batch_timestamp()
    cache_expires = current_batch + timedelta(hours=6)
    ticker_upper = ticker.upper()

    try:
        # Delete existing cached posts for this ticker in this batch
        await db.execute(
            delete(CachedRedditPost).where(
                CachedRedditPost.ticker == ticker_upper,
                CachedRedditPost.batch_timestamp == current_batch
            )
        )

        # Insert new cached posts
        for post in posts:
            cached_post = CachedRedditPost(
                ticker=ticker_upper,
                title=post.get("title", ""),
                url=post.get("url", ""),
                selftext=post.get("selftext", ""),
                score=post.get("score", 0),
                num_comments=post.get("num_comments", 0),
                author=post.get("author", ""),
                subreddit=post.get("subreddit", ""),
                created_utc=int(post.get("created_utc", 0)),
                permalink=post.get("permalink", ""),
                sentiment_score=post.get("sentiment_score", 0.0),
                batch_timestamp=current_batch,
                cache_expires_at=cache_expires,
            )
            db.add(cached_post)

        await db.commit()
        logger.info(f"✅ Cached {len(posts)} Reddit posts for {ticker} (batch: {current_batch})")

    except Exception as e:
        await db.rollback()
        logger.error(f"Error caching Reddit posts for {ticker}: {e}", exc_info=True)
        raise


async def fetch_and_cache_reddit_posts(
    db: AsyncSession,
    ticker: str,
    limit: int = 10,
    timeframe: str = "week"
) -> List[Dict]:
    """
    Fetch Reddit posts from API and cache them for 6 hours.

    Args:
        db: Database session
        ticker: Stock ticker
        limit: Number of posts to fetch
        timeframe: Time filter (hour, day, week, month, year, all)

    Returns:
        List of post dictionaries
    """
    try:
        # Fetch from Reddit API
        posts = await fetch_reddit_posts_for_ticker(
            ticker=ticker,
            limit=limit,
            timeframe=timeframe
        )

        if not posts:
            logger.warning(f"No Reddit posts found for {ticker}")
            return []

        # Calculate sentiment scores for each post
        for post in posts:
            sentiment_score = await get_post_sentiment_score(post)
            post["sentiment_score"] = sentiment_score

        # Cache the posts
        await cache_reddit_posts(db, ticker, posts)

        logger.info(f"✅ Fetched and cached {len(posts)} Reddit posts for {ticker}")
        return posts

    except Exception as e:
        logger.error(f"Error fetching/caching Reddit posts for {ticker}: {e}", exc_info=True)
        return []


async def cleanup_expired_reddit_cache(db: AsyncSession) -> int:
    """
    Delete expired Reddit posts from cache.

    Returns:
        Number of deleted posts
    """
    try:
        result = await db.execute(
            delete(CachedRedditPost).where(
                CachedRedditPost.cache_expires_at < datetime.utcnow()
            )
        )
        await db.commit()
        deleted_count = result.rowcount

        if deleted_count > 0:
            logger.info(f"🗑️  Cleaned up {deleted_count} expired Reddit posts from cache")

        return deleted_count

    except Exception as e:
        await db.rollback()
        logger.error(f"Error cleaning up expired Reddit cache: {e}")
        return 0


async def get_reddit_posts_with_cache(
    db: AsyncSession,
    ticker: str,
    limit: int = 10,
    timeframe: str = "week"
) -> tuple[List[Dict], bool]:
    """
    Get Reddit posts for a ticker, using cache if available.

    Args:
        db: Database session
        ticker: Stock ticker
        limit: Number of posts to return
        timeframe: Time filter for fresh fetches

    Returns:
        Tuple of (posts, is_cached)
    """
    # Try cache first
    cached_posts = await get_cached_reddit_posts(db, ticker, limit)

    if cached_posts:
        return cached_posts, True

    # Cache miss - fetch and cache
    fresh_posts = await fetch_and_cache_reddit_posts(db, ticker, limit, timeframe)
    return fresh_posts, False