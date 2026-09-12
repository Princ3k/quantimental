"""
Live Signal Service

The single place a live signal is built. Every API route that returns a signal
calls into here, so the dashboard, the single-ticker analyzer and the batch
endpoints can never disagree about how a score was produced.

Two depths are available:

- ``DEPTH_FAST`` — price and technicals only. Used by the dashboard, where a
  dozen tickers load at once. Sentiment is reported as *unavailable* and the
  hybrid score falls back to technicals alone.
- ``DEPTH_FULL`` — adds the ML sentiment pipeline (Reddit, news, Twitter).
  Slower and subject to third-party rate limits, so it is reserved for
  explicit single-ticker analysis.

The important rule, in both depths: **nothing is invented**. The previous
implementation filled missing sentiment with `random.randint(65, 85)` scaled off
trading volume, and jittered confidence by +/-10 on every call. A stock with no
coverage now says it has no coverage, and identical inputs always produce an
identical result.
"""

from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timezone
from typing import Any, Optional

from app.engines.hybrid import HybridEngine, hybrid_engine
from app.engines.quant import quant_engine
from app.services.data.market_data_service import market_data_service

logger = logging.getLogger(__name__)

DEPTH_FAST = "fast"
DEPTH_FULL = "full"

# When sentiment is unavailable the hybrid score is technicals-only rather than
# technicals blended against a fabricated neutral 50, which would drag every
# score toward the middle and mute real signals.
_TECHNICAL_ONLY = HybridEngine(technical_weight=1.0, sentiment_weight=0.0)

# How long a single ticker's sentiment fetch may take before we give up and
# fall back to technicals. Reddit and news APIs are the slowest dependency and
# should never hold a request open indefinitely.
SENTIMENT_TIMEOUT_SECONDS = 20.0


class LiveSignalService:
    """Builds live signals by composing the Quant, Psych and Hybrid engines."""

    def __init__(self, sentiment_service: Optional[Any] = None) -> None:
        # Injected lazily: importing the sentiment stack pulls in transformers
        # and torch, which is expensive and unnecessary for fast-depth requests.
        self._sentiment_service = sentiment_service
        self._sentiment_init_failed = False

    def _get_sentiment_service(self) -> Optional[Any]:
        """Load the sentiment service on first use, tolerating absence."""
        if self._sentiment_service is not None:
            return self._sentiment_service
        if self._sentiment_init_failed:
            return None
        try:
            from app.services.data.real_time_sentiment_service import RealTimeSentimentService

            self._sentiment_service = RealTimeSentimentService()
        except Exception as exc:
            # Missing API keys or ML dependencies must degrade the product, not
            # break it: technical analysis still works perfectly well alone.
            logger.warning("Sentiment service unavailable, continuing without it: %s", exc)
            self._sentiment_init_failed = True
            return None
        return self._sentiment_service

    async def generate(self, ticker: str, depth: str = DEPTH_FAST) -> dict[str, Any]:
        """
        Build a complete signal for one ticker.

        Returns a dict shaped for the API. When market data is unavailable the
        result has ``available: False`` and an explanatory ``reason``; it never
        contains invented prices or ratings.
        """
        symbol = ticker.upper().strip()

        # yfinance is synchronous and network-bound, so keep it off the event loop.
        quote = await asyncio.to_thread(market_data_service.get_quote, symbol)

        if not quote.get("available"):
            return {
                "ticker": symbol,
                "available": False,
                "reason": quote.get("reason", f"No market data available for {symbol}."),
                "analyzed_at": datetime.now(timezone.utc).isoformat(),
            }

        indicators = quote["indicators"]

        # The raw rating is a weighted blend that clusters near the middle, so
        # scoring on it directly makes most of the scale unreachable. The
        # percentile of the measured distribution is what gets scored; the raw
        # value is carried through for transparency.
        technical_raw = quant_engine.calculate_technical_rating(indicators)
        technical_rating = quant_engine.strength_percentile(technical_raw)
        technical_notes = quant_engine.explain(indicators)

        sentiment = await self._get_sentiment(symbol, depth)

        if sentiment["available"]:
            engine = hybrid_engine
            sentiment_rating = sentiment["rating"]
        else:
            engine = _TECHNICAL_ONLY
            # Passed through only so confidence can see it; with a zero weight
            # it cannot influence the score itself.
            sentiment_rating = technical_rating

        verdict = engine.synthesize(
            technical_rating=technical_rating,
            sentiment_rating=sentiment_rating,
            technical_indicators=indicators,
            sentiment_data=sentiment,
        )

        return self._assemble(symbol, quote, indicators, technical_rating,
                              technical_raw, technical_notes, sentiment, verdict, depth)

    async def _get_sentiment(self, symbol: str, depth: str) -> dict[str, Any]:
        """
        Fetch sentiment, or return an explicit 'unavailable' record.

        Fast depth never attempts the fetch. Full depth attempts it but treats
        timeouts and failures as "no data" rather than as an error, because a
        technically-grounded signal is still worth returning.
        """
        unavailable = {
            "available": False,
            "rating": None,
            "mentions": 0,
            "mention_velocity": "unknown",
            "reddit_buzz": 0,
            "twitter_buzz": 0,
            "reason": (
                "Sentiment is only gathered for detailed single-stock analysis."
                if depth == DEPTH_FAST
                else "No recent news or social posts were found for this stock."
            ),
        }

        if depth != DEPTH_FULL:
            return unavailable

        service = self._get_sentiment_service()
        if service is None:
            unavailable["reason"] = "Sentiment analysis is not configured on this server."
            return unavailable

        try:
            data = await asyncio.wait_for(
                service.get_sentiment_for_ticker(symbol),
                timeout=SENTIMENT_TIMEOUT_SECONDS,
            )
        except asyncio.TimeoutError:
            logger.warning("Sentiment fetch timed out for %s", symbol)
            unavailable["reason"] = "Sentiment sources did not respond in time."
            return unavailable
        except Exception as exc:
            logger.warning("Sentiment fetch failed for %s: %s", symbol, exc)
            return unavailable

        mentions = data.get("mentions", 0)
        if not mentions:
            # Zero mentions means the sources returned nothing, not that the
            # market is neutral. Reporting 50/100 here would be a fabrication.
            return unavailable

        return {
            "available": True,
            "rating": int(data.get("sentiment_rating", 50)),
            "mentions": mentions,
            "mention_velocity": data.get("mention_velocity", "steady"),
            "reddit_buzz": data.get("reddit_buzz", 0),
            "twitter_buzz": data.get("twitter_buzz", 0),
            "breakdown": data.get("breakdown", {}),
            "reason": None,
        }

    @staticmethod
    def _assemble(
        symbol: str,
        quote: dict[str, Any],
        indicators: dict[str, Any],
        technical_rating: int,
        technical_raw: int,
        technical_notes: list[str],
        sentiment: dict[str, Any],
        verdict: dict[str, Any],
        depth: str,
    ) -> dict[str, Any]:
        """Shape engine output into the JSON contract the frontend consumes."""
        price = quote["price"]
        previous_close = quote.get("previous_close")

        # Day-over-day change, which is what a price ticker conventionally shows.
        if previous_close:
            change = price - previous_close
            change_percent = change / previous_close * 100.0
        else:
            change = 0.0
            change_percent = 0.0

        sources = ["yahoo_finance"]
        if sentiment["available"]:
            sources += ["reddit", "marketaux", "twitter"]

        return {
            "ticker": symbol,
            "available": True,
            "company_name": quote["company"].get("name", symbol),
            "sector": quote["company"].get("sector"),
            "price": round(price, 2),
            "change": round(change, 2),
            "change_percent": round(change_percent, 2),
            "price_history": quote.get("price_history", []),
            "signal": verdict["signal"],
            "hybrid_score": verdict["hybrid_score"],
            "technical_rating": technical_rating,
            "technical_raw": technical_raw,
            "sentiment_rating": sentiment["rating"],
            "recommendation": {
                "action": verdict["recommendation"],
                "label": verdict["label"],
                "confidence": verdict["confidence"],
                "summary": verdict["plain_summary"],
                "reasons": verdict["reasons"] + technical_notes,
                "pattern": verdict["pattern"],
            },
            "technical_analysis": {
                "trend": indicators["trend"],
                "rsi": round(indicators["rsi"], 1),
                # Pre-worded so the UI never re-derives its own bands.
                "momentum": quant_engine.describe_momentum(indicators["rsi"]),
                "volatility": indicators["volatility"],
                "macd": round(indicators["macd"], 3),
                "macd_signal": round(indicators["macd_signal"], 3),
                "macd_histogram": round(indicators["macd_histogram"], 3),
                "stochastic_k": round(indicators["stochastic_k"], 1),
                "adx": round(indicators["adx"], 1),
                "bollinger_upper": round(indicators["bollinger_upper"], 2),
                "bollinger_lower": round(indicators["bollinger_lower"], 2),
                "sma_20": round(indicators["sma_20"], 2),
                "sma_50": round(indicators["sma_50"], 2),
                "sma_200": round(indicators["sma_200"], 2) if indicators["sma_200"] else None,
                "golden_cross": indicators["golden_cross"],
                "death_cross": indicators["death_cross"],
                "avg_volume": indicators["avg_volume"],
                "price_change_10d": indicators["price_change_10d"],
                "notes": technical_notes,
            },
            "sentiment_analysis": {
                "available": sentiment["available"],
                "rating": sentiment["rating"],
                "mentions": sentiment["mentions"],
                "mention_velocity": sentiment["mention_velocity"],
                "reddit_buzz": sentiment["reddit_buzz"],
                "twitter_buzz": sentiment["twitter_buzz"],
                "reason": sentiment.get("reason"),
            },
            "weights": verdict["weights"],
            "metadata": {
                "analyzed_at": datetime.now(timezone.utc).isoformat(),
                "depth": depth,
                "data_sources": sources,
                "data_quality": indicators.get("data_quality", {}),
            },
        }

    async def generate_many(
        self,
        tickers: list[str],
        depth: str = DEPTH_FAST,
    ) -> tuple[list[dict[str, Any]], list[dict[str, str]]]:
        """
        Build signals for several tickers concurrently.

        Returns (signals, failures). A ticker that cannot be priced lands in
        `failures` with a reason rather than silently vanishing or being
        replaced by mock data.
        """
        symbols = [t.upper().strip() for t in tickers if t and t.strip()]
        if not symbols:
            return [], []

        results = await asyncio.gather(
            *(self.generate(symbol, depth) for symbol in symbols),
            return_exceptions=True,
        )

        signals: list[dict[str, Any]] = []
        failures: list[dict[str, str]] = []

        for symbol, result in zip(symbols, results):
            if isinstance(result, Exception):
                logger.error("Failed to analyze %s: %s", symbol, result, exc_info=result)
                failures.append({"ticker": symbol, "reason": "Analysis failed unexpectedly."})
            elif not result.get("available"):
                failures.append({"ticker": symbol, "reason": result.get("reason", "Unavailable.")})
            else:
                signals.append(result)

        return signals, failures


live_signal_service = LiveSignalService()
