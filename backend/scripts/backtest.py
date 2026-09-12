#!/usr/bin/env python3
"""
Score the signal engine against history.

    python scripts/backtest.py                          # default universe, 2y
    python scripts/backtest.py --tickers AAPL MSFT NVDA
    python scripts/backtest.py --years 5 --horizon 20

Answers one question: when the engine said "Buy", did that stock go on to beat
simply holding? Read the caveats printed at the end before drawing conclusions.
"""

from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

import pandas as pd
import yfinance as yf

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.services.backtest.engine import BacktestReport, Backtester  # noqa: E402

logging.basicConfig(level=logging.WARNING, format="%(levelname)s: %(message)s")

# A deliberately mixed universe: mega-cap tech alone would measure one regime.
DEFAULT_UNIVERSE = [
    "AAPL", "MSFT", "NVDA", "GOOGL", "AMZN", "TSLA", "META",
    "JPM", "V", "JNJ", "WMT", "PG", "XOM", "KO", "DIS", "INTC",
]


def fetch(tickers: list[str], years: int) -> dict[str, pd.DataFrame]:
    """Download OHLCV for the universe in one batched request."""
    raw = yf.download(
        tickers, period=f"{years}y", progress=False, auto_adjust=True, group_by="ticker"
    )
    if raw is None or raw.empty:
        return {}

    data: dict[str, pd.DataFrame] = {}
    for ticker in tickers:
        try:
            frame = raw[ticker] if len(tickers) > 1 else raw
            frame = frame.dropna(subset=["Close"])
            if len(frame) > 100:
                data[ticker] = frame
        except (KeyError, TypeError):
            logging.warning("No data for %s", ticker)
    return data


def render(report: BacktestReport) -> None:
    """Print the report."""
    print()
    print("=" * 74)
    print("  QUANTIMENTAL — SIGNAL BACKTEST")
    print("=" * 74)
    print(f"  Universe      {len(report.tickers)} tickers")
    print(f"  Period        {report.start:%Y-%m-%d} to {report.end:%Y-%m-%d}")
    print(f"  Observations  {report.observations:,} "
          f"(a signal every {report.rebalance_days} days, judged {report.horizon_days} days out)")
    print()
    print(f"  Baseline: holding these names over the same windows returned "
          f"{report.baseline_return:+.2f}% on average.")
    print("  A verdict is only worth anything if it beats that.")
    print()
    print("-" * 74)
    print(f"  {'VERDICT':<13}{'N':>6}{'MEAN':>9}{'MEDIAN':>9}{'HIT':>8}{'EDGE':>9}   VS BASELINE")
    print("-" * 74)

    for bucket in report.buckets:
        hit = "     —" if bucket.hit_rate != bucket.hit_rate else f"{bucket.hit_rate:5.1f}%"
        mark = "  significant" if bucket.significant else ""
        print(
            f"  {bucket.action:<13}{bucket.count:>6}"
            f"{bucket.mean_return:>8.2f}%{bucket.median_return:>8.2f}%"
            f"{hit:>8}{bucket.edge_vs_baseline:>+8.2f}%{mark}"
        )

    print("-" * 74)
    if report.directional_accuracy is not None:
        print(f"  Directional calls correct: {report.directional_accuracy:.1f}% "
              f"(coin flip is ~50%, holds excluded)")
    print()

    _verdict(report)

    print()
    print("  What this does NOT measure")
    print("  " + "-" * 40)
    print("  · Sentiment. No historical archive exists, so this is the technical")
    print("    signal alone. The live product weights sentiment at 55%.")
    print("  · Survivorship. These tickers were picked today, so all of them")
    print("    survived. Real portfolios include the ones that did not.")
    print("  · Costs. Spreads, commissions and slippage are ignored.")
    print()


def _verdict(report: BacktestReport) -> None:
    """State plainly whether anything here is worth acting on."""
    bullish = [b for b in report.buckets if b.action in ("strong_buy", "buy")]
    bearish = [b for b in report.buckets if b.action in ("sell", "strong_sell")]
    significant = [b for b in report.buckets if b.significant]

    print("  Reading")
    print("  " + "-" * 40)

    if not significant:
        print("  No verdict beat the baseline by more than statistical noise.")
        print("  On this evidence the signal does not predict returns. That is a")
        print("  real result, and the honest thing to do with it is to stop")
        print("  presenting these verdicts as forecasts.")
        return

    for bucket in significant:
        direction = "beat" if bucket.edge_vs_baseline > 0 else "trailed"
        print(f"  '{bucket.action}' {direction} the baseline by "
              f"{abs(bucket.edge_vs_baseline):.2f}% over {report.horizon_days} days "
              f"(n={bucket.count}).")

    if bullish and bearish:
        spread = max(b.mean_return for b in bullish) - min(b.mean_return for b in bearish)
        print(f"  Spread between the most bullish and most bearish verdict: {spread:+.2f}%.")

    print()
    print("  Treat as a hypothesis worth more testing, not a validated edge.")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--tickers", nargs="+", default=DEFAULT_UNIVERSE)
    parser.add_argument("--years", type=int, default=2)
    parser.add_argument("--horizon", type=int, default=10,
                        help="trading days over which a verdict is judged")
    parser.add_argument("--rebalance", type=int, default=5,
                        help="trading days between signals")
    args = parser.parse_args()

    print(f"Fetching {len(args.tickers)} tickers over {args.years}y…", file=sys.stderr)
    data = fetch(args.tickers, args.years)
    if not data:
        print("No price data available.", file=sys.stderr)
        return 1

    print(f"Replaying the engine over {len(data)} tickers…", file=sys.stderr)
    report = Backtester(horizon_days=args.horizon, rebalance_days=args.rebalance).run(data)

    if report.observations == 0:
        print("No scoreable observations.", file=sys.stderr)
        return 1

    render(report)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
