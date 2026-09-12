"""Tests for the Quant Engine."""

from __future__ import annotations

import numpy as np
import pytest

from app.engines.quant import BARS_FOR_LONG_MA, MIN_BARS, QuantEngine


@pytest.fixture
def engine() -> QuantEngine:
    return QuantEngine()


class TestIndicatorCalculation:
    def test_produces_a_full_indicator_set(self, engine, ohlc):
        highs, lows, closes = ohlc
        result = engine.calculate_indicators(closes, highs, lows)

        for key in ("rsi", "sma_20", "sma_50", "macd", "adx", "trend", "volatility", "price"):
            assert key in result, f"missing {key}"

    def test_no_nan_leaks_into_the_output(self, engine, ohlc):
        """
        NaN is not JSON-serialisable, so it must never reach a response.
        Every indicator has to resolve to a real number or an explicit None.
        """
        highs, lows, closes = ohlc
        result = engine.calculate_indicators(closes, highs, lows)

        for key, value in result.items():
            if isinstance(value, float):
                assert not np.isnan(value), f"{key} is NaN"

    def test_price_is_the_latest_close(self, engine, ohlc):
        highs, lows, closes = ohlc
        result = engine.calculate_indicators(closes, highs, lows)
        assert result["price"] == pytest.approx(closes[-1])

    def test_short_history_is_flagged_not_faked(self, engine):
        result = engine.calculate_indicators(np.linspace(100, 110, MIN_BARS - 1))
        assert result["data_quality"]["sufficient"] is False
        assert result["rsi"] == 50.0  # neutral placeholder, not an invented reading

    def test_sma_200_is_none_without_enough_history(self, engine):
        closes = np.linspace(100, 150, BARS_FOR_LONG_MA - 50)
        result = engine.calculate_indicators(closes)
        # Reporting None is the honest answer; substituting SMA-50 would
        # mislabel a medium-term average as a long-term one.
        assert result["sma_200"] is None
        assert result["data_quality"]["has_sma_200"] is False

    def test_sma_200_present_with_enough_history(self, engine):
        closes = np.linspace(100, 150, BARS_FOR_LONG_MA + 20)
        result = engine.calculate_indicators(closes)
        assert result["sma_200"] is not None
        assert result["data_quality"]["has_sma_200"] is True

    def test_works_without_intraday_range(self, engine, rising_prices):
        result = engine.calculate_indicators(rising_prices)
        assert result["data_quality"]["has_intraday_range"] is False
        assert isinstance(result["adx"], float)


class TestTrendDetection:
    def test_identifies_an_uptrend(self, engine, rising_prices):
        result = engine.calculate_indicators(rising_prices)
        assert result["trend"] in {"uptrend", "strong_uptrend"}

    def test_identifies_a_downtrend(self, engine, falling_prices):
        result = engine.calculate_indicators(falling_prices)
        assert result["trend"] in {"downtrend", "strong_downtrend"}

    def test_identifies_sideways_movement(self, engine, flat_prices):
        result = engine.calculate_indicators(flat_prices)
        assert result["trend"] == "sideways"

    def test_noise_is_never_reported_as_a_trend(self, engine):
        """
        Regression test.

        An earlier detector combined price-vs-moving-average, MACD sign and
        10-day change, treating agreement between them as evidence of a trend.
        Those checks all ask a variant of "is price above its recent average",
        so on a flat stock they agreed by chance roughly half the time and
        produced an "uptrend" out of pure noise. Across many random flat
        series, none may be labelled as trending.
        """
        for seed in range(25):
            rng = np.random.default_rng(seed)
            flat = 100 + rng.normal(0.0, 0.6, 250)
            trend = engine.calculate_indicators(flat)["trend"]
            assert trend == "sideways", f"seed {seed} labelled flat noise as {trend!r}"

    def test_smooth_drift_is_not_vetoed_by_low_adx(self, engine):
        """
        Regression test.

        A steady, low-volatility climb produces a *low* ADX by construction,
        because ADX measures directional movement relative to range. Gating
        trend detection on ADX therefore mislabelled precisely the calmest,
        most persistent trends as sideways.
        """
        # Noise alongside the drift is what suppresses ADX: it creates
        # counter-directional bars while the underlying climb persists. (A
        # perfectly straight line scores ADX 100, so it cannot test this.)
        rng = np.random.default_rng(19)
        noisy_climb = 100 + np.cumsum(rng.normal(0.22, 0.9, 250))

        indicators = engine.calculate_indicators(noisy_climb)

        assert noisy_climb[-1] > noisy_climb[0] * 1.3, "fixture should clearly trend up"
        assert indicators["adx"] < 25.0, "fixture should have a low ADX to be meaningful"
        assert indicators["trend"] in {"uptrend", "strong_uptrend"}


class TestMovingAverageCross:
    """
    The detector is exercised directly with hand-built averages: building a
    price path whose cross lands inside the lookback window is fiddly and
    tests the fixture more than the logic.
    """

    @staticmethod
    def _averages(fast: list[float], slow: list[float]):
        return np.array(fast, dtype=float), np.array(slow, dtype=float)

    def test_detects_a_golden_cross(self, engine):
        # 50-day below the 200-day, then crossing above within the window.
        fast, slow = self._averages([98, 99, 100, 101, 102, 103], [100] * 6)
        result = engine._detect_ma_cross(fast, slow)
        assert result == {"golden_cross": True, "death_cross": False}

    def test_detects_a_death_cross(self, engine):
        fast, slow = self._averages([103, 102, 101, 100.5, 99, 98], [100] * 6)
        result = engine._detect_ma_cross(fast, slow)
        assert result == {"golden_cross": False, "death_cross": True}

    def test_no_cross_when_fast_stays_above(self, engine):
        fast, slow = self._averages([105, 106, 107, 108, 109, 110], [100] * 6)
        result = engine._detect_ma_cross(fast, slow)
        assert result == {"golden_cross": False, "death_cross": False}

    def test_no_cross_without_a_long_average(self, engine):
        fast, _ = self._averages([98, 99, 100, 101, 102, 103], [100] * 6)
        assert engine._detect_ma_cross(fast, None) == {
            "golden_cross": False,
            "death_cross": False,
        }

    def test_no_cross_in_a_steady_trend(self, engine):
        closes = np.linspace(100, 300, 260)
        result = engine.calculate_indicators(closes)
        assert result["golden_cross"] is False
        assert result["death_cross"] is False


class TestTechnicalRating:
    def test_rating_is_bounded(self, engine, rising_prices, falling_prices, flat_prices):
        for series in (rising_prices, falling_prices, flat_prices):
            rating = engine.calculate_technical_rating(engine.calculate_indicators(series))
            assert 0 <= rating <= 100

    def test_uptrend_rates_above_downtrend(self, engine, rising_prices, falling_prices):
        up = engine.calculate_technical_rating(engine.calculate_indicators(rising_prices))
        down = engine.calculate_technical_rating(engine.calculate_indicators(falling_prices))
        assert up > down

    def test_rating_is_deterministic(self, engine, rising_prices):
        indicators = engine.calculate_indicators(rising_prices)
        ratings = {engine.calculate_technical_rating(indicators) for _ in range(5)}
        assert len(ratings) == 1


class TestExplanations:
    def test_returns_readable_sentences(self, engine, rising_prices):
        notes = engine.explain(engine.calculate_indicators(rising_prices))
        assert notes
        for note in notes:
            assert isinstance(note, str)
            assert len(note) > 20
            assert note[0].isupper()
            assert note.endswith((".", "!"))

    def test_avoids_unexplained_jargon(self, engine, rising_prices):
        """
        The audience is first-time investors. Raw indicator acronyms should not
        appear bare in user-facing copy.
        """
        notes = " ".join(engine.explain(engine.calculate_indicators(rising_prices)))
        for jargon in ("RSI", "MACD", "ADX", "Bollinger", "stochastic"):
            assert jargon not in notes, f"jargon leaked into explanation: {jargon}"
