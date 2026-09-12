import json
import logging
from typing import Any
from aiokafka import AIOKafkaProducer
from app.core.config import get_settings

logger = logging.getLogger(__name__)
settings = get_settings()

class KafkaProducerClient:
    def __init__(self):
        self.producer = None

    async def start(self):
        """Initialize the Kafka producer."""
        if self.producer is None:
            try:
                self.producer = AIOKafkaProducer(
                    bootstrap_servers=settings.KAFKA_BOOTSTRAP_SERVERS,
                    value_serializer=lambda v: json.dumps(v).encode("utf-8")
                )
                await self.producer.start()
                logger.info("Kafka producer started")
            except Exception as e:
                logger.error(f"Failed to start Kafka producer: {e}")
                # Don't raise here to allow app startup even if Kafka is down temporarily
                self.producer = None

    async def stop(self):
        """Stop the Kafka producer."""
        if self.producer:
            await self.producer.stop()
            self.producer = None
            logger.info("Kafka producer stopped")

    async def send(self, topic: str, value: Any):
        """Send a message to a Kafka topic."""
        if not self.producer:
            # Try to restart/start if missing
            await self.start()
            
        if not self.producer:
            logger.warning(f"Kafka producer not available. Dropping message for {topic}")
            return

        try:
            await self.producer.send_and_wait(topic, value)
        except Exception as e:
            logger.error(f"Failed to send message to {topic}: {e}")

# Global instance
kafka_producer = KafkaProducerClient()

