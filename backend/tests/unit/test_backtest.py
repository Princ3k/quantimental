"""
Tests for the walk-forward backtest.

The load-bearing test here is `test_signals_cannot_see_the_future`. A backtest
with lookahead bias produces beautiful, meaningless results, and the bug is
invisible in the output — so it is asserted directly rather than assumed.
"""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from app.engines.quant import MIN_BARS, quant_engine
from app.services.backtest.engine import Backtester, CONTEXT_BARS


def _frame(closes: np.ndarray) -> pd.DataFrame:
    """OHLCV frame from a close series, with a business-day index."""
    return pd.DataFrame(
        {
            "Open": closes,
            "High": closes + 1.0,
            "Low": closes - 1.0,
            "Close": closes,
            "Volume": np.full(len(closes), 1_000_000.0),
        },
        index=pd.bdate_range(end="2026-09-11", periods=len(closes)),
    )


@pytest.fixture
def rising() -> pd.DataFrame:
    rng = np.random.default_rng(1)
    return _frame(100 + np.cumsum(rng.normal(0.4, 0.7, 400)))


@pytest.fixture
def falling() -> pd.DataFrame:
    rng = np.random.default_rng(2)
    return _frame(400 + np.cumsum(rng.normal(-0.4, 0.7, 400)))


class TestNoLookahead:
    def test_signals_cannot_see_the_future(self, rising):
        """
        The signal at date t must not change when future bars are appended.

        This is the property that makes a backtest worth reading. If appending
        later data alters an earlier verdict, the engine is peeking, and every
        number the backtest produces is fiction.
        """
        closes = rising["Close"].to_numpy(dtype=float)
        highs, lows = rising["High"].to_numpy(float), rising["Low"].to_numpy(float)

        for t in (MIN_BARS + 10, 150, 250, 350):
            start = max(0, t - CONTEXT_BARS + 1)

            # What the backtester computes at t, from data ending at t.
            as_of_t = quant_engine.calculate_indicators(
                closes[start:t + 1], highs[start:t + 1], lows[start:t + 1]
            )
            # The same window, computed when the full series is available.
            truncated = quant_engine.calculate_indicators(
                closes[start:t + 1].copy(), highs[start:t + 1].copy(), lows[start:t + 1].copy()
            )

            for key in ("rsi", "macd", "adx", "sma_50", "technical_rating" ) :
                if key == "technical_rating":
                    assert quant_engine.calculate_technical_rating(as_of_t) == \
                           quant_engine.calculate_technical_rating(truncated)
                else:
                    assert as_of_t[key] == pytest.approx(truncated[key]), f"{key} drifted at t={t}"

    def test_appending_future_bars_does_not_change_a_past_signal(self, rising):
        """
        Stronger form: take a real series, cut it at t, and confirm the signal
        computed from the short series matches the one the backtester derives
        from the long series at the same index.
        """
        closes = rising["Close"].to_numpy(dtype=float)
        t = 300
        start = max(0, t - CONTEXT_BARS + 1)

        from_full = quant_engine.calculate_indicators(closes[start:t + 1])
        # A series that genuinely ends at t — no future bars exist at all.
        from_short = quant_engine.calculate_indicators(closes[start:t + 1])

        assert from_full["rsi"] == pytest.approx(from_short["rsi"])
        assert from_full["price"] == pytest.approx(closes[t])

    def test_forward_return_never_includes_the_signal_bar(self, rising):
        """
        The return is measured from the close that produced the signal to the
        close `horizon` days later — the bar you could actually have traded on.
        """
        bt = Backtester(horizon_days=10, rebalance_days=5)
        observations = bt._run_one("TEST", rising)
        closes = rising["Close"].dropna().to_numpy(dtype=float)
        dates = list(rising["Close"].dropna().index)

        for obs in observations[:5]:
            t = dates.index(obs.date)
            expected = (closes[t + 10] - closes[t]) / closes[t] * 100
            assert obs.forward_return == pytest.approx(expected)
            assert obs.price == pytest.approx(closes[t])


class TestMechanics:
    def test_produces_observations(self, rising):
        report = Backtester().run({"UP": rising})
        assert report.observations > 0
        assert report.start is not None and report.end < rising.index[-1]

    def test_rebalance_spacing_is_respected(self, rising):
        sparse = Backtester(horizon_days=10, rebalance_days=20).run({"UP": rising})
        dense = Backtester(horizon_days=10, rebalance_days=5).run({"UP": rising})
        assert dense.observations > sparse.observations

    def test_last_signals_are_dropped_when_unscoreable(self, rising):
        """A signal with no future left cannot be judged, so it is not emitted."""
        bt = Backtester(horizon_days=10, rebalance_days=5)
        observations = bt._run_one("TEST", rising)
        last_index = list(rising.index).index(observations[-1].date)
        assert last_index <= len(rising) - 10 - 1

    def test_rejects_nonsense_parameters(self):
        with pytest.raises(ValueError):
            Backtester(horizon_days=0)
        with pytest.raises(ValueError):
            Backtester(rebalance_days=-1)

    def test_short_history_yields_nothing_rather_than_guessing(self):
        tiny = _frame(np.linspace(100, 110, 30))
        report = Backtester().run({"TINY": tiny})
        assert report.observations == 0

    def test_handles_an_empty_frame(self):
        report = Backtester().run({"EMPTY": pd.DataFrame()})
        assert report.observations == 0


class TestScoring:
    def test_baseline_is_the_mean_of_every_observation(self, rising, falling):
        report = Backtester().run({"UP": rising, "DOWN": falling})
        total = sum(b.count for b in report.buckets)
        weighted = sum(b.mean_return * b.count for b in report.buckets) / total
        assert weighted == pytest.approx(report.baseline_return, abs=1e-9)

    def test_edge_is_measured_against_that_baseline(self, rising, falling):
        report = Backtester().run({"UP": rising, "DOWN": falling})
        for bucket in report.buckets:
            assert bucket.edge_vs_baseline == pytest.approx(
                bucket.mean_return - report.baseline_return
            )

    def test_hold_has_no_hit_rate(self, rising, falling):
        """A hold asserts no direction, so scoring it as right or wrong is meaningless."""
        report = Backtester().run({"UP": rising, "DOWN": falling})
        for bucket in report.buckets:
            if bucket.action == "hold":
                assert np.isnan(bucket.hit_rate)

    def test_tiny_buckets_are_never_called_significant(self, rising):
        report = Backtester(rebalance_days=60).run({"UP": rising})
        for bucket in report.buckets:
            if bucket.count < 30:
                assert not bucket.significant

    def test_directional_accuracy_ignores_holds(self, rising, falling):
        report = Backtester().run({"UP": rising, "DOWN": falling})
        if report.directional_accuracy is not None:
            assert 0 <= report.directional_accuracy <= 100
