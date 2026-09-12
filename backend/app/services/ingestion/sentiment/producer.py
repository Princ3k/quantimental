import asyncio
import logging
from sqlalchemy import select
from app.services.ingestion.sentiment.sentiment_data_fetcher import fetch_all_sentiment_sources
from app.core.kafka import kafka_producer
from app.core.config import get_settings
from app.db.session import async_session
from app.db.models import NewsArticle

logger = logging.getLogger(__name__)
settings = get_settings()

class SentimentIngestionService:
    """
    Service to fetch sentiment data and publish to Kafka.
    """
    
    async def check_url_exists(self, url: str) -> bool:
        """
        Check if a URL has already been fetched in the DB.
        
        Note: This is only called when skip_full_text=False (when fetching content).
        When skip_full_text=True, this function is not used to avoid unnecessary DB queries.
        """
        if not url:
            return False
            
        async with async_session() as session:
            try:
                # Check if we have content for this URL
                result = await session.execute(
                    select(NewsArticle).where(
                        NewsArticle.url == url,
                        NewsArticle.is_content_available == True
                    )
                )
                exists = result.scalar_one_or_none() is not None
                return exists
            except Exception as e:
                logger.error(f"DB check failed for url {url}: {e}")
                return False
    
    async def run(self, tickers: list[str]):
        """
        Fetch data for tickers and publish to Kafka.
        """
        await kafka_producer.start()
        try:
            for ticker in tickers:
                logger.info(f"Ingesting sentiment for {ticker}")
                
                # Skip full text to avoid slow scraping (News Fetcher worker will handle it)
                # Don't pass url_filter_func when skip_full_text=True to avoid unnecessary DB queries
                data = await fetch_all_sentiment_sources(
                    ticker, 
                    url_filter_func=None,  # Skip DB checks when skip_full_text=True
                    skip_full_text=True  # Fast mode - just metadata
                )
                
                # Publish Reddit posts
                posts = data.get("reddit_posts", [])
                for post in posts:
                    event = {
                        "event_type": "sentiment_ingestion",
                        "source_type": "reddit",
                        "ticker": ticker,
                        "payload": post,
                        "timestamp": post.get("created_utc")
                    }
                    await kafka_producer.send(settings.KAFKA_TOPIC_SENTIMENT_RAW, event)
                
                # Publish News
                news_items = data.get("marketaux_news", [])
                for news in news_items:
                    # If cached, we might want to tag it or handle differently
                    # For now, we still emit the event so the consumer can decide (or update timestamp)
                    # But the payload will not have full_text if it was skipped
                    
                    event = {
                        "event_type": "sentiment_ingestion",
                        "source_type": "news",
                        "ticker": ticker,
                        "payload": news,
                        "timestamp": news.get("published_at")
                    }
                    await kafka_producer.send(settings.KAFKA_TOPIC_SENTIMENT_RAW, event)
                    
                # Publish Tweets
                tweets = data.get("twitter_posts", [])
                for tweet in tweets:
                    event = {
                        "event_type": "sentiment_ingestion",
                        "source_type": "twitter",
                        "ticker": ticker,
                        "payload": tweet,
                        "timestamp": tweet.get("created_at")
                    }
                    await kafka_producer.send(settings.KAFKA_TOPIC_SENTIMENT_RAW, event)
                    
                logger.info(
                    f"Published events for {ticker}: "
                    f"{len(posts)} reddit, {len(news_items)} news, {len(tweets)} tweets"
                )

                # Space out requests to stay within API rate limits (ScrapeBadger: 180 req/15min)
                await asyncio.sleep(5)
        except Exception as e:
            logger.error(f"Error in sentiment ingestion: {e}")
        finally:
            await kafka_producer.stop()

if __name__ == "__main__":
    # Setup logging
    logging.basicConfig(level=logging.INFO)
    
    # Test run
    service = SentimentIngestionService()
    asyncio.run(service.run(["AAPL", "TSLA"]))
