#!/usr/bin/env python3
"""
Score the signal engine against history.

    python scripts/backtest.py                          # default universe, 2y
    python scripts/backtest.py --tickers AAPL MSFT NVDA
    python scripts/backtest.py --years 5 --horizon 20
    python scripts/backtest.py --json ../public/backtest.json

`--json` writes the result where the site can read it. The findings here are
the reason the product no longer publishes buy/sell verdicts, and a claim like
that is worth nothing if the numbers behind it live only in one terminal.

Answers one question: when the engine said "Buy", did that stock go on to beat
simply holding? Read the caveats printed at the end before drawing conclusions.
"""

from __future__ import annotations

import argparse
import json
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


def to_json(report: BacktestReport) -> dict:
    """
    The report as data, for publishing.

    Carries the caveats alongside the numbers rather than leaving them to
    whoever renders it. A backtest quoted without its limits is how a null
    result turns into a marketing claim on its way to a web page.
    """
    return {
        "generated_at": pd.Timestamp.utcnow().isoformat(),
        "universe": report.tickers,
        "period": {
            "start": report.start.strftime("%Y-%m-%d") if report.start is not None else None,
            "end": report.end.strftime("%Y-%m-%d") if report.end is not None else None,
        },
        "observations": report.observations,
        "horizon_days": report.horizon_days,
        "rebalance_days": report.rebalance_days,
        "baseline_return": round(report.baseline_return, 3),
        "directional_accuracy": (
            round(report.directional_accuracy, 1)
            if report.directional_accuracy is not None
            else None
        ),
        "buckets": [
            {
                "action": b.action,
                "count": b.count,
                "mean_return": round(b.mean_return, 3),
                "median_return": round(b.median_return, 3),
                "hit_rate": None if b.hit_rate != b.hit_rate else round(b.hit_rate, 1),
                "edge_vs_baseline": round(b.edge_vs_baseline, 3),
                "std_error": round(b.std_error, 3),
                "significant": b.significant,
                # The figure a reader needs to judge the edge for themselves.
                "t_stat": round(b.edge_vs_baseline / b.std_error, 2) if b.std_error else None,
            }
            for b in report.buckets
        ],
        "any_significant": any(b.significant for b in report.buckets),
        "limitations": [
            "Sentiment is excluded. No historical archive existed when this ran, "
            "so this measures the technical signal alone — while the live engine "
            "weighted sentiment at 55%.",
            "Survivorship bias. These tickers were chosen today, so every one of "
            "them survived the period. Real portfolios include the ones that did not.",
            "No costs. Spreads, commissions and slippage are ignored, and they fall "
            "hardest on the most active strategies.",
            "Overlapping windows are avoided by spacing signals, but the sample is "
            "still small enough that the significance test is a sanity filter "
            "rather than a formal result.",
        ],
    }


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
    parser.add_argument("--json", metavar="PATH",
                        help="also write the result as JSON, for publishing")
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

    if args.json:
        destination = Path(args.json)
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_text(json.dumps(to_json(report), indent=2) + "\n")
        print(f"\nWrote {destination}", file=sys.stderr)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
