"""
Tests for the pure-Python technical indicators.

These replace a C dependency (TA-Lib), so they are checked against closed-form
expectations and known mathematical properties rather than against another
implementation — the point is that the maths is right on its own terms.
"""

from __future__ import annotations

import numpy as np
import pytest

from app.engines import indicators as ta


class TestSMA:
    def test_matches_manual_average(self):
        values = np.arange(1.0, 11.0)  # 1..10
        result = ta.sma(values, 3)
        # Last window is (8+9+10)/3
        assert result[-1] == pytest.approx(9.0)
        assert result[2] == pytest.approx(2.0)  # (1+2+3)/3

    def test_leading_values_are_nan(self):
        result = ta.sma(np.arange(1.0, 11.0), 3)
        assert np.isnan(result[:2]).all()
        assert not np.isnan(result[2:]).any()

    def test_constant_series_returns_the_constant(self):
        result = ta.sma(np.full(50, 7.0), 10)
        assert result[-1] == pytest.approx(7.0)


class TestEMA:
    def test_seeded_with_sma_of_first_period(self):
        values = np.arange(1.0, 21.0)
        result = ta.ema(values, 5)
        # First EMA value is the SMA of the first 5 points: (1+2+3+4+5)/5
        assert result[4] == pytest.approx(3.0)

    def test_constant_series_returns_the_constant(self):
        result = ta.ema(np.full(50, 42.0), 10)
        assert result[-1] == pytest.approx(42.0)

    def test_reacts_faster_than_sma(self):
        # A step change part-way through the window: the EMA weights recent
        # bars more heavily, so it should sit above the equal-weighted SMA.
        # (With 10+ bars at the new level the SMA has fully caught up and the
        # comparison stops being meaningful.)
        values = np.concatenate([np.full(30, 100.0), np.full(4, 110.0)])
        assert ta.ema(values, 10)[-1] > ta.sma(values, 10)[-1]

    def test_too_short_input_is_all_nan(self):
        assert np.isnan(ta.ema(np.arange(3.0), 10)).all()


class TestRSI:
    def test_monotonic_rise_gives_rsi_100(self):
        # With no down days there is no average loss, so RSI pins at 100.
        result = ta.rsi(np.arange(1.0, 60.0), 14)
        assert result[-1] == pytest.approx(100.0)

    def test_monotonic_fall_gives_rsi_0(self):
        result = ta.rsi(np.arange(60.0, 1.0, -1.0), 14)
        assert result[-1] == pytest.approx(0.0)

    def test_stays_within_bounds(self, rising_prices, falling_prices, flat_prices):
        for series in (rising_prices, falling_prices, flat_prices):
            values = ta.rsi(series, 14)
            valid = values[~np.isnan(values)]
            assert valid.min() >= 0.0
            assert valid.max() <= 100.0

    def test_uptrend_reads_above_downtrend(self, rising_prices, falling_prices):
        assert ta.rsi(rising_prices, 14)[-1] > ta.rsi(falling_prices, 14)[-1]


class TestMACD:
    def test_histogram_is_line_minus_signal(self, rising_prices):
        line, signal, histogram = ta.macd(rising_prices)
        valid = ~np.isnan(histogram)
        assert np.allclose(histogram[valid], (line - signal)[valid])

    def test_positive_in_uptrend_negative_in_downtrend(self, rising_prices, falling_prices):
        assert ta.macd(rising_prices)[0][-1] > 0
        assert ta.macd(falling_prices)[0][-1] < 0

    def test_constant_series_gives_zero(self):
        line, _, _ = ta.macd(np.full(100, 50.0))
        assert line[-1] == pytest.approx(0.0, abs=1e-9)


class TestBollingerBands:
    def test_bands_straddle_the_middle(self, rising_prices):
        upper, middle, lower = ta.bollinger_bands(rising_prices, 20, 2.0)
        valid = ~np.isnan(middle)
        assert (upper[valid] >= middle[valid]).all()
        assert (middle[valid] >= lower[valid]).all()

    def test_middle_band_is_the_sma(self, rising_prices):
        _, middle, _ = ta.bollinger_bands(rising_prices, 20, 2.0)
        expected = ta.sma(rising_prices, 20)
        valid = ~np.isnan(middle)
        assert np.allclose(middle[valid], expected[valid])

    def test_zero_volatility_collapses_the_bands(self):
        upper, middle, lower = ta.bollinger_bands(np.full(50, 10.0), 20, 2.0)
        assert upper[-1] == pytest.approx(lower[-1])
        assert middle[-1] == pytest.approx(10.0)


class TestStochastic:
    def test_bounded_zero_to_hundred(self, ohlc):
        highs, lows, closes = ohlc
        slow_k, slow_d = ta.stochastic(highs, lows, closes)
        for series in (slow_k, slow_d):
            valid = series[~np.isnan(series)]
            assert valid.min() >= 0.0
            assert valid.max() <= 100.0

    def test_close_at_window_high_reads_near_100(self):
        closes = np.concatenate([np.full(20, 10.0), np.array([20.0] * 5)])
        highs, lows = closes.copy(), closes.copy()
        slow_k, _ = ta.stochastic(highs, lows, closes, 14, 3, 3)
        assert slow_k[-1] == pytest.approx(100.0)

    def test_flat_window_is_treated_as_mid_range(self):
        # high == low everywhere: position within the range is undefined, and
        # 50 is the honest answer rather than a divide-by-zero.
        flat = np.full(40, 5.0)
        slow_k, _ = ta.stochastic(flat, flat, flat)
        assert slow_k[-1] == pytest.approx(50.0)


class TestTrueRangeAndATR:
    def test_first_bar_true_range_is_nan(self):
        closes = np.array([10.0, 11.0, 12.0, 13.0])
        tr = ta.true_range(closes + 1, closes - 1, closes)
        assert np.isnan(tr[0])

    def test_true_range_accounts_for_gaps(self):
        # A gap up: |high - prev_close| exceeds the intraday high-low range.
        closes = np.array([10.0, 20.0])
        highs = np.array([10.5, 20.5])
        lows = np.array([9.5, 19.5])
        tr = ta.true_range(highs, lows, closes)
        assert tr[1] == pytest.approx(10.5)  # 20.5 - 10.0, not 20.5 - 19.5

    def test_atr_is_non_negative(self, ohlc):
        highs, lows, closes = ohlc
        values = ta.atr(highs, lows, closes, 14)
        valid = values[~np.isnan(values)]
        assert (valid >= 0).all()

    def test_atr_first_value_lands_after_the_period(self, ohlc):
        highs, lows, closes = ohlc
        values = ta.atr(highs, lows, closes, 14)
        # Bar 0 has no true range, so the seed consumes bars 1..14.
        assert np.isnan(values[13])
        assert not np.isnan(values[14])

    def test_wider_ranges_give_larger_atr(self):
        closes = np.full(60, 100.0)
        narrow = ta.atr(closes + 0.5, closes - 0.5, closes, 14)[-1]
        wide = ta.atr(closes + 5.0, closes - 5.0, closes, 14)[-1]
        assert wide > narrow


class TestADX:
    def test_bounded_zero_to_hundred(self, ohlc):
        highs, lows, closes = ohlc
        values = ta.adx(highs, lows, closes, 14)
        valid = values[~np.isnan(values)]
        assert valid.min() >= 0.0
        assert valid.max() <= 100.0

    def test_strong_trend_scores_higher_than_chop(self, flat_prices):
        trending = np.arange(100.0, 200.0)
        choppy = flat_prices[:100]
        trend_adx = ta.adx(trending + 1, trending - 1, trending, 14)[-1]
        chop_adx = ta.adx(choppy + 1, choppy - 1, choppy, 14)[-1]
        assert trend_adx > chop_adx

    def test_flat_market_has_no_directional_strength(self):
        flat = np.full(80, 50.0)
        assert ta.adx(flat, flat, flat, 14)[-1] == pytest.approx(0.0)


class TestShortInputs:
    """Indicators must degrade to NaN, never raise, on insufficient data."""

    @pytest.mark.parametrize("length", [0, 1, 2, 5])
    def test_no_exceptions_on_tiny_inputs(self, length):
        closes = np.linspace(10.0, 12.0, length) if length else np.array([])
        highs = closes + 0.5 if length else np.array([])
        lows = closes - 0.5 if length else np.array([])

        ta.sma(closes, 20)
        ta.ema(closes, 12)
        ta.rsi(closes, 14)
        ta.macd(closes)
        ta.bollinger_bands(closes, 20)
        if length:
            ta.stochastic(highs, lows, closes)
            ta.atr(highs, lows, closes, 14)
            ta.adx(highs, lows, closes, 14)
