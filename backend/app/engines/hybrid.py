"""
Hybrid Engine — "So what should I actually do?"

Combines the technical rating (what the math says) and the sentiment rating
(what the crowd feels) into one recommendation, a confidence figure, and an
explanation a first-time investor can follow.

Design notes
------------
- Confidence is *derived*, never random. It starts from a base and moves on
  evidence: agreement between the two engines raises it, disagreement and thin
  data lower it. An earlier version added `random.randint(-10, 10)` to the
  score, which meant the same inputs produced a different confidence on every
  refresh. In a tool people might act on, that is indefensible.
- Every recommendation carries a `plain_summary`: one sentence, no jargon,
  stating what the signal is and the single biggest reason for it.
"""

from __future__ import annotations

import logging
from enum import Enum
from typing import Any, Optional

logger = logging.getLogger(__name__)


class SignalType(str, Enum):
    """Trading signal types, from most bullish to most bearish."""

    STRONG_BUY = "strong_buy"
    BUY = "buy"
    HOLD = "hold"
    SELL = "sell"
    STRONG_SELL = "strong_sell"


# Human-readable labels, used directly by the UI so wording stays consistent.
SIGNAL_LABELS: dict[str, str] = {
    "strong_buy": "Strong Buy",
    "buy": "Buy",
    "hold": "Hold",
    "sell": "Sell",
    "strong_sell": "Strong Sell",
}

SIGNAL_MEANINGS: dict[str, str] = {
    "strong_buy": "Both the price trend and the market mood look clearly positive right now.",
    "buy": "The overall picture leans positive, with some caveats.",
    "hold": "The signals are mixed or quiet — there is no clear edge either way today.",
    "sell": "The overall picture leans negative, with some caveats.",
    "strong_sell": "Both the price trend and the market mood look clearly negative right now.",
}


class HybridEngine:
    """Combines technical and sentiment ratings into a single recommendation."""

    def __init__(self, technical_weight: float = 0.45, sentiment_weight: float = 0.55) -> None:
        total = technical_weight + sentiment_weight
        if total <= 0:
            raise ValueError("Weights must sum to a positive number")
        if abs(total - 1.0) > 0.01:
            logger.warning("Weights sum to %.2f, normalising to 1.0", total)
        self.technical_weight = technical_weight / total
        self.sentiment_weight = sentiment_weight / total

    def synthesize(
        self,
        technical_rating: int,
        sentiment_rating: int,
        technical_indicators: Optional[dict[str, Any]] = None,
        sentiment_data: Optional[dict[str, Any]] = None,
    ) -> dict[str, Any]:
        """
        Combine both ratings into a recommendation.

        Args:
            technical_rating: 0-100 from the Quant Engine.
            sentiment_rating: 0-100 from the Psych Engine.
            technical_indicators: Raw indicator dict, used for explanations.
            sentiment_data: Sentiment detail (mentions, velocity, coverage).

        Returns:
            Dict with hybrid_score, signal, recommendation, confidence,
            reasons, plain_summary, pattern and weights.
        """
        hybrid_score = int(
            round(
                technical_rating * self.technical_weight
                + sentiment_rating * self.sentiment_weight
            )
        )
        hybrid_score = max(0, min(100, hybrid_score))

        if hybrid_score >= 70:
            signal = "bullish"
        elif hybrid_score <= 40:
            signal = "bearish"
        else:
            signal = "neutral"

        recommendation = self._classify(hybrid_score)

        # When sentiment could not be gathered, `sentiment_rating` is a stand-in
        # for the technical rating so the weighted sum still works. It must not
        # then be read as independent corroboration, so comparisons between the
        # two engines are suppressed entirely.
        has_sentiment = bool(sentiment_data and sentiment_data.get("available"))

        confidence = self._calculate_confidence(
            technical_rating, sentiment_rating, technical_indicators, sentiment_data, has_sentiment
        )

        pattern = (
            self.detect_pattern(technical_rating, sentiment_rating, technical_indicators)
            if has_sentiment
            else None
        )

        reasons = self._build_reasons(
            technical_rating, sentiment_rating, pattern, sentiment_data, has_sentiment
        )

        return {
            "hybrid_score": hybrid_score,
            "signal": signal,
            "recommendation": recommendation.value,
            "label": SIGNAL_LABELS[recommendation.value],
            "confidence": confidence,
            "reasons": reasons,
            "plain_summary": self._plain_summary(recommendation, reasons),
            "pattern": pattern,
            "weights": {
                "technical": round(self.technical_weight, 2),
                "sentiment": round(self.sentiment_weight, 2),
            },
        }

    @staticmethod
    def _classify(hybrid_score: int) -> SignalType:
        """Map a 0-100 score onto a five-point recommendation scale."""
        if hybrid_score >= 80:
            return SignalType.STRONG_BUY
        if hybrid_score >= 65:
            return SignalType.BUY
        if hybrid_score >= 40:
            return SignalType.HOLD
        if hybrid_score >= 25:
            return SignalType.SELL
        return SignalType.STRONG_SELL

    def _calculate_confidence(
        self,
        technical_rating: int,
        sentiment_rating: int,
        indicators: Optional[dict[str, Any]],
        sentiment_data: Optional[dict[str, Any]],
        has_sentiment: bool = True,
    ) -> int:
        """
        Derive a 0-95 confidence figure from how much the evidence agrees.

        Capped at 95 deliberately: no market signal deserves to be presented
        as a certainty.
        """
        confidence = 50.0

        if has_sentiment:
            # Agreement between two independent engines is the strongest
            # evidence available. Only meaningful when sentiment is real.
            divergence = abs(technical_rating - sentiment_rating)
            if divergence < 10:
                confidence += 20
            elif divergence < 20:
                confidence += 12
            elif divergence > 40:
                confidence -= 15
            elif divergence > 30:
                confidence -= 8
            conviction = abs((technical_rating + sentiment_rating) / 2 - 50)
        else:
            # Half the evidence is missing, so a technicals-only reading starts
            # from a lower ceiling no matter how clean the chart looks.
            confidence -= 10
            conviction = abs(technical_rating - 50)

        # A decisive reading in either direction is more actionable than a
        # score parked in the middle.
        confidence += min(15.0, conviction * 0.4)

        if indicators:
            # A confirmed trend is more trustworthy than a choppy tape.
            adx = indicators.get("adx", 25.0)
            if adx > 40:
                confidence += 8
            elif adx < 20:
                confidence -= 8

            # High volatility widens the range of plausible outcomes.
            if indicators.get("volatility") == "high":
                confidence -= 7

            quality = indicators.get("data_quality") or {}
            if quality.get("sufficient") is False:
                confidence -= 25
            elif not quality.get("has_sma_200", True):
                confidence -= 5

        # Coverage depth only matters when sentiment was actually gathered.
        # Absence was already priced in above; penalising it again here would
        # charge the same missing evidence two or three times over.
        if has_sentiment and sentiment_data:
            # Sentiment computed from a handful of posts is noise, not signal.
            mentions = sentiment_data.get("mentions", 0)
            if mentions < 10:
                confidence -= 8
            elif mentions > 100:
                confidence += 5

        return int(max(5, min(95, round(confidence))))

    def detect_pattern(
        self,
        technical_rating: int,
        sentiment_rating: int,
        indicators: Optional[dict[str, Any]] = None,
    ) -> Optional[dict[str, str]]:
        """
        Detect a recognisable setup worth calling out by name.

        Returns a dict with `id`, `name` and a plain-English `description`,
        or None when nothing notable is happening.
        """
        if not indicators:
            return None

        rsi = indicators.get("rsi", 50.0)

        if rsi > 70 and sentiment_rating > 75:
            return {
                "id": "blow_off_top",
                "name": "Crowded trade",
                "description": (
                    "The price has run hard and the crowd is very excited. "
                    "That combination has historically preceded pullbacks more often than not."
                ),
            }
        if rsi < 30 and sentiment_rating < 40:
            return {
                "id": "capitulation",
                "name": "Everyone has given up",
                "description": (
                    "The price has fallen hard and sentiment is bleak. "
                    "Bottoms often form when there is nobody left to sell."
                ),
            }
        if rsi > 70 and sentiment_rating < 40:
            return {
                "id": "bearish_divergence",
                "name": "Price up, mood down",
                "description": (
                    "The price is climbing but the conversation around it is negative. "
                    "Rallies without support from sentiment tend to be fragile."
                ),
            }
        if technical_rating > 65 and sentiment_rating > 65:
            return {
                "id": "confirmation_bullish",
                "name": "Everything agrees — positive",
                "description": "The price trend and the market mood are both pointing the same way, upward.",
            }
        if technical_rating < 35 and sentiment_rating < 35:
            return {
                "id": "confirmation_bearish",
                "name": "Everything agrees — negative",
                "description": "The price trend and the market mood are both pointing the same way, downward.",
            }
        return None

    @staticmethod
    def _build_reasons(
        technical_rating: int,
        sentiment_rating: int,
        pattern: Optional[dict[str, str]],
        sentiment_data: Optional[dict[str, Any]],
        has_sentiment: bool = True,
    ) -> list[str]:
        """Assemble the cross-engine observations, most important first."""
        reasons: list[str] = []

        if pattern:
            reasons.append(pattern["description"])

        if has_sentiment:
            divergence = abs(technical_rating - sentiment_rating)
            if divergence > 30:
                if technical_rating > sentiment_rating:
                    reasons.append(
                        "The numbers look better than the mood — the chart is healthier "
                        "than the conversation around this stock."
                    )
                else:
                    reasons.append(
                        "The mood looks better than the numbers — people are upbeat, "
                        "but the chart has not confirmed it yet."
                    )
            elif divergence < 10:
                reasons.append("The chart and the market mood are telling the same story.")

        if sentiment_data:
            if sentiment_data.get("available") is False:
                reasons.append(
                    "No recent news or social coverage was available, so this reading "
                    "is based on price action alone."
                )
            else:
                mentions = sentiment_data.get("mentions", 0)
                velocity = sentiment_data.get("mention_velocity", "steady")
                if mentions == 0:
                    reasons.append("Nobody is talking about this stock right now.")
                elif velocity == "rising":
                    reasons.append(f"Attention is picking up ({mentions:,} recent mentions).")
                elif velocity == "falling":
                    reasons.append(f"Attention is fading ({mentions:,} recent mentions).")
                elif mentions > 100:
                    reasons.append(f"Steady, heavy discussion ({mentions:,} recent mentions).")

        return reasons

    @staticmethod
    def _plain_summary(recommendation: SignalType, reasons: list[str]) -> str:
        """One jargon-free sentence: what the signal is, and why."""
        meaning = SIGNAL_MEANINGS[recommendation.value]
        if reasons:
            return f"{meaning} {reasons[0]}"
        return meaning


hybrid_engine = HybridEngine(technical_weight=0.45, sentiment_weight=0.55)
