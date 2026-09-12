"""
Quant Engine — "What does the math say?"

Turns raw OHLCV bars into technical indicators and a single 0-100 technical
rating, plus the plain-English observations that justify it.

This is the only place technical scoring lives. The API routes call into it
rather than recomputing indicators inline, so the numbers shown on a stock card
and the numbers used to generate a signal can never drift apart.
"""

from __future__ import annotations

import logging
from typing import Any, Optional

import numpy as np

from app.engines import indicators as ta

logger = logging.getLogger(__name__)

# Indicators need history to warm up. ADX(14) alone consumes ~28 bars before it
# produces a value, and SMA-200 needs 200. Below this we degrade rather than lie.
MIN_BARS = 60
BARS_FOR_LONG_MA = 200

# Conventional ADX band: above 25 a market is trending strongly enough for the
# direction to be worth acting on. Used only to qualify a trend as "strong".
TRENDING_ADX = 25.0

# How far the 20-day average must travel over 20 sessions, as a percentage of
# price, before the move counts as a trend rather than drift. Measured
# empirically: a range-bound stock stays inside +/-0.5%, while a genuine trend
# runs to 3% and beyond.
TREND_SLOPE_PCT = 1.0
STRONG_TREND_SLOPE_PCT = 2.5

# Sessions over which the slope is measured.
SLOPE_WINDOW = 20


# ---------------------------------------------------------------------------
# Rating calibration
#
# The raw technical rating is a weighted average of six bounded components, and
# averaging bounded components concentrates the result near the middle. Measured
# across 11,472 readings spanning 48 instruments and five years (2021-2026), it
# never left 41-79, with mean 58.7 and standard deviation 6.5.
#
# That made three of the five verdicts unreachable: the thresholds for
# strong_sell, sell and strong_buy sat outside the range the rating can occupy,
# so the engine emitted only "hold" (80.5%) and "buy" (19.5%) — and could never
# tell anyone to sell.
#
# Mapping the raw rating through its own empirical distribution fixes that. A
# percentile is uniform by construction, so every band is reachable and each one
# means something statable: "stronger than 85% of readings we have measured".
#
# The trade-off is that this is *relative*, not absolute. In a falling market
# the best available reading still lands in the top percentile, so a high score
# means "better than most right now", never "good in absolute terms". The UI
# has to say so.
# ---------------------------------------------------------------------------

# (raw rating, percentile) pairs from the measured distribution.
RATING_DISTRIBUTION: tuple[tuple[float, float], ...] = (
    (41.0, 0.0),
    (46.0, 1.0),
    (48.0, 5.0),
    (50.0, 10.0),
    (53.0, 20.0),
    (55.0, 30.0),
    (57.0, 40.0),
    (58.0, 50.0),
    (60.0, 60.0),
    (62.0, 70.0),
    (64.0, 80.0),
    (68.0, 90.0),
    (69.0, 95.0),
    (73.0, 99.0),
    (79.0, 100.0),
)


def rating_to_percentile(rating: float) -> float:
    """
    Map a raw technical rating onto its percentile in the measured distribution.

    Linear interpolation between breakpoints; clamped at both ends so a reading
    outside the observed range saturates rather than extrapolating into nonsense.
    """
    points = RATING_DISTRIBUTION
    if rating <= points[0][0]:
        return 0.0
    if rating >= points[-1][0]:
        return 100.0

    for (low_rating, low_pct), (high_rating, high_pct) in zip(points, points[1:]):
        if low_rating <= rating <= high_rating:
            span = high_rating - low_rating
            if span <= 0:
                return low_pct
            position = (rating - low_rating) / span
            return low_pct + position * (high_pct - low_pct)

    return 50.0


class QuantEngine:
    """Calculates technical indicators and a technical rating from price data."""

    def calculate_indicators(
        self,
        closes: np.ndarray,
        highs: Optional[np.ndarray] = None,
        lows: Optional[np.ndarray] = None,
        volumes: Optional[np.ndarray] = None,
    ) -> dict[str, Any]:
        """
        Calculate all technical indicators from price arrays.

        Args:
            closes: Closing prices, oldest first.
            highs/lows: Intraday extremes. Fall back to closes when absent,
                which makes range-based indicators (Stochastic, ATR, ADX)
                conservative rather than wrong.
            volumes: Share volumes, used only for the average-volume field.

        Returns:
            Dict of indicators. `data_quality` reports how much history backed
            the result so callers can decide how much to trust it.
        """
        closes = np.asarray(closes, dtype=float)
        n = len(closes)

        if n < MIN_BARS:
            logger.warning("Insufficient price history: %d bars (need %d)", n, MIN_BARS)
            return self._insufficient_data(closes)

        has_range = highs is not None and lows is not None
        highs = np.asarray(highs, dtype=float) if highs is not None else closes
        lows = np.asarray(lows, dtype=float) if lows is not None else closes
        volumes = np.asarray(volumes, dtype=float) if volumes is not None else np.zeros(n)

        price = float(closes[-1])
        results: dict[str, Any] = {"price": price, "bars": n}

        results["rsi"] = self._last(ta.rsi(closes, 14), 50.0)

        sma_20 = ta.sma(closes, 20)
        sma_50 = ta.sma(closes, 50)
        results["sma_20"] = self._last(sma_20, price)
        results["sma_50"] = self._last(sma_50, price)

        # SMA-200 is only meaningful with 200 bars behind it. Report None rather
        # than silently substituting SMA-50, which would make every long-term
        # trend read as "price vs 50-day" while claiming to be the 200-day.
        has_long_ma = n >= BARS_FOR_LONG_MA
        sma_200 = ta.sma(closes, 200) if has_long_ma else None
        results["sma_200"] = self._last(sma_200, price) if has_long_ma else None

        macd_line, macd_signal, macd_hist = ta.macd(closes)
        results["macd"] = self._last(macd_line, 0.0)
        results["macd_signal"] = self._last(macd_signal, 0.0)
        results["macd_histogram"] = self._last(macd_hist, 0.0)

        upper, middle, lower = ta.bollinger_bands(closes, 20, 2.0)
        results["bollinger_upper"] = self._last(upper, price)
        results["bollinger_middle"] = self._last(middle, price)
        results["bollinger_lower"] = self._last(lower, price)

        slow_k, slow_d = ta.stochastic(highs, lows, closes)
        results["stochastic_k"] = self._last(slow_k, 50.0)
        results["stochastic_d"] = self._last(slow_d, 50.0)

        atr_value = self._last(ta.atr(highs, lows, closes, 14), 0.0)
        results["atr"] = atr_value
        results["atr_percent"] = (atr_value / price * 100.0) if price > 0 else 0.0

        results["adx"] = self._last(ta.adx(highs, lows, closes, 14), 25.0)

        results["avg_volume"] = int(volumes.mean()) if volumes.size and volumes.any() else 0

        # 10-day price change, used for the headline "change" figure.
        if n >= 11 and closes[-11] > 0:
            results["price_change_10d"] = round((price - closes[-11]) / closes[-11] * 100.0, 2)
        else:
            results["price_change_10d"] = 0.0

        results["trend"] = self._detect_trend(closes, sma_20, results)
        results["volatility"] = self._classify_volatility(results["atr_percent"])

        results.update(self._detect_ma_cross(sma_50, sma_200))

        results["support"] = results["bollinger_lower"]
        results["resistance"] = results["bollinger_upper"]

        results["data_quality"] = {
            "bars": n,
            "sufficient": True,
            "has_sma_200": has_long_ma,
            "has_intraday_range": has_range,
        }
        return results

    @staticmethod
    def _last(series: Optional[np.ndarray], fallback: float) -> float:
        """Read the most recent non-NaN value, falling back when unavailable."""
        if series is None or len(series) == 0:
            return fallback
        value = series[-1]
        return float(value) if not np.isnan(value) else fallback

    def _detect_trend(
        self,
        closes: np.ndarray,
        sma_20: np.ndarray,
        ind: dict[str, Any],
    ) -> str:
        """
        Classify trend as strong_uptrend / uptrend / sideways / downtrend /
        strong_downtrend.

        Direction is taken from the *slope of the 20-day average* over the last
        20 sessions, expressed as a percentage of price. That single measure is
        what separates a real trend from noise: a range-bound stock's moving
        average barely moves (empirically within +/-0.5%), while a genuine trend
        drags it several percent.

        Earlier versions combined spot checks — price vs its moving averages,
        MACD sign, 10-day change — and treated agreement between them as
        evidence. Those checks are not independent: they all ask a version of
        "is price above its recent average", so on a flat stock they agree by
        chance about half the time and manufactured an "uptrend" out of noise.

        ADX is used only to qualify an already-established trend as strong. It
        cannot veto one, because a smooth, persistent drift produces a *low*
        ADX by construction.
        """
        price = closes[-1] if len(closes) else 0.0
        if price <= 0 or len(sma_20) <= SLOPE_WINDOW:
            return "sideways"

        latest, earlier = sma_20[-1], sma_20[-(SLOPE_WINDOW + 1)]
        if np.isnan(latest) or np.isnan(earlier):
            return "sideways"

        slope_pct = (latest - earlier) / price * 100.0

        if abs(slope_pct) < TREND_SLOPE_PCT:
            return "sideways"

        confirmed = ind["adx"] > TRENDING_ADX

        if slope_pct > 0:
            if confirmed and slope_pct > STRONG_TREND_SLOPE_PCT:
                return "strong_uptrend"
            return "uptrend"

        if confirmed and slope_pct < -STRONG_TREND_SLOPE_PCT:
            return "strong_downtrend"
        return "downtrend"

    @staticmethod
    def _classify_volatility(atr_percent: float) -> str:
        """Bucket ATR-as-percent-of-price into a human-readable band."""
        if atr_percent > 3.0:
            return "high"
        if atr_percent > 1.5:
            return "moderate"
        return "low"

    @staticmethod
    def _detect_ma_cross(
        sma_50: np.ndarray,
        sma_200: Optional[np.ndarray],
    ) -> dict[str, bool]:
        """
        Detect a Golden Cross (50 crossing above 200) or Death Cross (below).

        Looks across the last 5 sessions rather than only the latest bar — a
        cross that happened three days ago is still the relevant market event,
        and checking a single bar means the signal is visible for one day only.
        """
        no_cross = {"golden_cross": False, "death_cross": False}
        if sma_200 is None or len(sma_50) < 6:
            return no_cross

        window = 5
        recent_50, recent_200 = sma_50[-(window + 1):], sma_200[-(window + 1):]
        if np.isnan(recent_50).any() or np.isnan(recent_200).any():
            return no_cross

        above = recent_50 > recent_200
        if not above[0] and above[-1]:
            return {"golden_cross": True, "death_cross": False}
        if above[0] and not above[-1]:
            return {"golden_cross": False, "death_cross": True}
        return no_cross

    def calculate_technical_rating(self, ind: dict[str, Any]) -> int:
        """
        Combine indicators into a single 0-100 technical rating.

        Higher is more constructive. Each component is scored 0-100 on its own
        terms, then weighted. Weights favour momentum and trend (50% combined)
        because those are the most persistent signals at a daily timeframe.
        """
        price = ind.get("price", 0.0)

        # RSI: healthiest mid-range, penalised at both extremes.
        rsi_value = ind.get("rsi", 50.0)
        rsi_score = 100.0 - abs(rsi_value - 50.0) * 2.0

        trend_score = {
            "strong_uptrend": 90.0,
            "uptrend": 75.0,
            "sideways": 50.0,
            "downtrend": 35.0,
            "strong_downtrend": 20.0,
        }.get(ind.get("trend", "sideways"), 50.0)

        macd_score = 70.0 if ind.get("macd", 0.0) > ind.get("macd_signal", 0.0) else 30.0

        # Stochastic: oversold implies room to bounce, overbought room to fall.
        stoch = ind.get("stochastic_k", 50.0)
        if stoch < 20:
            stoch_score = 80.0
        elif stoch > 80:
            stoch_score = 20.0
        else:
            stoch_score = 50.0

        adx_value = ind.get("adx", 25.0)
        if adx_value > 40:
            adx_score = 80.0
        elif adx_value > 25:
            adx_score = 60.0
        else:
            adx_score = 40.0

        upper = ind.get("bollinger_upper", price)
        lower = ind.get("bollinger_lower", price)
        band_width = upper - lower
        if band_width > 0:
            position = (price - lower) / band_width
            if position > 0.8:
                bb_score = 30.0
            elif position < 0.2:
                bb_score = 70.0
            else:
                bb_score = 50.0
        else:
            bb_score = 50.0

        rating = (
            rsi_score * 0.25
            + trend_score * 0.25
            + macd_score * 0.15
            + stoch_score * 0.15
            + adx_score * 0.10
            + bb_score * 0.10
        )
        return int(max(0, min(100, round(rating))))

    @staticmethod
    def describe_momentum(rsi: float) -> dict[str, Any]:
        """
        Describe a momentum (RSI) reading in words.

        This is the single definition of those bands. The frontend renders
        whatever this returns rather than re-deriving labels from the raw
        number, so a card can never show "leaning to buyers" next to a
        sentence calling the same reading "fairly balanced".
        """
        if rsi >= 70:
            return {
                "value": round(rsi, 1),
                "label": "Bought heavily",
                "meaning": (
                    "Buyers have been in control for a while. "
                    "Stretches like this often pause or pull back."
                ),
            }
        if rsi >= 55:
            return {
                "value": round(rsi, 1),
                "label": "Leaning to buyers",
                "meaning": "Slightly more buying than selling pressure recently.",
            }
        if rsi > 45:
            return {
                "value": round(rsi, 1),
                "label": "Balanced",
                "meaning": "Buying and selling pressure are roughly even.",
            }
        if rsi > 30:
            return {
                "value": round(rsi, 1),
                "label": "Leaning to sellers",
                "meaning": "Slightly more selling than buying pressure recently.",
            }
        return {
            "value": round(rsi, 1),
            "label": "Sold off hard",
            "meaning": (
                "Sellers have been in control for a while. "
                "Stretches like this often bounce."
            ),
        }

    @staticmethod
    def strength_percentile(rating: int) -> int:
        """
        The rating expressed as a percentile of readings we have measured.

        This is what the signal engine scores on. The raw rating is retained
        because it is the interpretable weighted blend; the percentile is what
        makes a five-point scale usable.
        """
        return int(round(rating_to_percentile(float(rating))))

    def explain(self, ind: dict[str, Any]) -> list[str]:
        """
        Produce plain-English observations about the technical picture.

        Written for someone who has never heard of RSI: each line states what
        was measured and what it implies, without assuming the jargon.
        """
        notes: list[str] = []
        price = ind.get("price", 0.0)

        rsi_value = ind.get("rsi", 50.0)
        momentum = self.describe_momentum(rsi_value)
        notes.append(f"{momentum['meaning']} Momentum reads {rsi_value:.0f} out of 100.")

        trend = ind.get("trend", "sideways")
        adx_value = ind.get("adx", 25.0)
        if trend == "strong_uptrend":
            notes.append(f"Price is in a clear, sustained uptrend (trend strength {adx_value:.0f}).")
        elif trend == "uptrend":
            notes.append("Price has been drifting upward over the past two weeks.")
        elif trend == "strong_downtrend":
            notes.append(f"Price is in a clear, sustained downtrend (trend strength {adx_value:.0f}).")
        elif trend == "downtrend":
            notes.append("Price has been drifting downward over the past two weeks.")
        else:
            notes.append("Price is moving sideways with no clear direction.")

        if ind.get("golden_cross"):
            notes.append(
                "The 50-day average just crossed above the 200-day — a widely watched bullish marker."
            )
        elif ind.get("death_cross"):
            notes.append(
                "The 50-day average just crossed below the 200-day — a widely watched bearish marker."
            )

        if ind.get("macd", 0.0) > ind.get("macd_signal", 0.0):
            notes.append("Momentum has turned positive over the past few sessions.")
        else:
            notes.append("Momentum has turned negative over the past few sessions.")

        upper, lower = ind.get("bollinger_upper", price), ind.get("bollinger_lower", price)
        if upper > lower:
            position = (price - lower) / (upper - lower)
            if position > 0.9:
                notes.append("Price is at the top of its recent range, where it has tended to stall.")
            elif position < 0.1:
                notes.append("Price is at the bottom of its recent range, where it has tended to find support.")

        volatility = ind.get("volatility", "moderate")
        if volatility == "high":
            notes.append("Day-to-day swings are larger than usual, so expect a bumpier ride.")
        elif volatility == "low":
            notes.append("Day-to-day swings are small — price action has been calm.")

        return notes

    def _insufficient_data(self, closes: np.ndarray) -> dict[str, Any]:
        """
        Neutral indicator set for tickers without enough history.

        Everything sits at its neutral midpoint and `data_quality.sufficient`
        is False, so callers can surface "not enough history" instead of
        presenting invented numbers as analysis.
        """
        price = float(closes[-1]) if len(closes) else 0.0
        return {
            "price": price,
            "bars": len(closes),
            "rsi": 50.0,
            "sma_20": price,
            "sma_50": price,
            "sma_200": None,
            "macd": 0.0,
            "macd_signal": 0.0,
            "macd_histogram": 0.0,
            "bollinger_upper": price,
            "bollinger_middle": price,
            "bollinger_lower": price,
            "stochastic_k": 50.0,
            "stochastic_d": 50.0,
            "atr": 0.0,
            "atr_percent": 0.0,
            "adx": 25.0,
            "avg_volume": 0,
            "price_change_10d": 0.0,
            "trend": "sideways",
            "volatility": "moderate",
            "golden_cross": False,
            "death_cross": False,
            "support": price,
            "resistance": price,
            "data_quality": {
                "bars": len(closes),
                "sufficient": False,
                "has_sma_200": False,
                "has_intraday_range": False,
            },
        }


quant_engine = QuantEngine()
