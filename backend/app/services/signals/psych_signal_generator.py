"""
Psych Signal Generator Service

Generates PsychSignals from raw sentiment events.
Aggregates daily sentiment data and classifies emotional states.
"""

import logging
from datetime import date, datetime, timedelta
from typing import Optional, List, Dict, Any
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession
import json

from app.db.models import Stock, SentimentEvent, PsychSignal

logger = logging.getLogger(__name__)


class PsychSignalGenerator:
    """
    Generates and persists PsychSignals from sentiment events.

    Workflow:
    1. Fetch all sentiment events for a specific date
    2. Calculate aggregate sentiment score (average)
    3. Calculate mention count and 30-day average
    4. Classify emotion based on sentiment and velocity
    5. Extract top keywords
    6. Persist PsychSignal to database
    """

    # Emotion classification thresholds
    SENTIMENT_VERY_POSITIVE = 0.3
    SENTIMENT_POSITIVE = 0.1
    SENTIMENT_NEGATIVE = -0.1
    SENTIMENT_VERY_NEGATIVE = -0.3

    HYPE_EXTREME = 3.0  # 3x normal mention volume
    HYPE_HIGH = 2.0
    HYPE_MODERATE = 1.5

    def __init__(self, session: AsyncSession):
        """
        Initialize the generator.

        Args:
            session: Async database session
        """
        self.session = session

    async def fetch_sentiment_events(
        self,
        ticker: str,
        target_date: date
    ) -> List[SentimentEvent]:
        """
        Fetch all sentiment events for a ticker on a specific date.

        Args:
            ticker: Stock ticker symbol
            target_date: Date to fetch events for

        Returns:
            List of SentimentEvent objects
        """
        start_datetime = datetime.combine(target_date, datetime.min.time())
        end_datetime = datetime.combine(target_date, datetime.max.time())

        result = await self.session.execute(
            select(SentimentEvent)
            .where(SentimentEvent.ticker == ticker)
            .where(SentimentEvent.timestamp >= start_datetime)
            .where(SentimentEvent.timestamp <= end_datetime)
        )
        events = result.scalars().all()
        return list(events)

    async def calculate_30day_avg_mentions(
        self,
        ticker: str,
        target_date: date
    ) -> float:
        """
        Calculate 30-day average mention count for a ticker.

        Args:
            ticker: Stock ticker symbol
            target_date: End date for 30-day period

        Returns:
            Average mentions per day over last 30 days
        """
        start_date = target_date - timedelta(days=30)
        start_datetime = datetime.combine(start_date, datetime.min.time())
        end_datetime = datetime.combine(target_date, datetime.max.time())

        # Count total mentions in last 30 days
        result = await self.session.execute(
            select(func.count(SentimentEvent.id))
            .where(SentimentEvent.ticker == ticker)
            .where(SentimentEvent.timestamp >= start_datetime)
            .where(SentimentEvent.timestamp <= end_datetime)
        )
        total_mentions = result.scalar() or 0

        # Return average per day
        avg_mentions = total_mentions / 30.0
        return round(avg_mentions, 2)

    def classify_emotion(
        self,
        sentiment_score: float,
        hype_velocity: float
    ) -> str:
        """
        Classify emotional state based on sentiment and hype.

        Emotion classifications:
        - EXTREME_GREED: Very positive + extreme hype
        - FOMO: Positive + high hype (fear of missing out)
        - GREED: Very positive sentiment
        - OPTIMISM: Positive sentiment
        - NEUTRAL: Neutral sentiment
        - CONCERN: Negative sentiment
        - FEAR: Very negative sentiment
        - FUD: Very negative + high mentions (fear, uncertainty, doubt)

        Args:
            sentiment_score: Average sentiment (-1.0 to +1.0)
            hype_velocity: Mention velocity vs 30-day average

        Returns:
            Emotion classification string
        """
        # Extreme positive cases
        if sentiment_score >= self.SENTIMENT_VERY_POSITIVE:
            if hype_velocity >= self.HYPE_EXTREME:
                return "EXTREME_GREED"
            return "GREED"

        # Positive with FOMO potential
        if sentiment_score >= self.SENTIMENT_POSITIVE:
            if hype_velocity >= self.HYPE_HIGH:
                return "FOMO"
            return "OPTIMISM"

        # Extreme negative cases
        if sentiment_score <= self.SENTIMENT_VERY_NEGATIVE:
            if hype_velocity >= self.HYPE_HIGH:
                return "FUD"  # High mentions + very negative = FUD
            return "FEAR"

        # Negative
        if sentiment_score <= self.SENTIMENT_NEGATIVE:
            return "CONCERN"

        # Default neutral
        return "NEUTRAL"

    def extract_top_keywords(
        self,
        events: List[SentimentEvent],
        top_n: int = 5
    ) -> List[str]:
        """
        Extract top keywords from sentiment event texts.

        Simple implementation: most common words (excluding stopwords).
        TODO: Enhance with NLP for better keyword extraction.

        Args:
            events: List of sentiment events
            top_n: Number of top keywords to return

        Returns:
            List of top keywords
        """
        # Simple stopwords list
        stopwords = {
            'the', 'a', 'an', 'and', 'or', 'but', 'in', 'on', 'at', 'to', 'for',
            'of', 'is', 'are', 'was', 'were', 'be', 'been', 'being', 'have', 'has',
            'had', 'do', 'does', 'did', 'will', 'would', 'should', 'could', 'may',
            'might', 'can', 'this', 'that', 'these', 'those', 'i', 'you', 'he',
            'she', 'it', 'we', 'they', 'what', 'which', 'who', 'when', 'where',
            'why', 'how', 'all', 'each', 'every', 'both', 'few', 'more', 'most',
            'other', 'some', 'such', 'no', 'not', 'only', 'own', 'same', 'so',
            'than', 'too', 'very', 's', 't', 'just', 'now', 'get', 'like'
        }

        word_counts = {}

        for event in events:
            if not event.text:
                continue

            # Simple word tokenization (lowercase, split by spaces)
            words = event.text.lower().split()

            for word in words:
                # Remove punctuation
                word = ''.join(c for c in word if c.isalnum())

                # Skip stopwords and short words
                if len(word) <= 2 or word in stopwords:
                    continue

                word_counts[word] = word_counts.get(word, 0) + 1

        # Sort by frequency and get top N
        top_keywords = sorted(
            word_counts.items(),
            key=lambda x: x[1],
            reverse=True
        )[:top_n]

        return [word for word, count in top_keywords]

    async def generate_signal_for_ticker(
        self,
        ticker: str,
        analysis_date: date
    ) -> Optional[PsychSignal]:
        """
        Generate a PsychSignal for a specific ticker and date.

        Args:
            ticker: Stock ticker symbol
            analysis_date: Date to generate signal for

        Returns:
            PsychSignal object if successful, None if no data
        """
        logger.info(f"Generating PsychSignal for {ticker} on {analysis_date}")

        try:
            # 1. Fetch sentiment events
            events = await self.fetch_sentiment_events(ticker, analysis_date)

            if not events:
                logger.warning(f"No sentiment events for {ticker} on {analysis_date}")
                return None

            mention_count = len(events)

            # 2. Calculate aggregate sentiment score
            sentiment_scores = [
                e.sentiment_score for e in events
                if e.sentiment_score is not None
            ]

            if not sentiment_scores:
                logger.warning(f"No sentiment scores for {ticker} on {analysis_date}")
                return None

            avg_sentiment = sum(sentiment_scores) / len(sentiment_scores)

            # 3. Calculate 30-day average and hype velocity
            avg_30d = await self.calculate_30day_avg_mentions(ticker, analysis_date)

            if avg_30d > 0:
                hype_velocity = mention_count / avg_30d
            else:
                hype_velocity = 1.0  # Default to 1x if no historical data

            # 4. Classify emotion
            emotion = self.classify_emotion(avg_sentiment, hype_velocity)

            # 5. Extract top keywords
            top_keywords = self.extract_top_keywords(events, top_n=5)

            # 6. Create PsychSignal record
            psych_signal = PsychSignal(
                ticker=ticker,
                date=analysis_date,
                sentiment_score=round(avg_sentiment, 3),
                emotion=emotion,
                hype_velocity=round(hype_velocity, 2),
                mention_count=mention_count,
                mention_avg_30d=int(avg_30d),
                top_keywords=json.dumps(top_keywords)
            )

            # Check if signal already exists (upsert logic)
            existing = await self.session.execute(
                select(PsychSignal)
                .where(PsychSignal.ticker == ticker)
                .where(PsychSignal.date == analysis_date)
            )
            existing_signal = existing.scalar_one_or_none()

            if existing_signal:
                # Update existing
                logger.info(f"Updating existing PsychSignal for {ticker} on {analysis_date}")
                existing_signal.sentiment_score = psych_signal.sentiment_score
                existing_signal.emotion = psych_signal.emotion
                existing_signal.hype_velocity = psych_signal.hype_velocity
                existing_signal.mention_count = psych_signal.mention_count
                existing_signal.mention_avg_30d = psych_signal.mention_avg_30d
                existing_signal.top_keywords = psych_signal.top_keywords
                result_signal = existing_signal
            else:
                # Insert new
                logger.info(f"Creating new PsychSignal for {ticker} on {analysis_date}")
                self.session.add(psych_signal)
                result_signal = psych_signal

            await self.session.commit()
            await self.session.refresh(result_signal)

            logger.info(
                f"✅ PsychSignal generated: {ticker} → {emotion} "
                f"(sentiment={avg_sentiment:.3f}, velocity={hype_velocity:.2f}x)"
            )

            return result_signal

        except Exception as e:
            logger.error(f"Error generating PsychSignal for {ticker}: {e}")
            await self.session.rollback()
            return None

    async def generate_signals_for_date(
        self,
        analysis_date: date
    ) -> List[PsychSignal]:
        """
        Generate PsychSignals for all stocks with sentiment data on a date.

        Args:
            analysis_date: Date to generate signals for

        Returns:
            List of PsychSignal objects
        """
        logger.info(f"Generating PsychSignals for all stocks on {analysis_date}")

        # Get all unique tickers with sentiment events on this date
        start_datetime = datetime.combine(analysis_date, datetime.min.time())
        end_datetime = datetime.combine(analysis_date, datetime.max.time())

        result = await self.session.execute(
            select(SentimentEvent.ticker)
            .where(SentimentEvent.timestamp >= start_datetime)
            .where(SentimentEvent.timestamp <= end_datetime)
            .distinct()
        )
        tickers = [row[0] for row in result.all()]

        if not tickers:
            logger.warning(f"No sentiment events found for {analysis_date}")
            return []

        logger.info(f"Found {len(tickers)} tickers with sentiment data")

        # Generate PsychSignal for each ticker
        psych_signals = []
        for ticker in tickers:
            signal = await self.generate_signal_for_ticker(ticker, analysis_date)
            if signal:
                psych_signals.append(signal)

        logger.info(f"✅ Generated {len(psych_signals)} PsychSignals for {analysis_date}")
        return psych_signals

    async def backfill_signals(
        self,
        start_date: date,
        end_date: date
    ) -> Dict[str, int]:
        """
        Backfill PsychSignals for a date range.

        Args:
            start_date: Start date (inclusive)
            end_date: End date (inclusive)

        Returns:
            Dictionary with statistics
        """
        logger.info(f"Backfilling PsychSignals from {start_date} to {end_date}")

        total_signals = 0
        current_date = start_date

        while current_date <= end_date:
            signals = await self.generate_signals_for_date(current_date)
            total_signals += len(signals)
            current_date += timedelta(days=1)

        logger.info(f"✅ Backfill complete: {total_signals} PsychSignals generated")

        return {
            'total_signals': total_signals,
            'date_range': f"{start_date} to {end_date}"
        }