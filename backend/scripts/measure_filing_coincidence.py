"""
How often does an 8-K land on a day we call the move company-specific?

Phase 0 of the filings work, and the thing that decides whether the rest of it
gets built. The pitch for ingesting 8-Ks is that they name the catalyst behind
the moves attribution can only call "specific to this company". That is a
testable claim and it has a boring failure mode: if a filing is no more likely
on a company-specific day than on any other day, filings explain nothing and
the LLM phase is not worth its hallucination risk.

So the number that matters is not "how many company-specific days have a
filing". It is the ratio of that to the base rate. Enrichment near 1.0 means
the two are independent and the idea is dead.

Method
------

Attribution comes from `app.engines.attribution.decompose` — the production
function, not a copy — fed the same measurements the scan builds: today's move
and this stock's own typical day, with sector medians over the same universe.
ATR excludes the current bar, as the scan does, so a large day does not
normalise itself away.

A filing is assigned to the session it could have moved: acceptance after 16:00
ET belongs to the next trading day, anything earlier to the current one.
Acceptance timestamps are UTC and converted at a fixed -4, which is right for
EDT and an hour out for the winter weeks. An hour's error only matters for
filings accepted between 16:00 and 17:00 ET, so it is noted rather than fixed.

Each company's window starts at the later of the price history and its own
earliest filing in EDGAR's recent list, which holds 1,000 filings and so
reaches back further for some companies than others. Counting days a company
could not have had a filing recorded for would bias the base rate down and the
enrichment up — that is the error this measurement exists to avoid making.
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
import time
from collections import Counter, defaultdict
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Optional

import httpx
import numpy as np
import pandas as pd
import yfinance as yf

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.engines.attribution import (  # noqa: E402
    FLAT_THRESHOLD_PCT,
    decompose,
)
from app.services.scan.unusual_service import (  # noqa: E402
    ATR_WINDOW,
    UNUSUAL_MULTIPLE,
    load_universe,
)

logging.basicConfig(level=logging.INFO, format="%(message)s")
logger = logging.getLogger("phase0")

# The SEC blocks automated access without a declared contact. This is a
# requirement of their access policy, not a nicety.
USER_AGENT = "Quantimental research atifkhan308@gmail.com"
SEC_SPACING_SECONDS = 0.12  # their ceiling is 10/s; sit under it

TICKER_MAP_URL = "https://www.sec.gov/files/company_tickers.json"
SUBMISSIONS_URL = "https://data.sec.gov/submissions/CIK{cik:010d}.json"

MARKET_CLOSE_HOUR_ET = 16
ET_OFFSET_HOURS = -4

CACHE = Path(__file__).resolve().parents[1] / ".cache" / "phase0"


def _client() -> httpx.Client:
    return httpx.Client(headers={"User-Agent": USER_AGENT}, timeout=30.0)


def _cached(name: str, fetch) -> Any:
    CACHE.mkdir(parents=True, exist_ok=True)
    path = CACHE / name
    if path.exists():
        return json.loads(path.read_text())
    payload = fetch()
    path.write_text(json.dumps(payload))
    return payload


def cik_for_tickers(tickers: list[str], client: httpx.Client) -> dict[str, int]:
    raw = _cached("company_tickers.json", lambda: client.get(TICKER_MAP_URL).json())
    by_ticker = {row["ticker"]: int(row["cik_str"]) for row in raw.values()}
    # EDGAR writes class shares with a dash where Yahoo uses a dot.
    return {
        t: by_ticker[key]
        for t in tickers
        for key in (t, t.replace(".", "-"))
        if key in by_ticker
    }


def filings_for(ticker: str, cik: int, client: httpx.Client) -> dict[str, Any]:
    """Every 8-K EDGAR still lists for one company, with its items."""

    def fetch() -> dict[str, Any]:
        time.sleep(SEC_SPACING_SECONDS)
        response = client.get(SUBMISSIONS_URL.format(cik=cik))
        response.raise_for_status()
        recent = response.json()["filings"]["recent"]
        return {
            "earliest_any": min(recent["filingDate"]) if recent["filingDate"] else None,
            "filings": [
                {"accepted": recent["acceptanceDateTime"][i], "items": recent["items"][i]}
                for i, form in enumerate(recent["form"])
                if form == "8-K"
            ],
        }

    return _cached(f"sub_{ticker}.json", fetch)


def session_for(accepted_utc: str, sessions: list[pd.Timestamp]) -> Optional[pd.Timestamp]:
    """The trading day a filing could have moved."""
    stamp = datetime.fromisoformat(accepted_utc.replace("Z", "+00:00"))
    et = stamp.astimezone(timezone.utc) + timedelta(hours=ET_OFFSET_HOURS)
    day = et.date()
    if et.hour >= MARKET_CLOSE_HOUR_ET:
        day += timedelta(days=1)

    target = pd.Timestamp(day)
    for session in sessions:          # roll onto the next open session
        if session >= target:
            return session
    return None


def _frame_for(data: pd.DataFrame, ticker: str) -> Optional[pd.DataFrame]:
    if isinstance(data.columns, pd.MultiIndex):
        if ticker not in data.columns.get_level_values(0):
            return None
        frame = data[ticker]
    else:
        frame = data
    return frame if {"High", "Low", "Close"} <= set(frame.columns) else None


def atr_percent(frame: pd.DataFrame) -> pd.Series:
    """Rolling ATR as a percent of the previous close, excluding today's bar."""
    previous = frame["Close"].shift(1)
    tr = pd.concat(
        [frame["High"] - frame["Low"],
         (frame["High"] - previous).abs(),
         (frame["Low"] - previous).abs()],
        axis=1,
    ).max(axis=1)
    tr.iloc[0] = np.nan
    # shift(1) so the window ends on yesterday: today's move is being judged
    # against normal, and must not be part of it.
    return tr.shift(1).rolling(ATR_WINDOW).mean() / previous * 100.0


def classify(change: float, context: dict[str, Any]) -> str:
    """The branch `attribution.explain` would take for this stock today."""
    if not context["diverged"]:
        return "tracked_market"

    sector_pct = context["sector_percent"]
    stock_up = change > FLAT_THRESHOLD_PCT
    stock_down = change < -FLAT_THRESHOLD_PCT
    sector_up = sector_pct > FLAT_THRESHOLD_PCT
    sector_down = sector_pct < -FLAT_THRESHOLD_PCT

    if (stock_up and sector_down) or (stock_down and sector_up):
        return "against_sector"
    if not stock_up and not stock_down and (sector_up or sector_down):
        return "did_not_follow"
    return "company_specific"


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--period", default="2y")
    parser.add_argument("--json", type=Path, help="write the result here")
    args = parser.parse_args()

    universe = load_universe()
    tickers = [row["ticker"] for row in universe]
    sectors = {row["ticker"]: row["sector"] for row in universe}
    logger.info("Universe: %d tickers", len(tickers))

    logger.info("Downloading %s of prices...", args.period)
    prices = yf.download(
        tickers, period=args.period, auto_adjust=False,
        group_by="ticker", threads=True, progress=False,
    )

    changes: dict[str, pd.Series] = {}
    typicals: dict[str, pd.Series] = {}
    for ticker in tickers:
        frame = _frame_for(prices, ticker)
        if frame is None or frame["Close"].dropna().empty:
            continue
        changes[ticker] = frame["Close"].pct_change() * 100.0
        typicals[ticker] = atr_percent(frame)

    sessions = sorted(prices.index)
    logger.info("Measured %d tickers over %d sessions", len(changes), len(sessions))

    logger.info("Fetching 8-K history from EDGAR (about a minute)...")
    with _client() as client:
        ciks = cik_for_tickers(tickers, client)
        by_ticker: dict[str, dict[pd.Timestamp, list[str]]] = {}
        earliest: dict[str, pd.Timestamp] = {}
        for n, (ticker, cik) in enumerate(ciks.items(), 1):
            if ticker not in changes:
                continue
            try:
                record = filings_for(ticker, cik, client)
            except Exception as exc:  # noqa: BLE001
                logger.warning("  %s: %s", ticker, exc)
                continue
            landed: dict[pd.Timestamp, list[str]] = defaultdict(list)
            for filing in record["filings"]:
                session = session_for(filing["accepted"], sessions)
                if session is not None:
                    landed[session].extend(
                        i.strip() for i in (filing["items"] or "").split(",") if i.strip()
                    )
            by_ticker[ticker] = landed
            if record["earliest_any"]:
                earliest[ticker] = pd.Timestamp(record["earliest_any"])
            if n % 100 == 0:
                logger.info("  %d/%d", n, len(ciks))

    logger.info("EDGAR coverage: %d tickers", len(by_ticker))

    counts: Counter[str] = Counter()
    filed: Counter[str] = Counter()
    unusual_counts: Counter[str] = Counter()
    unusual_filed: Counter[str] = Counter()
    items_on_specific: Counter[str] = Counter()
    items_overall: Counter[str] = Counter()

    for index, session in enumerate(sessions):
        if index < ATR_WINDOW + 2:
            continue

        measurements = []
        for ticker in by_ticker:
            change = changes[ticker].get(session)
            typical = typicals[ticker].get(session)
            if change is None or typical is None:
                continue
            if not np.isfinite(change) or not np.isfinite(typical) or typical <= 0:
                continue
            # Only count days this company could have had a filing recorded for.
            if ticker in earliest and session < earliest[ticker]:
                continue
            measurements.append({
                "ticker": ticker,
                "change_percent": float(change),
                "typical_percent": float(typical),
            })

        if len(measurements) < 100:
            continue

        attribution = decompose(measurements, sectors)
        for row in measurements:
            ticker = row["ticker"]
            context = attribution.get(ticker)
            if not context:
                continue

            kind = classify(row["change_percent"], context)
            has_filing = session in by_ticker[ticker]
            items = by_ticker[ticker].get(session, [])

            counts[kind] += 1
            counts["all"] += 1
            if has_filing:
                filed[kind] += 1
                filed["all"] += 1
                items_overall.update(items)
                if kind == "company_specific":
                    items_on_specific.update(items)

            if abs(row["change_percent"]) >= row["typical_percent"] * UNUSUAL_MULTIPLE:
                unusual_counts[kind] += 1
                unusual_counts["all"] += 1
                if has_filing:
                    unusual_filed[kind] += 1
                    unusual_filed["all"] += 1

    def rate(kind: str, f=filed, c=counts) -> float:
        return (f[kind] / c[kind] * 100.0) if c[kind] else 0.0

    base = rate("all")
    specific = rate("company_specific")

    print("\n" + "=" * 66)
    print("  Do 8-K filings land on the days we call company-specific?")
    print("=" * 66)
    print(f"\n  {counts['all']:,} ticker-days across {len(by_ticker)} companies\n")

    print("  How the attribution classified them")
    for kind in ("tracked_market", "company_specific", "against_sector", "did_not_follow"):
        share = counts[kind] / counts["all"] * 100.0 if counts["all"] else 0.0
        print(f"    {kind:<18} {counts[kind]:>8,}  {share:5.1f}%   "
              f"8-K on {rate(kind):5.2f}% of them")

    print(f"\n  Base rate, any day        {base:5.2f}%")
    print(f"  Company-specific days     {specific:5.2f}%")
    enrichment = specific / base if base else 0.0
    print(f"  Enrichment                {enrichment:5.2f}x")

    ub = (unusual_filed["all"] / unusual_counts["all"] * 100.0) if unusual_counts["all"] else 0.0
    us = (unusual_filed["company_specific"] / unusual_counts["company_specific"] * 100.0
          if unusual_counts["company_specific"] else 0.0)
    print(f"\n  Restricted to unusual moves (>= {UNUSUAL_MULTIPLE}x typical), "
          f"{unusual_counts['all']:,} days")
    print(f"    any unusual day         {ub:5.2f}%")
    print(f"    unusual + specific      {us:5.2f}%   "
          f"({(us / ub if ub else 0):.2f}x the unusual base rate)")

    print("\n  Items most often filed on a company-specific day")
    for item, n in items_on_specific.most_common(8):
        overall = items_overall[item] or 1
        print(f"    {item:<6} {n:>6,}   {n / overall * 100:5.1f}% of this item's filings")

    print("\n" + "=" * 66)
    if enrichment < 1.2:
        print("  Filings are ~independent of company-specific moves. Phase 3 is not")
        print("  worth its hallucination risk; Phase 1 still stands on earnings days.")
    elif enrichment < 2.0:
        print("  A real but modest signal. Phase 1 and 2 are justified; Phase 3 only")
        print("  if the item mix shows filings people would actually want explained.")
    else:
        print("  Strongly enriched. Filings explain a meaningful share of the moves")
        print("  attribution can currently only call company-specific. Build Phase 3.")
    print("=" * 66 + "\n")

    if args.json:
        args.json.write_text(json.dumps({
            "measured_at": datetime.now(timezone.utc).isoformat(),
            "period": args.period,
            "companies": len(by_ticker),
            "ticker_days": counts["all"],
            "counts": dict(counts),
            "filed": dict(filed),
            "base_rate_percent": round(base, 3),
            "company_specific_rate_percent": round(specific, 3),
            "enrichment": round(enrichment, 3),
            "unusual": {
                "days": unusual_counts["all"],
                "base_rate_percent": round(ub, 3),
                "company_specific_rate_percent": round(us, 3),
            },
            "items_on_company_specific": dict(items_on_specific.most_common(20)),
        }, indent=2) + "\n")
        logger.info("Wrote %s", args.json)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
