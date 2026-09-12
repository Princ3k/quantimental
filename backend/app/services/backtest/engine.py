"""
Walk-forward backtest of the signal engine.

The question this answers: **when the engine said "Buy", did that stock go on to
outperform simply holding?** Until that is measured, a verdict is an opinion
with a number attached.

How it avoids fooling itself
----------------------------

Lookahead bias is the failure mode that makes backtests useless, and it enters
quietly. Three guards:

1. **The signal at date `t` is computed from a slice ending at `t`.** Never from
   the full series. `calculate_indicators` cannot see a bar that has not been
   passed to it, so a slice is a hard boundary rather than a convention.
2. **Forward returns start at `t`'s close and end at `t + horizon`.** The bar
   that produced the signal is the bar you could have acted on, and it is never
   part of the measured return.
3. **No statistic is fitted across the whole period.** The composite's display
   sparkline standardises z-scores over a full year, which is fine for a chart
   and fatal here, so the backtest does not use it.

What it cannot tell you
-----------------------

- **Sentiment is not included.** There is no archive of historical Reddit or
  news sentiment, so scores here are technicals-only. The live product weights
  sentiment at 55%, so this measures a different, simpler signal.
- **Survivorship bias.** Tickers are chosen today, so every one of them
  survived. Real-world results include companies that did not.
- **No costs.** Spreads, commissions and slippage are ignored, and they fall
  hardest on the most active strategies.

Read the output as "is there a signal here at all", not as an expected return.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any, Optional

import numpy as np
import pandas as pd

from app.engines.hybrid import HybridEngine
from app.engines.quant import MIN_BARS, quant_engine

logger = logging.getLogger(__name__)

# Indicators need history; 300 bars covers SMA-200 plus warm-up. Using a
# rolling window rather than all history keeps cost constant per observation
# and matches what the live service actually sees.
CONTEXT_BARS = 300

# Sentiment cannot be reconstructed historically, so the backtest scores the
# technical signal alone rather than blending against a fabricated value.
_TECHNICAL_ONLY = HybridEngine(technical_weight=1.0, sentiment_weight=0.0)


@dataclass
class Observation:
    """One signal and what happened next."""

    ticker: str
    date: pd.Timestamp
    action: str
    hybrid_score: int
    confidence: int
    technical_rating: int
    price: float
    forward_return: float


@dataclass
class BucketResult:
    """Aggregate outcome for one verdict."""

    action: str
    count: int
    mean_return: float
    median_return: float
    hit_rate: float
    edge_vs_baseline: float
    std_error: float

    @property
    def significant(self) -> bool:
        """
        Whether the edge clears two standard errors.

        A rough 95% bar. With samples this small it is a sanity filter, not a
        formal test — it exists to stop a three-observation bucket being read
        as a finding.
        """
        return self.count >= 30 and abs(self.edge_vs_baseline) > 2 * self.std_error


@dataclass
class BacktestReport:
    """Everything the run measured."""

    tickers: list[str]
    horizon_days: int
    rebalance_days: int
    observations: int
    start: Optional[pd.Timestamp]
    end: Optional[pd.Timestamp]
    baseline_return: float
    buckets: list[BucketResult] = field(default_factory=list)
    directional_accuracy: Optional[float] = None


class Backtester:
    """Replays the engine over history and scores what it said."""

    def __init__(self, horizon_days: int = 10, rebalance_days: int = 5) -> None:
        """
        Args:
            horizon_days: Trading days over which a verdict is judged.
            rebalance_days: Spacing between signals. Overlapping windows
                correlate observations and overstate significance, so this
                should not be much smaller than the horizon.
        """
        if horizon_days < 1 or rebalance_days < 1:
            raise ValueError("horizon_days and rebalance_days must be positive")
        self.horizon_days = horizon_days
        self.rebalance_days = rebalance_days

    def run(self, price_data: dict[str, pd.DataFrame]) -> BacktestReport:
        """
        Backtest across several tickers.

        Args:
            price_data: ticker -> OHLCV frame, oldest first, indexed by date.
        """
        observations: list[Observation] = []
        for ticker, frame in price_data.items():
            observations.extend(self._run_one(ticker, frame))

        return self._summarise(list(price_data), observations)

    def _run_one(self, ticker: str, frame: pd.DataFrame) -> list[Observation]:
        """Walk one ticker forward, emitting a signal every `rebalance_days`."""
        if "Close" not in frame or frame.empty:
            logger.warning("%s: no price data", ticker)
            return []

        clean = frame.dropna(subset=["Close"])
        closes = clean["Close"].to_numpy(dtype=float)
        highs = clean["High"].to_numpy(dtype=float) if "High" in clean else None
        lows = clean["Low"].to_numpy(dtype=float) if "Low" in clean else None
        dates = clean.index

        # The first signal needs MIN_BARS of history behind it; the last needs
        # `horizon_days` of future ahead of it to be scored at all.
        first = MIN_BARS
        last = len(closes) - self.horizon_days - 1
        if last <= first:
            logger.warning("%s: only %d bars, not enough to score", ticker, len(closes))
            return []

        results: list[Observation] = []
        for t in range(first, last + 1, self.rebalance_days):
            # The hard boundary: everything after t is invisible by construction.
            start = max(0, t - CONTEXT_BARS + 1)
            window = slice(start, t + 1)

            indicators = quant_engine.calculate_indicators(
                closes[window],
                highs[window] if highs is not None else None,
                lows[window] if lows is not None else None,
            )
            if not indicators.get("data_quality", {}).get("sufficient", True):
                continue

            rating = quant_engine.calculate_technical_rating(indicators)
            verdict = _TECHNICAL_ONLY.synthesize(
                technical_rating=rating,
                sentiment_rating=rating,
                technical_indicators=indicators,
                sentiment_data={"available": False, "mentions": 0},
            )

            entry = float(closes[t])
            exit_price = float(closes[t + self.horizon_days])
            if entry <= 0:
                continue

            results.append(
                Observation(
                    ticker=ticker,
                    date=dates[t],
                    action=verdict["recommendation"],
                    hybrid_score=verdict["hybrid_score"],
                    confidence=verdict["confidence"],
                    technical_rating=rating,
                    price=entry,
                    forward_return=(exit_price - entry) / entry * 100.0,
                )
            )

        return results

    def _summarise(
        self, tickers: list[str], observations: list[Observation]
    ) -> BacktestReport:
        """Aggregate observations into per-verdict results."""
        if not observations:
            return BacktestReport(
                tickers=tickers,
                horizon_days=self.horizon_days,
                rebalance_days=self.rebalance_days,
                observations=0,
                start=None,
                end=None,
                baseline_return=0.0,
            )

        returns = np.array([o.forward_return for o in observations])

        # The bar to clear. Every observation, regardless of verdict, is what
        # you would have earned holding these names over the same windows —
        # so a verdict only means something if it beats this.
        baseline = float(returns.mean())

        buckets: list[BucketResult] = []
        for action in ("strong_buy", "buy", "hold", "sell", "strong_sell"):
            subset = np.array(
                [o.forward_return for o in observations if o.action == action]
            )
            if subset.size == 0:
                continue

            bullish = action in ("strong_buy", "buy")
            bearish = action in ("sell", "strong_sell")
            if bullish:
                hit_rate = float((subset > 0).mean() * 100)
            elif bearish:
                hit_rate = float((subset < 0).mean() * 100)
            else:
                hit_rate = float('nan')  # "Hold" makes no directional claim.

            # Standard error of the mean, for judging whether an edge is noise.
            std_error = float(subset.std(ddof=1) / np.sqrt(subset.size)) if subset.size > 1 else float("inf")

            buckets.append(
                BucketResult(
                    action=action,
                    count=int(subset.size),
                    mean_return=float(subset.mean()),
                    median_return=float(np.median(subset)),
                    hit_rate=hit_rate,
                    edge_vs_baseline=float(subset.mean()) - baseline,
                    std_error=std_error,
                )
            )

        return BacktestReport(
            tickers=tickers,
            horizon_days=self.horizon_days,
            rebalance_days=self.rebalance_days,
            observations=len(observations),
            start=min(o.date for o in observations),
            end=max(o.date for o in observations),
            baseline_return=baseline,
            buckets=buckets,
            directional_accuracy=self._directional_accuracy(observations),
        )

    @staticmethod
    def _directional_accuracy(observations: list[Observation]) -> Optional[float]:
        """
        Share of directional calls that pointed the right way.

        Holds are excluded — they assert nothing to be right or wrong about.
        """
        directional = [
            o for o in observations
            if o.action in ("strong_buy", "buy", "sell", "strong_sell")
        ]
        if not directional:
            return None

        correct = sum(
            1
            for o in directional
            if (o.action in ("strong_buy", "buy") and o.forward_return > 0)
            or (o.action in ("sell", "strong_sell") and o.forward_return < 0)
        )
        return correct / len(directional) * 100.0
