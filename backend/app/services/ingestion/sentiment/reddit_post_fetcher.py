"""
Reddit Post Fetcher - Using Native JSON API (No Authentication Required)

Reddit provides public JSON endpoints that don't require authentication:
- https://www.reddit.com/r/{subreddit}/search.json?q={ticker}
- https://www.reddit.com/r/{subreddit}.json

This allows us to fetch actual Reddit posts with titles, content, URLs, scores, and comments.
"""

import logging
import httpx
from typing import List, Dict, Optional
from datetime import datetime

logger = logging.getLogger(__name__)

# Popular stock/investing subreddits
STOCK_SUBREDDITS = [
    "wallstreetbets",
    "stocks",
    "investing",
    "stockmarket",
    "options",
]

DEFAULT_TIMEOUT = 10.0
USER_AGENT = "Mozilla/5.0 (compatible; QuantimentalBot/1.0)"


async def fetch_reddit_posts_for_ticker(
    ticker: str,
    limit: int = 10,
    timeframe: str = "week",
    subreddits: Optional[List[str]] = None
) -> List[Dict]:
    """
    Fetch Reddit posts mentioning a specific ticker from investing subreddits.

    Args:
        ticker: Stock ticker symbol (e.g., "AAPL")
        limit: Number of posts to fetch per subreddit
        timeframe: Time filter - "hour", "day", "week", "month", "year", "all"
        subreddits: List of subreddits to search (defaults to STOCK_SUBREDDITS)

    Returns:
        List of dictionaries containing post data:
        [
            {
                "title": "NVDA earnings beat expectations",
                "url": "https://www.reddit.com/r/wallstreetbets/...",
                "selftext": "Post content...",
                "score": 1523,
                "num_comments": 234,
                "author": "username",
                "subreddit": "wallstreetbets",
                "created_utc": 1700000000,
                "permalink": "/r/wallstreetbets/comments/...",
                "ticker": "NVDA",
                "source": "reddit"
            },
            ...
        ]
    """
    if subreddits is None:
        subreddits = STOCK_SUBREDDITS

    all_posts = []
    ticker_upper = ticker.upper()

    async with httpx.AsyncClient(timeout=DEFAULT_TIMEOUT) as client:
        for subreddit in subreddits:
            try:
                # Search for ticker in subreddit
                url = f"https://www.reddit.com/r/{subreddit}/search.json"
                params = {
                    "q": ticker_upper,
                    "restrict_sr": "1",  # Search only this subreddit
                    "sort": "top",
                    "t": timeframe,
                    "limit": limit,
                }
                headers = {"User-Agent": USER_AGENT}

                response = await client.get(url, params=params, headers=headers)
                response.raise_for_status()

                data = response.json()

                if "data" not in data or "children" not in data["data"]:
                    logger.warning(f"Unexpected Reddit response format for r/{subreddit}")
                    continue

                posts = data["data"]["children"]

                for post in posts:
                    post_data = post["data"]

                    # Filter out removed/deleted posts
                    if post_data.get("removed_by_category") or post_data.get("title") == "[deleted]":
                        continue

                    all_posts.append({
                        "title": post_data.get("title", ""),
                        "url": f"https://www.reddit.com{post_data.get('permalink', '')}",
                        "selftext": post_data.get("selftext", "")[:500],  # Truncate long posts
                        "score": post_data.get("score", 0),
                        "num_comments": post_data.get("num_comments", 0),
                        "author": post_data.get("author", ""),
                        "subreddit": post_data.get("subreddit", subreddit),
                        "created_utc": post_data.get("created_utc", 0),
                        "permalink": post_data.get("permalink", ""),
                        "ticker": ticker_upper,
                        "source": "reddit",
                    })

                logger.info(f"✅ Fetched {len(posts)} posts for {ticker} from r/{subreddit}")

            except httpx.HTTPStatusError as e:
                logger.error(f"❌ Reddit API HTTP error for r/{subreddit}: {e.response.status_code}")
            except httpx.TimeoutException:
                logger.error(f"❌ Reddit API timeout for r/{subreddit}")
            except Exception as e:
                logger.error(f"❌ Reddit API error for r/{subreddit}: {e}")

    # Sort by score (most upvoted first)
    all_posts.sort(key=lambda x: x["score"], reverse=True)

    logger.info(f"✅ Total {len(all_posts)} Reddit posts fetched for {ticker}")
    return all_posts


async def fetch_trending_reddit_posts(
    subreddit: str = "wallstreetbets",
    limit: int = 25,
    timeframe: str = "day"
) -> List[Dict]:
    """
    Fetch trending posts from a specific subreddit (no ticker filter).

    Args:
        subreddit: Subreddit name
        limit: Number of posts to fetch
        timeframe: Time filter - "hour", "day", "week", "month", "year", "all"

    Returns:
        List of post dictionaries
    """
    try:
        url = f"https://www.reddit.com/r/{subreddit}/top.json"
        params = {
            "t": timeframe,
            "limit": limit,
        }
        headers = {"User-Agent": USER_AGENT}

        async with httpx.AsyncClient(timeout=DEFAULT_TIMEOUT) as client:
            response = await client.get(url, params=params, headers=headers)
            response.raise_for_status()

            data = response.json()
            posts = data["data"]["children"]

            formatted_posts = []
            for post in posts:
                post_data = post["data"]

                if post_data.get("removed_by_category") or post_data.get("title") == "[deleted]":
                    continue

                formatted_posts.append({
                    "title": post_data.get("title", ""),
                    "url": f"https://www.reddit.com{post_data.get('permalink', '')}",
                    "selftext": post_data.get("selftext", "")[:500],
                    "score": post_data.get("score", 0),
                    "num_comments": post_data.get("num_comments", 0),
                    "author": post_data.get("author", ""),
                    "subreddit": post_data.get("subreddit", subreddit),
                    "created_utc": post_data.get("created_utc", 0),
                    "permalink": post_data.get("permalink", ""),
                    "source": "reddit",
                })

            logger.info(f"✅ Fetched {len(formatted_posts)} trending posts from r/{subreddit}")
            return formatted_posts

    except Exception as e:
        logger.error(f"❌ Error fetching trending posts from r/{subreddit}: {e}")
        return []


async def fetch_post_comments(
    permalink: str,
    limit: int = 50,
    sort: str = "top"
) -> List[Dict]:
    """
    Fetch comments for a specific Reddit post.

    Args:
        permalink: Post permalink (e.g., "/r/wallstreetbets/comments/abc123/...")
        limit: Number of top-level comments to fetch
        sort: Comment sort order - "top", "new", "best", "controversial"

    Returns:
        List of comment dictionaries:
        [
            {
                "id": "comment_id",
                "author": "username",
                "body": "comment text",
                "score": 42,
                "created_utc": 1700000000,
                "permalink": "/r/sub/comments/.../comment_id/",
                "replies_count": 5,
                "depth": 0
            },
            ...
        ]
    """
    try:
        # Construct the JSON URL
        url = f"https://www.reddit.com{permalink}.json"
        params = {
            "limit": limit,
            "sort": sort,
        }
        headers = {"User-Agent": USER_AGENT}

        async with httpx.AsyncClient(timeout=DEFAULT_TIMEOUT) as client:
            response = await client.get(url, params=params, headers=headers)
            response.raise_for_status()

            data = response.json()

            # Reddit returns [post_data, comments_data]
            if not isinstance(data, list) or len(data) < 2:
                logger.warning(f"Unexpected Reddit comments response format for {permalink}")
                return []

            comments_data = data[1]  # Second element is comments
            if "data" not in comments_data or "children" not in comments_data["data"]:
                return []

            comments = []
            for comment in comments_data["data"]["children"]:
                if comment["kind"] != "t1":  # t1 = comment
                    continue

                comment_data = comment["data"]

                # Skip deleted/removed comments
                if comment_data.get("author") == "[deleted]" or comment_data.get("body") == "[deleted]":
                    continue

                # Count replies
                replies_count = 0
                if "replies" in comment_data and comment_data["replies"]:
                    if isinstance(comment_data["replies"], dict):
                        replies_data = comment_data["replies"].get("data", {})
                        replies_count = len(replies_data.get("children", []))

                comments.append({
                    "id": comment_data.get("id", ""),
                    "author": comment_data.get("author", ""),
                    "body": comment_data.get("body", "")[:1000],  # Truncate long comments
                    "score": comment_data.get("score", 0),
                    "created_utc": comment_data.get("created_utc", 0),
                    "permalink": comment_data.get("permalink", ""),
                    "replies_count": replies_count,
                    "depth": comment_data.get("depth", 0),
                })

            logger.info(f"✅ Fetched {len(comments)} comments from {permalink}")
            return comments

    except httpx.HTTPStatusError as e:
        logger.error(f"❌ Reddit API HTTP error for comments {permalink}: {e.response.status_code}")
        return []
    except httpx.TimeoutException:
        logger.error(f"❌ Reddit API timeout for comments {permalink}")
        return []
    except Exception as e:
        logger.error(f"❌ Error fetching comments for {permalink}: {e}")
        return []


async def get_post_sentiment_score(post: Dict) -> float:
    """
    Calculate sentiment score from Reddit post metrics.

    Args:
        post: Post dictionary with score, num_comments

    Returns:
        Sentiment score from -1.0 to +1.0
    """
    score = post.get("score", 0)
    comments = post.get("num_comments", 0)

    # Posts with high upvotes = bullish
    # Posts with comments but low score = controversial/bearish
    if score > 0:
        # Logarithmic scale for upvotes
        import math
        upvote_score = min(math.log10(score + 1) / 4.0, 1.0)

        # Comment engagement boost
        comment_boost = min(comments / 100, 0.2)

        return min(upvote_score + comment_boost, 1.0)
    else:
        # Negative or zero score = bearish
        return max(score / 100, -1.0)


async def analyze_comment_sentiment(comments: List[Dict]) -> Dict[str, any]:
    """
    Analyze sentiment from Reddit comments.

    Args:
        comments: List of comment dictionaries

    Returns:
        Dictionary with:
        - average_score: Average upvote score
        - total_comments: Total number of comments
        - sentiment_score: Calculated sentiment (-1.0 to +1.0)
        - top_comments: Top 5 comments by score
    """
    if not comments:
        return {
            "average_score": 0,
            "total_comments": 0,
            "sentiment_score": 0.0,
            "top_comments": []
        }

    scores = [c.get("score", 0) for c in comments]
    avg_score = sum(scores) / len(scores) if scores else 0

    # Calculate sentiment based on average comment score
    import math
    if avg_score > 0:
        sentiment = min(math.log10(avg_score + 1) / 3.0, 1.0)
    else:
        sentiment = max(avg_score / 10, -1.0)

    # Get top comments
    top_comments = sorted(comments, key=lambda x: x.get("score", 0), reverse=True)[:5]

    return {
        "average_score": round(avg_score, 2),
        "total_comments": len(comments),
        "sentiment_score": round(sentiment, 3),
        "top_comments": [
            {
                "author": c.get("author"),
                "body": c.get("body", "")[:200],  # First 200 chars
                "score": c.get("score"),
            }
            for c in top_comments
        ]
    }


# Test function
async def test_reddit_post_fetcher():
    """Test the Reddit post fetcher."""
    print("Testing Reddit Post Fetcher (Native JSON API)")
    print("=" * 70)

    # Test 1: Fetch posts for specific ticker
    print("\n📊 Test 1: Fetching posts for NVDA...")
    nvda_posts = await fetch_reddit_posts_for_ticker("NVDA", limit=5, timeframe="week")

    if nvda_posts:
        print(f"\n✅ Found {len(nvda_posts)} posts for NVDA\n")
        print(f"{'Score':<8} {'Comments':<10} {'Subreddit':<20} {'Title':<50}")
        print("-" * 90)

        for post in nvda_posts[:10]:
            title = post["title"][:47] + "..." if len(post["title"]) > 50 else post["title"]
            print(f"{post['score']:<8} {post['num_comments']:<10} r/{post['subreddit']:<19} {title}")

            # Calculate sentiment
            sentiment = await get_post_sentiment_score(post)
            print(f"  → Sentiment: {sentiment:+.3f} | URL: {post['url'][:60]}...")
    else:
        print("⚠️  No posts found for NVDA")

    # Test 2: Fetch trending posts
    print("\n" + "=" * 70)
    print("📊 Test 2: Fetching trending posts from r/wallstreetbets...")
    trending = await fetch_trending_reddit_posts("wallstreetbets", limit=10, timeframe="day")

    if trending:
        print(f"\n✅ Found {len(trending)} trending posts\n")
        print(f"{'Score':<8} {'Comments':<10} {'Title':<60}")
        print("-" * 80)

        for post in trending[:5]:
            title = post["title"][:57] + "..." if len(post["title"]) > 60 else post["title"]
            print(f"{post['score']:<8} {post['num_comments']:<10} {title}")
    else:
        print("⚠️  No trending posts found")


if __name__ == "__main__":
    import asyncio
    asyncio.run(test_reddit_post_fetcher())