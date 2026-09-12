"""
News Content Fetcher Worker

This service:
1. Consumes metadata-only news events from Kafka (topic: `news_raw` or `sentiment.raw_events`).
2. Fetches the full content of the article using `trafilatura`.
3. Stores the full article in the database (`news_articles`).
4. Produces enriched events (with content) to a new Kafka topic (`news_enriched`) for downstream processing.

"""

import asyncio
import json
import logging
import signal
from datetime import datetime
from typing import Optional

import trafilatura
from aiokafka import AIOKafkaConsumer, AIOKafkaProducer
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.db.models import NewsArticle
from app.db.session import async_session

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)

settings = get_settings()

# Constants
MAX_ARTICLE_LENGTH = 10000  # Max chars to store/process
KAFKA_GROUP_ID = "quantimental-news-fetcher"
TOPIC_INPUT = settings.KAFKA_TOPIC_SENTIMENT_RAW
TOPIC_OUTPUT = "news.enriched"


class NewsFetcherWorker:
    def __init__(self):
        self.consumer: Optional[AIOKafkaConsumer] = None
        self.producer: Optional[AIOKafkaProducer] = None
        self.running = True

    async def start(self):
        """Initialize Kafka consumer and producer."""
        logger.info("Starting News Fetcher Worker...")
        
        # Producer for enriched events
        self.producer = AIOKafkaProducer(
            bootstrap_servers=settings.KAFKA_BOOTSTRAP_SERVERS,
            value_serializer=lambda v: json.dumps(v).encode("utf-8")
        )
        await self.producer.start()

        # Consumer for raw events
        self.consumer = AIOKafkaConsumer(
            TOPIC_INPUT,
            bootstrap_servers=settings.KAFKA_BOOTSTRAP_SERVERS,
            group_id=KAFKA_GROUP_ID,
            value_deserializer=lambda m: json.loads(m.decode("utf-8")),
            auto_offset_reset="earliest"
        )
        await self.consumer.start()
        logger.info(f"Listening on topic: {TOPIC_INPUT}")

    async def stop(self):
        """Graceful shutdown."""
        logger.info("Stopping worker...")
        self.running = False
        if self.consumer:
            await self.consumer.stop()
        if self.producer:
            await self.producer.stop()

    async def fetch_content(self, url: str) -> Optional[str]:
        """Fetch and clean article text from URL."""
        if not url:
            return None
            
        try:
            # Run blocking I/O in thread pool
            loop = asyncio.get_event_loop()
            downloaded = await loop.run_in_executor(None, trafilatura.fetch_url, url)
            
            if not downloaded:
                return None
                
            text = await loop.run_in_executor(
                None, 
                lambda: trafilatura.extract(
                    downloaded,
                    include_comments=False,
                    include_tables=False,
                    no_fallback=True
                )
            )
            
            if text and len(text) > MAX_ARTICLE_LENGTH:
                text = text[:MAX_ARTICLE_LENGTH] + "... [TRUNCATED]"
                
            return text
            
        except Exception as e:
            logger.warning(f"Failed to fetch {url}: {e}")
            return None

    async def process_event(self, event: dict):
        """Process a single Kafka event."""
        event_type = event.get("event_type")
        source_type = event.get("source_type")
        payload = event.get("payload", {})
        
        # We only care about news articles that need content
        if source_type != "news":
            return  # Skip non-news events
            
        url = payload.get("url")
        if not url:
            logger.debug("Skipping event with no URL")
            return

        # Check DB first (Deduplication)
        content = None
        async with async_session() as session:
            article = await self._get_or_create_article(session, payload)
            
            # If we already have content, skip fetching
            if article.is_content_available:
                logger.info(f"Content already available for {url}, skipping fetch.")
                content = article.content
            else:
                # Fetch content
                logger.info(f"Fetching content for {url}")
                content = await self.fetch_content(url)
                
                # Update DB
                if content:
                    article.content = content
                    article.is_content_available = True
                    article.content_fetched_at = datetime.utcnow()
                    await session.commit()
                    logger.info(f"Stored content for {url} ({len(content)} chars)")
                else:
                    logger.warning(f"No content extracted for {url}")

        # Produce enriched event
        enriched_event = event.copy()
        # Ensure payload is a dict (copy it if it exists)
        enriched_event["payload"] = payload.copy() if payload else {}
        
        enriched_event["payload"]["full_text"] = content
        enriched_event["payload"]["is_content_available"] = bool(content)
        enriched_event["enrichment_stage"] = "news_fetcher"
        
        await self.producer.send(TOPIC_OUTPUT, enriched_event)

    async def _get_or_create_article(self, session: AsyncSession, payload: dict) -> NewsArticle:
        """Get existing article from DB or create a placeholder."""
        url = payload.get("url")
        result = await session.execute(select(NewsArticle).where(NewsArticle.url == url))
        article = result.scalar_one_or_none()
        
        if not article:
            # Create new record
            article = NewsArticle(
                url=url,
                title=payload.get("title", "Unknown"),
                source_domain=payload.get("news_source", "Unknown"),
                published_at=None, # Parse this if needed
                author=None,
                is_content_available=False
            )
            # Handle date parsing carefully if needed, or leave null
            pub_date = payload.get("published_at")
            if pub_date:
                try:
                    # Basic ISO parsing, might need robust parser
                    article.published_at = datetime.fromisoformat(pub_date.replace("Z", "+00:00"))
                except:
                    pass
                    
            session.add(article)
            await session.commit()
            await session.refresh(article)
            
        return article

    async def run(self):
        """Main loop."""
        await self.start()
        try:
            async for msg in self.consumer:
                try:
                    await self.process_event(msg.value)
                except Exception as e:
                    logger.error(f"Error processing message: {e}")
        finally:
            await self.stop()


async def main():
    worker = NewsFetcherWorker()
    
    # Handle shutdown signals
    loop = asyncio.get_event_loop()
    for sig in (signal.SIGTERM, signal.SIGINT):
        loop.add_signal_handler(sig, lambda: asyncio.create_task(worker.stop()))
        
    await worker.run()


if __name__ == "__main__":
    asyncio.run(main())

