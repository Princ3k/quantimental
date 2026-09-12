"""
Sentiment Data Fetcher

Fetches sentiment-related data from multiple social media and financial data sources.

Supported sources:
- Reddit (r/stocks, r/investing, r/wallstreetbets)
- MarketAux (financial news with sentiment analysis)
- Twitter/X (via ScrapeBadger)

Design philosophy:
- Async everything (non-blocking I/O)
- Framework-agnostic (no FastAPI dependencies)
- Light normalization only (no analysis)
- Graceful error handling (log and return empty/None)
- No credentials required for Reddit (uses public JSON API)
"""

import asyncio
import logging
import os
from datetime import datetime
from typing import Any, Optional, Callable, Awaitable

import httpx
import trafilatura
from dotenv import load_dotenv

logger = logging.getLogger(__name__)

# Load environment variables
load_dotenv()

# Reddit public JSON API (no credentials needed)
REDDIT_BASE_URL = "https://www.reddit.com"
REDDIT_USER_AGENT = "python:quantimental-sentiment:v1.0.0"
REDDIT_TARGET_SUBREDDITS = ["stocks", "investing", "wallstreetbets"]

# MarketAux API configuration
MARKETAUX_API_KEY = os.getenv("MARKETAUX_API_KEY", "")
MARKETAUX_BASE_URL = "https://api.marketaux.com/v1/news/all"

# Twitter API configuration (ScrapeBadger)
TWITTER_API_KEY = os.getenv("TWITTER_API_KEY", "")
TWITTER_BASE_URL = "https://scrapebadger.com/api/v1/twitter/tweets/advanced_search"

# HTTP configuration
DEFAULT_TIMEOUT = 30.0
MAX_RETRIES = 2

# Content Fetching configuration
MAX_ARTICLE_LENGTH = 5000  # Truncate articles longer than this

async def fetch_reddit_posts_for_ticker(ticker: str, limit: int = 25) -> list[dict]:
    """
    Fetch recent Reddit posts related to a stock ticker using the public JSON API.

    No credentials required — uses Reddit's unauthenticated .json endpoint.
    Searches r/stocks, r/investing, and r/wallstreetbets.

    Args:
        ticker: Stock symbol (e.g., "AAPL", "TSLA")
        limit: Maximum posts per subreddit (default: 25, max: 100)

    Returns:
        List of normalized post dicts with source, subreddit, post_id,
        created_utc, author, title, text, url, score.
    """
    ticker = ticker.upper().strip()
    logger.info(f"Fetching Reddit posts for ticker: {ticker}")

    headers = {"User-Agent": REDDIT_USER_AGENT}
    all_posts = []

    async with httpx.AsyncClient(timeout=DEFAULT_TIMEOUT) as client:
        for subreddit in REDDIT_TARGET_SUBREDDITS:
            try:
                url = f"{REDDIT_BASE_URL}/r/{subreddit}/search.json"
                params = {
                    "q": ticker,
                    "restrict_sr": "1",
                    "sort": "new",
                    "t": "week",
                    "limit": limit,
                }
                response = await client.get(url, params=params, headers=headers)
                response.raise_for_status()
                data = response.json()

                posts = data.get("data", {}).get("children", [])
                for post_wrapper in posts:
                    post = post_wrapper.get("data", {})
                    all_posts.append({
                        "source": "reddit",
                        "subreddit": subreddit,
                        "post_id": post.get("id", ""),
                        "created_utc": post.get("created_utc", 0),
                        "author": post.get("author", "[deleted]"),
                        "title": post.get("title", ""),
                        "text": post.get("selftext", ""),
                        "url": f"https://reddit.com{post.get('permalink', '')}",
                        "score": post.get("score", 0),
                    })

                logger.debug(f"r/{subreddit}: {len(posts)} posts for {ticker}")

            except httpx.HTTPStatusError as e:
                logger.warning(f"Reddit r/{subreddit} HTTP {e.response.status_code}")
                continue
            except httpx.TimeoutException:
                logger.warning(f"Reddit r/{subreddit} timed out")
                continue
            except Exception as e:
                logger.error(f"Reddit r/{subreddit} error: {e}")
                continue

    logger.info(f"Fetched {len(all_posts)} total Reddit posts for {ticker}")
    return all_posts


async def fetch_article_content(url: str, timeout: float = 3.0) -> str:
    """
    Fetch and extract full article text from a URL.
    
    Uses trafilatura for robust extraction of main content, removing
    ads, navigation, and boilerplate.
    
    Features:
    - Truncates text to MAX_ARTICLE_LENGTH for LLM efficiency
    - Respects robots.txt (handled by trafilatura mainly, but we add delays in caller)
    - Robust error handling with timeout
    
    Args:
        url: Article URL
        timeout: Maximum seconds to wait for download (default: 10.0)
        
    Returns:
        Extracted full text or empty string if extraction fails
    """
    if not url:
        return ""
        
    try:
        # Run blocking trafilatura in a thread pool WITH TIMEOUT
        loop = asyncio.get_event_loop()
        
        # Download with timeout protection
        # Use httpx directly with strict timeout instead of trafilatura's fetch
        import httpx
        async with httpx.AsyncClient(timeout=timeout) as client:
            response = await client.get(url, follow_redirects=True)
            downloaded = response.text
        
        if not downloaded:
            return ""
            
        # Extract with timeout protection (still use executor for CPU-bound extraction)
        text = await asyncio.wait_for(
            loop.run_in_executor(
                None, 
                lambda: trafilatura.extract(
                    downloaded,
                    include_comments=False,
                    include_tables=False,
                    no_fallback=True
                )
            ),
            timeout=3.0  # Extraction should be fast
        )
        
        if not text:
            return ""
            
        # Truncate text for LLM (Requirement 4)
        if len(text) > MAX_ARTICLE_LENGTH:
            text = text[:MAX_ARTICLE_LENGTH] + "... [TRUNCATED]"
            
        return text
        
    except asyncio.TimeoutError:
        # Timeout is expected for slow sites
        logger.warning(f"Timeout fetching content from {url} (>{timeout}s)")
        return ""
    except Exception as e:
        # Log but don't fail (Requirement 2)
        logger.warning(f"Failed to extract content from {url}: {e}")
        return ""


async def fetch_marketaux_news(
    ticker: str, 
    limit: int = 10, 
    url_filter_func: Optional[Callable[[str], Awaitable[bool]]] = None,
    skip_full_text: bool = False
) -> list[dict]:
    """
    Fetch financial news from MarketAux API for a specific ticker.
    
    MarketAux provides comprehensive financial news with built-in sentiment analysis.
    Free tier: 100 requests/day, 10 results per request.
    
    Args:
        ticker: Stock symbol (e.g., "AAPL", "TSLA")
        limit: Maximum number of news articles to fetch (default: 10)
        url_filter_func: Optional async function that takes a URL and returns True
                         if the article should be SKIPPED (e.g. already in DB).
    
    Returns:
        List of normalized news dictionaries.
    """
    ticker = ticker.upper().strip()
    logger.info(f"Fetching MarketAux news for ticker: {ticker}")
    
    if not MARKETAUX_API_KEY:
        logger.warning(
            "MarketAux API key not found. Set MARKETAUX_API_KEY in .env. "
            "Get free key at: https://www.marketaux.com"
        )
        return []
    
    async with httpx.AsyncClient(timeout=DEFAULT_TIMEOUT) as client:
        try:
            params = {
                "api_token": MARKETAUX_API_KEY,
                "symbols": ticker,
                "limit": limit,
                "filter_entities": "true",
                "language": "en",
                "sort": "published_desc"  # Latest news first
            }
            
            response = await client.get(
                MARKETAUX_BASE_URL,
                params=params
            )
            response.raise_for_status()
            data = response.json()
            
            # Extract articles from response
            articles = data.get("data", [])
            
            # Process articles concurrently to fetch full text
            async def process_article(article):
                url = article.get("url", "")
                full_text = ""
                is_cached = False
                
                # Only check cache if we're going to fetch content (skip if skip_full_text=True)
                if url_filter_func and url and not skip_full_text:
                    try:
                        should_skip = await url_filter_func(url)
                        if should_skip:
                            logger.debug(f"Skipping content fetch for cached URL: {url}")
                            is_cached = True
                    except Exception as e:
                        logger.error(f"Error in url_filter_func: {e}")

                # Fetch full text if URL exists and not cached (and not skipped)
                if url and not is_cached and not skip_full_text:
                    full_text = await fetch_article_content(url)
                
                # Extract entity-specific sentiment for this ticker
                ticker_sentiment = 0
                ticker_relevance = 0
                
                for entity in article.get("entities", []):
                    if entity.get("symbol", "").upper() == ticker:
                        ticker_sentiment = entity.get("sentiment_score", 0)
                        ticker_relevance = entity.get("match_score", 0)
                        break
                
                return {
                    "source": "marketaux",
                    "news_source": article.get("source", ""),
                    "title": article.get("title", ""),
                    "description": article.get("description", "") or article.get("snippet", ""),
                    "full_text": full_text,
                    "url": url,
                    "published_at": article.get("published_at", ""),
                    "sentiment_score": ticker_sentiment,
                    "relevance_score": ticker_relevance,
                    "keywords": article.get("keywords", "").split(",") if article.get("keywords") else [],
                    "is_cached": is_cached,  # Flag to indicate if content was from cache (skipped)
                    "entities": [
                        {
                            "symbol": e.get("symbol"),
                            "name": e.get("name"),
                            "sentiment": e.get("sentiment_score", 0)
                        }
                        for e in article.get("entities", [])[:5]  # Top 5 entities
                    ]
                }

            # Gather all article processing tasks
            news_articles = await asyncio.gather(*[process_article(a) for a in articles])
            
            logger.info(f"Fetched {len(news_articles)} MarketAux news articles for {ticker}")
            return list(news_articles)
            
        except httpx.HTTPStatusError as e:
            if e.response.status_code == 429:
                logger.warning(f"MarketAux rate limit exceeded. Free tier: 100 requests/day")
            else:
                logger.error(f"HTTP error fetching MarketAux news: {e.response.status_code}")
            return []
        except httpx.TimeoutException:
            logger.warning(f"Timeout fetching MarketAux news for {ticker}")
            return []
        except Exception as e:
            logger.error(f"Unexpected error fetching MarketAux news: {e}")
            return []


async def fetch_twitter_posts(ticker: str, limit: int = 20, min_followers: int = 50) -> list[dict]:
    """
    Fetch recent tweets about a ticker using ScrapeBadger.

    Args:
        ticker: Stock symbol (e.g., "AAPL")
        limit: Number of tweets to fetch (default: 20)
        min_followers: Unused (ScrapeBadger doesn't return follower counts in search results)

    Returns:
        List of normalized tweet dictionaries
    """
    ticker = ticker.upper().strip()
    cashtag = f"${ticker}"
    logger.info(f"Fetching Twitter posts for {cashtag}")

    if not TWITTER_API_KEY:
        logger.warning("Twitter API key not found. Set TWITTER_API_KEY in .env")
        return []

    async with httpx.AsyncClient(timeout=DEFAULT_TIMEOUT) as client:
        try:
            params = {
                "query": f"{cashtag} lang:en",
                "query_type": "Latest",
            }
            headers = {
                "x-api-key": TWITTER_API_KEY
            }

            response = await client.get(TWITTER_BASE_URL, params=params, headers=headers)

            # On rate limit, wait and retry once
            if response.status_code == 429:
                retry_after = int(response.headers.get("Retry-After", 15))
                logger.warning(f"Twitter 429 for {ticker} — waiting {retry_after}s then retrying")
                await asyncio.sleep(retry_after)
                response = await client.get(TWITTER_BASE_URL, params=params, headers=headers)

            response.raise_for_status()
            data = response.json()

            tweets = data.get("data", [])
            normalized_tweets = []

            for tweet in tweets:
                # Skip retweets
                if tweet.get("is_retweet"):
                    continue

                normalized = {
                    "source": "twitter",
                    "tweet_id": tweet.get("id", ""),
                    "text": tweet.get("full_text") or tweet.get("text", ""),
                    "created_at": tweet.get("created_at", ""),
                    "author": tweet.get("username", ""),
                    "followers": 0,  # Not provided in search results
                    "likes": tweet.get("favorite_count", 0),
                    "retweets": tweet.get("retweet_count", 0),
                    "replies": tweet.get("reply_count", 0),
                    "views": tweet.get("view_count", 0),
                    "url": f"https://twitter.com/{tweet.get('username', 'i')}/status/{tweet.get('id', '')}"
                }
                normalized_tweets.append(normalized)

                if len(normalized_tweets) >= limit:
                    break

            logger.info(f"Fetched {len(normalized_tweets)} tweets for {ticker}")
            return normalized_tweets

        except Exception as e:
            logger.error(f"Error fetching tweets for {ticker}: {e}")
            return []


async def fetch_all_sentiment_sources(
    ticker: str,
    url_filter_func: Optional[Callable[[str], Awaitable[bool]]] = None,
    skip_full_text: bool = False
) -> dict[str, Any]:
    """
    Fetch sentiment data from all available sources.

    Fetches data from Reddit, MarketAux, and Twitter in parallel.

    Args:
        ticker: Stock symbol (e.g., "AAPL", "TSLA")
        url_filter_func: Optional async function to check if URL already exists (deduplication)

    Returns:
        Dictionary with fields:
            - ticker: Stock symbol
            - reddit_posts: List of Reddit post dicts
            - marketaux_news: List of news article dicts
            - twitter_posts: List of tweet dicts
    """
    ticker = ticker.upper().strip()
    logger.info(f"Fetching all sentiment sources for {ticker}")

    # Fetch from all sources in parallel
    reddit_task = fetch_reddit_posts_for_ticker(ticker)
    marketaux_task = fetch_marketaux_news(ticker, url_filter_func=url_filter_func, skip_full_text=skip_full_text)
    twitter_task = fetch_twitter_posts(ticker)
    
    # Wait for all tasks to complete
    results = await asyncio.gather(
        reddit_task,
        marketaux_task,
        twitter_task,
        return_exceptions=True
    )
    
    # Unpack results
    reddit_posts, marketaux_news, twitter_posts = results
    
    # Handle potential exceptions
    if isinstance(reddit_posts, Exception):
        logger.error(f"Reddit fetch failed: {reddit_posts}")
        reddit_posts = []
    
    if isinstance(marketaux_news, Exception):
        logger.error(f"MarketAux fetch failed: {marketaux_news}")
        marketaux_news = []
        
    if isinstance(twitter_posts, Exception):
        logger.error(f"Twitter fetch failed: {twitter_posts}")
        twitter_posts = []

    result = {
        "ticker": ticker,
        "reddit_posts": reddit_posts if isinstance(reddit_posts, list) else [],
        "marketaux_news": marketaux_news if isinstance(marketaux_news, list) else [],
        "twitter_posts": twitter_posts if isinstance(twitter_posts, list) else [],
    }

    logger.info(
        f"Sentiment data fetch complete for {ticker}: "
        f"{len(result['reddit_posts'])} Reddit posts, "
        f"{len(result['marketaux_news'])} news articles, "
        f"{len(result['twitter_posts'])} tweets"
    )

    return result


# Testing and demonstration
async def main():
    """Test the sentiment data fetcher with sample tickers."""
    print("\n=== Sentiment Data Fetcher Test ===\n")

    test_ticker = "AAPL"

    # Test 1: Reddit posts
    print(f"Test 1: Fetching Reddit posts for {test_ticker}...")
    reddit_posts = await fetch_reddit_posts_for_ticker(test_ticker, limit=5)
    print(f"✅ Found {len(reddit_posts)} Reddit posts")
    
    # Test 2: MarketAux news
    print(f"Test 2: Fetching MarketAux news for {test_ticker}...")
    news = await fetch_marketaux_news(test_ticker, limit=5)
    print(f"✅ Found {len(news)} news articles")
    
    # Test 3: Twitter posts
    print(f"Test 3: Fetching Twitter posts for {test_ticker}...")
    tweets = await fetch_twitter_posts(test_ticker, limit=5)
    print(f"✅ Found {len(tweets)} tweets")

    # Test 4: All sources (parallel fetch)
    print(f"Test 4: Fetching all sources for {test_ticker}...")
    all_data = await fetch_all_sentiment_sources(test_ticker)
    print(f"✅ Complete!")
    print(f"Total Reddit posts: {len(all_data['reddit_posts'])}")
    print(f"Total news articles: {len(all_data['marketaux_news'])}")
    print(f"Total tweets: {len(all_data['twitter_posts'])}")


if __name__ == "__main__":
    asyncio.run(main())
