import asyncio
import json
import logging
import signal
from datetime import datetime, timedelta, timezone

from aiokafka import AIOKafkaConsumer
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import text

from app.core.config import get_settings
from app.db.session import async_session
from app.db.models import SentimentEvent, SentimentAggregate

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)

logger = logging.getLogger(__name__)
settings = get_settings()

def round_bucket(ts: datetime, minutes=15):
    return ts.replace(minute=ts.minute - ts.minute % minutes, second=0, microsecond=0)

async def process_and_persist(event, session: AsyncSession):
    ticker = event.get("ticker")
    if not ticker:
        return

    ts_str = event.get("timestamp")
    try:
        if isinstance(ts_str, (int, float)):
            ts = datetime.fromtimestamp(ts_str)
        else:
            ts = datetime.fromisoformat(str(ts_str).replace("Z", "+00:00"))
    except Exception:
        ts = datetime.utcnow()
    
    # Ensure naive UTC for consistency with DB
    if ts.tzinfo is not None:
        ts = ts.astimezone(timezone.utc).replace(tzinfo=None)

    sentiment_data = event.get("sentiment", {})
    score = sentiment_data.get("score", 0.0)
    label = sentiment_data.get("label", "neutral")
    confidence = sentiment_data.get("confidence", 0.0)
    
    bucket = round_bucket(ts)
    
    payload = event.get("payload", {})
    source = event.get("source_type", "unknown")
    
    # Insert raw event
    # Mapping fields to match SentimentEvent model
    ev = SentimentEvent(
        ticker=ticker,
        timestamp=ts,
        sentiment_score=score, # Model uses sentiment_score
        sentiment_label=label,
        confidence=confidence,
        source=source,
        text=(payload.get("full_text") or payload.get("title") or "")[:1000], # Truncate for storage
        url=payload.get("url"),
        author=payload.get("author"),
        ingested_at=datetime.utcnow()
    )
    session.add(ev)

    # Update aggregate
    # Using raw SQL for atomic upsert (ON CONFLICT)
    await session.execute(
        text("""
        INSERT INTO sentiment_aggregates (ticker, bucket, total_score, count)
        VALUES (:ticker, :bucket, :score, 1)
        ON CONFLICT (ticker, bucket)
        DO UPDATE SET
            total_score = sentiment_aggregates.total_score + :score,
            count = sentiment_aggregates.count + 1;
        """),
        {"ticker": ticker, "bucket": bucket, "score": score}
    )

    await session.commit()
    logger.info(f"Persisted event and aggregate for {ticker} at {bucket}")

async def run():
    logger.info("Starting Aggregator Worker...")
    
    consumer = AIOKafkaConsumer(
        settings.KAFKA_TOPIC_SENTIMENT_SCORED,
        bootstrap_servers=settings.KAFKA_BOOTSTRAP_SERVERS,
        group_id="sentiment-aggregator",
        value_deserializer=lambda m: json.loads(m.decode("utf-8")),
        auto_offset_reset="earliest",
    )

    logger.info("Starting Kafka consumer...")
    await consumer.start()
    logger.info("Kafka consumer started")

    try:
        logger.info("Aggregator listening on %s", settings.KAFKA_TOPIC_SENTIMENT_SCORED)
        async for msg in consumer:
            event = msg.value
            async with async_session() as session:
                await process_and_persist(event, session)

    finally:
        await consumer.stop()

def main():
    try:
        asyncio.run(run())
    except KeyboardInterrupt:
        logger.info("Aggregator worker stopped by user")

if __name__ == "__main__":
    main()
