import asyncio
import json
import logging
import signal
from aiokafka import AIOKafkaConsumer
from sqlalchemy import select
from app.core.kafka import kafka_producer
from app.core.config import get_settings
from app.services.enrichment.sentiment.model import SentimentModel
from app.db.session import async_session
from app.db.models import NewsArticle

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)

logger = logging.getLogger(__name__)
settings = get_settings()

async def run():
    logger.info("Starting Classifier Worker...")
    
    consumer = AIOKafkaConsumer(
        settings.KAFKA_TOPIC_SENTIMENT_RAW,
        bootstrap_servers=settings.KAFKA_BOOTSTRAP_SERVERS,
        group_id="sentiment-classifier",
        value_deserializer=lambda m: json.loads(m.decode("utf-8")),
        auto_offset_reset="earliest",
    )

    model = SentimentModel()
    
    # Ensure producer is connected
    logger.info("Starting Kafka producer...")
    await kafka_producer.start()
    logger.info("Kafka producer started")
    
    logger.info("Starting Kafka consumer...")
    await consumer.start()
    logger.info("Kafka consumer started")

    try:
        logger.info("Classifier listening on topic %s", settings.KAFKA_TOPIC_SENTIMENT_RAW)
        async for msg in consumer:
            event = msg.value
            
            # Extract text from payload (support both structure types if needed)
            payload = event.get("payload", {})
            text = payload.get("full_text") or payload.get("description") or payload.get("title") or payload.get("text") or ""
            
            # For news articles, check database for full text if not in payload
            # (News Fetcher Worker stores it in DB but publishes to different topic)
            event_source = event.get("source_type", "").lower()
            if event_source == "news" and not payload.get("full_text"):
                url = payload.get("url")
                if url:
                    try:
                        async with async_session() as session:
                            result = await session.execute(
                                select(NewsArticle).where(
                                    NewsArticle.url == url,
                                    NewsArticle.is_content_available == True
                                )
                            )
                            article = result.scalar_one_or_none()
                            if article and article.content:
                                text = article.content
                                logger.debug(f"Retrieved full text from DB for {url} ({len(text)} chars)")
                    except Exception as e:
                        logger.warning(f"Failed to fetch article content from DB: {e}")
            
            if not text:
                logger.debug(f"Skipping event {event.get('event_id')} - no text found")
                continue

            # Determine ML model source type from event source_type (already set above)
            
            # Map event source types to ML model source types
            if event_source == "news":
                ml_source_type = "news"
            elif event_source in ["reddit", "twitter"]:
                # Use "social" for Reddit/Twitter (Twitter RoBERTa model)
                # For longer Reddit posts, could use "discussion" but "social" is more appropriate
                ml_source_type = "social"
            else:
                # Fallback to VADER for unknown sources
                ml_source_type = None
            
            # Use ML models if source type is known, otherwise fallback to VADER
            if ml_source_type:
                try:
                    ml_result = model.analyze(text, source_type=ml_source_type)
                    # Convert ML result to same format as VADER
                    sentiment_label = ml_result["sentiment"]
                    confidence = ml_result["confidence"]
                    
                    # Map ML sentiment labels to numeric score for compatibility
                    # ML models return: "positive"/"negative"/"neutral" or "bullish"/"bearish"/"neutral"
                    if "bullish" in sentiment_label or "positive" in sentiment_label:
                        score = confidence  # Positive score
                        label = "positive"
                    elif "bearish" in sentiment_label or "negative" in sentiment_label:
                        score = -confidence  # Negative score
                        label = "negative"
                    else:
                        score = 0.0
                        label = "neutral"
                    
                    logger.debug(f"Using ML model ({ml_source_type}) for {event_source}: {sentiment_label} -> {label}")
                except Exception as e:
                    logger.warning(f"ML model failed for {event_source}, falling back to VADER: {e}")
                    # Fallback to VADER
                    score, label, confidence = model.predict(text)
            else:
                # Use VADER for unknown sources or fallback
                score, label, confidence = model.predict(text)
                logger.debug(f"Using VADER for {event_source}")

            enriched = {
                **event,
                "sentiment": {
                    "score": score,
                    "label": label,
                    "confidence": confidence,
                    "model_used": ml_source_type if ml_source_type else "vader"
                }
            }

            # Use the wrapper's send method which handles send_and_wait
            await kafka_producer.send(
                settings.KAFKA_TOPIC_SENTIMENT_SCORED,
                enriched,
            )
            logger.info(f"Processed event for {event.get('ticker')} ({event_source}): {label} ({score:.3f}) [model: {enriched['sentiment']['model_used']}]")

    finally:
        await consumer.stop()
        await kafka_producer.stop()

def main():
    try:
        asyncio.run(run())
    except KeyboardInterrupt:
        logger.info("Classifier worker stopped by user")

if __name__ == "__main__":
    main()

