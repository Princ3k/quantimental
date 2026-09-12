"""
Batch Orchestration Scheduler

Runs ingestion jobs every 6 hours to keep data fresh while preserving API calls:
- 6 AM (pre-market): Full refresh before market opens
- 12 PM (intraday): Midday update during trading
- 6 PM (post-market): Post-close analysis
- 12 AM (midnight): EOD comprehensive refresh

Pipeline: Ingest → Quant → Psych → Hybrid → Feed Refresh
"""

import logging
import asyncio
from datetime import datetime, timedelta
from typing import List, Dict, Any, Optional
import sys
from pathlib import Path

# Add parent directory to path for imports
sys.path.append(str(Path(__file__).parent.parent.parent.parent))

from app.services.ingestion.sentiment.sentiment_data_fetcher import fetch_all_sentiment_sources
from app.services.enrichment.sentiment.model import SentimentModel
from app.services.data.market_data_service import MarketDataService
from app.services.data.real_time_sentiment_service import RealTimeSentimentService
from app.db.session import async_session
from app.db.models import HybridSignal, NewsArticle
from sqlalchemy import select, and_

logger = logging.getLogger(__name__)


class BatchOrchestrator:
    """
    Orchestrates the full ingestion and analysis pipeline.

    Stages:
    1. Ingest: Fetch raw data from Yahoo Finance, Reddit, Twitter, News
    2. Quant: Calculate technical indicators
    3. Psych: Analyze sentiment with ML models
    4. Hybrid: Combine technical + sentiment scores
    5. Persist: Save results to database
    6. Refresh: Update public feed
    """

    def __init__(self, tickers: List[str]):
        """
        Initialize orchestrator with target tickers.

        Args:
            tickers: List of stock symbols to analyze
        """
        self.tickers = tickers
        self.market_service = MarketDataService()
        self.sentiment_service = RealTimeSentimentService()
        self.run_id = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
        self.results: Dict[str, Any] = {}

    async def run_full_pipeline(self) -> Dict[str, Any]:
        """
        Execute the full pipeline for all tickers.

        Returns:
            Dictionary with execution results and metrics
        """
        start_time = datetime.utcnow()
        logger.info(f"🚀 Starting batch run {self.run_id} for {len(self.tickers)} tickers")

        try:
            # Stage 1: Ingest Raw Data
            logger.info("📥 Stage 1/5: Ingesting raw data...")
            ingest_results = await self._stage_ingest()

            # Stage 2: Quantitative Analysis
            logger.info("📊 Stage 2/5: Running quantitative analysis...")
            quant_results = await self._stage_quant()

            # Stage 3: Psychometric Analysis
            logger.info("🧠 Stage 3/5: Performing psychometric analysis...")
            psych_results = await self._stage_psych(ingest_results)

            # Stage 4: Hybrid Scoring
            logger.info("⚖️  Stage 4/5: Computing hybrid scores...")
            hybrid_results = await self._stage_hybrid(quant_results, psych_results)

            # Stage 5: Persist & Refresh Feed
            logger.info("💾 Stage 5/5: Persisting results and refreshing feed...")
            persist_results = await self._stage_persist(hybrid_results)

            end_time = datetime.utcnow()
            duration = (end_time - start_time).total_seconds()

            summary = {
                "run_id": self.run_id,
                "status": "success",
                "start_time": start_time.isoformat(),
                "end_time": end_time.isoformat(),
                "duration_seconds": duration,
                "tickers_processed": len(self.tickers),
                "tickers_succeeded": sum(1 for r in hybrid_results.values() if r.get("success")),
                "tickers_failed": sum(1 for r in hybrid_results.values() if not r.get("success")),
                "stages": {
                    "ingest": ingest_results.get("summary"),
                    "quant": quant_results.get("summary"),
                    "psych": psych_results.get("summary"),
                    "hybrid": hybrid_results.get("summary"),
                    "persist": persist_results,
                }
            }

            logger.info(f"✅ Batch run {self.run_id} completed successfully in {duration:.2f}s")
            logger.info(f"   Processed: {summary['tickers_succeeded']}/{summary['tickers_processed']}")

            return summary

        except Exception as e:
            logger.error(f"❌ Batch run {self.run_id} failed: {e}", exc_info=True)
            return {
                "run_id": self.run_id,
                "status": "failed",
                "error": str(e),
                "start_time": start_time.isoformat(),
            }

    async def _stage_ingest(self) -> Dict[str, Any]:
        """Stage 1: Ingest raw data from all sources."""
        results = {}

        # Fetch sentiment data in parallel for all tickers
        tasks = {
            ticker: fetch_all_sentiment_sources(ticker, skip_full_text=True)
            for ticker in self.tickers
        }

        responses = await asyncio.gather(*tasks.values(), return_exceptions=True)

        for ticker, response in zip(tasks.keys(), responses):
            if isinstance(response, Exception):
                logger.error(f"Failed to ingest {ticker}: {response}")
                results[ticker] = {"success": False, "error": str(response)}
            else:
                reddit_count = len(response.get("reddit_posts", []))
                news_count = len(response.get("marketaux_news", []))
                twitter_count = len(response.get("twitter_posts", []))

                results[ticker] = {
                    "success": True,
                    "reddit_posts": reddit_count,
                    "news_articles": news_count,
                    "tweets": twitter_count,
                    "data": response,
                }

                logger.debug(
                    f"  {ticker}: {reddit_count} Reddit, {news_count} news, {twitter_count} tweets"
                )

        success_count = sum(1 for r in results.values() if r.get("success"))

        return {
            "results": results,
            "summary": {
                "total": len(self.tickers),
                "succeeded": success_count,
                "failed": len(self.tickers) - success_count,
            },
        }

    async def _stage_quant(self) -> Dict[str, Any]:
        """Stage 2: Calculate technical indicators."""
        results = {}

        for ticker in self.tickers:
            try:
                quote = self.market_service.get_quote(ticker)
                if not quote.get("available"):
                    # No market data is a skip, not a crash: the rest of the
                    # batch should still run.
                    results[ticker] = {"success": False, "error": quote.get("reason", "No data")}
                    logger.warning("  %s: %s", ticker, quote.get("reason", "no market data"))
                    continue
                results[ticker] = {"success": True, "quote": quote}
                logger.debug("  %s: Price $%.2f", ticker, quote["price"])
            except Exception as e:
                logger.error(f"Failed quant analysis for {ticker}: {e}")
                results[ticker] = {"success": False, "error": str(e)}

        success_count = sum(1 for r in results.values() if r.get("success"))

        return {
            "results": results,
            "summary": {
                "total": len(self.tickers),
                "succeeded": success_count,
                "failed": len(self.tickers) - success_count,
            },
        }

    async def _stage_psych(self, ingest_results: Dict) -> Dict[str, Any]:
        """Stage 3: Analyze sentiment with ML models."""
        results = {}

        ingest_data = ingest_results.get("results", {})

        for ticker in self.tickers:
            try:
                ticker_data = ingest_data.get(ticker, {})

                if not ticker_data.get("success"):
                    results[ticker] = {"success": False, "error": "Ingest failed"}
                    continue

                # Get sentiment analysis
                sentiment = await self.sentiment_service.get_sentiment_for_ticker(ticker)

                results[ticker] = {
                    "success": True,
                    "sentiment_rating": sentiment.get("sentiment_rating"),
                    "mentions": sentiment.get("mentions"),
                    "velocity": sentiment.get("mention_velocity"),
                }

                logger.debug(
                    f"  {ticker}: Sentiment {sentiment.get('sentiment_rating')}/100, "
                    f"{sentiment.get('mentions')} mentions"
                )

            except Exception as e:
                logger.error(f"Failed psych analysis for {ticker}: {e}")
                results[ticker] = {"success": False, "error": str(e)}

        success_count = sum(1 for r in results.values() if r.get("success"))

        return {
            "results": results,
            "summary": {
                "total": len(self.tickers),
                "succeeded": success_count,
                "failed": len(self.tickers) - success_count,
            },
        }

    async def _stage_hybrid(
        self, quant_results: Dict, psych_results: Dict
    ) -> Dict[str, Any]:
        """Stage 4: Combine quant + psych into hybrid scores."""
        results = {}

        quant_data = quant_results.get("results", {})
        psych_data = psych_results.get("results", {})

        for ticker in self.tickers:
            try:
                quant = quant_data.get(ticker, {})
                psych = psych_data.get(ticker, {})

                if not (quant.get("success") and psych.get("success")):
                    results[ticker] = {"success": False, "error": "Prerequisite stage failed"}
                    continue

                quote = quant.get("quote", {})
                indicators = quote.get("indicators", {})

                # Calculate technical rating (simplified from ingestion.py)
                rsi = indicators.get("rsi", 50)
                technical_rating = int(100 - abs(rsi - 50) * 2)

                # Get sentiment rating
                sentiment_rating = psych.get("sentiment_rating", 50)

                # Hybrid score: 45% technical + 55% sentiment
                hybrid_score = int(0.45 * technical_rating + 0.55 * sentiment_rating)

                # Signal classification
                if hybrid_score >= 70:
                    signal = "bullish"
                elif hybrid_score <= 40:
                    signal = "bearish"
                else:
                    signal = "neutral"

                results[ticker] = {
                    "success": True,
                    "ticker": ticker,
                    "technical_rating": technical_rating,
                    "sentiment_rating": sentiment_rating,
                    "hybrid_score": hybrid_score,
                    "signal": signal,
                    "price": quote.get("price"),
                    "company_name": quote.get("company", {}).get("name", ticker),
                    "mentions": psych.get("mentions", 0),
                    "velocity": psych.get("velocity", "steady"),
                }

                logger.debug(
                    f"  {ticker}: Hybrid {hybrid_score} = Tech {technical_rating} + "
                    f"Sent {sentiment_rating} → {signal}"
                )

            except Exception as e:
                logger.error(f"Failed hybrid scoring for {ticker}: {e}")
                results[ticker] = {"success": False, "error": str(e)}

        success_count = sum(1 for r in results.values() if r.get("success"))

        return {
            "results": results,
            "summary": {
                "total": len(self.tickers),
                "succeeded": success_count,
                "failed": len(self.tickers) - success_count,
            },
        }

    async def _stage_persist(self, hybrid_results: Dict) -> Dict[str, Any]:
        """Stage 5: Save results to database with idempotency."""
        saved_count = 0
        updated_count = 0
        failed_count = 0

        hybrid_data = hybrid_results.get("results", {})

        async with async_session() as session:
            for ticker, data in hybrid_data.items():
                if not data.get("success"):
                    failed_count += 1
                    continue

                try:
                    # Check if signal already exists for today (idempotency)
                    today = datetime.utcnow().date()
                    existing = await session.execute(
                        select(HybridSignal).where(
                            and_(
                                HybridSignal.ticker == ticker,
                                HybridSignal.created_at >= datetime.combine(
                                    today, datetime.min.time()
                                ),
                            )
                        )
                    )
                    existing_signal = existing.scalar_one_or_none()

                    if existing_signal:
                        # Update existing signal
                        existing_signal.signal = data.get("signal", "neutral").upper()
                        existing_signal.confidence = min(data.get("hybrid_score", 50) / 100, 1.0)
                        existing_signal.reason = f"Hybrid Score: {data.get('hybrid_score')} (Tech: {data.get('technical_rating')}, Sent: {data.get('sentiment_rating')})"
                        existing_signal.reason_short = f"{data.get('signal', 'neutral').title()} - Score {data.get('hybrid_score')}"
                        updated_count += 1
                        logger.debug(f"  Updated {ticker}")
                    else:
                        # Create new signal (Note: using minimal fields that match HybridSignal model)
                        # The actual model has different fields, so we store what we can
                        new_signal = HybridSignal(
                            ticker=ticker,
                            date=datetime.utcnow().date(),
                            signal=data.get("signal", "neutral").upper(),
                            confidence=min(data.get("hybrid_score", 50) / 100, 1.0),
                            reason=f"Hybrid Score: {data.get('hybrid_score')} (Tech: {data.get('technical_rating')}, Sent: {data.get('sentiment_rating')})",
                            reason_short=f"{data.get('signal', 'neutral').title()} - Score {data.get('hybrid_score')}",
                        )
                        session.add(new_signal)
                        saved_count += 1
                        logger.debug(f"  Created {ticker}")

                except Exception as e:
                    logger.error(f"Failed to persist {ticker}: {e}")
                    failed_count += 1

            # Commit all changes
            await session.commit()

        logger.info(
            f"  💾 Persisted: {saved_count} new, {updated_count} updated, {failed_count} failed"
        )

        return {
            "saved": saved_count,
            "updated": updated_count,
            "failed": failed_count,
            "total": saved_count + updated_count,
        }


class SchedulerConfig:
    """Configuration for batch scheduler."""

    # Schedule times (24-hour format)
    SCHEDULE_TIMES = [
        {"hour": 6, "minute": 0, "name": "pre-market"},
        {"hour": 12, "minute": 0, "name": "intraday"},
        {"hour": 18, "minute": 0, "name": "post-market"},
        {"hour": 0, "minute": 0, "name": "midnight"},
    ]

    # Default watchlist tickers (matches SEED_TICKERS from seed_database.py)
    DEFAULT_TICKERS = [
        "AAPL", "MSFT", "GOOGL", "AMZN", "NVDA",
        "TSLA", "META", "JPM", "V", "JNJ",
        "WMT", "PG", "DIS", "NFLX", "COIN"
    ]


async def run_scheduled_batch(tickers: Optional[List[str]] = None):
    """
    Run a single batch execution.

    Args:
        tickers: List of tickers to analyze (defaults to DEFAULT_TICKERS)
    """
    if tickers is None:
        tickers = SchedulerConfig.DEFAULT_TICKERS

    orchestrator = BatchOrchestrator(tickers)
    results = await orchestrator.run_full_pipeline()

    # Log summary
    if results.get("status") == "success":
        logger.info("="*60)
        logger.info(f"✅ Batch completed: {results['tickers_succeeded']}/{results['tickers_processed']} succeeded")
        logger.info(f"⏱️  Duration: {results['duration_seconds']:.2f}s")
        logger.info("="*60)
    else:
        logger.error(f"❌ Batch failed: {results.get('error')}")

    return results


async def scheduler_loop():
    """
    Main scheduler loop - runs batches at scheduled times.

    Runs forever, checking every minute if it's time to execute a batch.
    """
    logger.info("🕐 Batch scheduler started")
    logger.info(f"   Schedule: {', '.join([s['name'] for s in SchedulerConfig.SCHEDULE_TIMES])}")

    last_run_date = None

    while True:
        now = datetime.now()
        current_hour = now.hour
        current_minute = now.minute
        current_date = now.date()

        # Check if we should run a batch
        for schedule in SchedulerConfig.SCHEDULE_TIMES:
            if current_hour == schedule["hour"] and current_minute == schedule["minute"]:
                # Prevent duplicate runs within the same minute
                if last_run_date == (current_date, current_hour, current_minute):
                    break

                logger.info(f"\n⏰ Triggered: {schedule['name']} batch at {now.strftime('%Y-%m-%d %H:%M')}")

                try:
                    await run_scheduled_batch()
                    last_run_date = (current_date, current_hour, current_minute)
                except Exception as e:
                    logger.error(f"Failed to run {schedule['name']} batch: {e}", exc_info=True)
                    # TODO: Send alert notification

                break

        # Sleep for 60 seconds before next check
        await asyncio.sleep(60)


# CLI Entry Point
if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    # Run scheduler loop
    asyncio.run(scheduler_loop())
