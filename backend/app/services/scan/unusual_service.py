"""
Unusual-movement scan.

The question this answers: **what is worth looking at today, whether or not you
own it?**

A watchlist of six stocks is quiet most days, and an app with nothing to say is
an app nobody opens. Scanning a broad universe means there is almost always
something genuinely notable — and "genuinely" is the constraint that makes this
worth building rather than a list of today's biggest percentage movers.

What counts as unusual
----------------------

A move is measured against **that stock's own recent daily range**, not against
a fixed percentage and not against other stocks. A 3% day is remarkable for a
utility and a Tuesday for a volatile small cap; one threshold gets both wrong,
and a raw percentage leaderboard is just a list of the most volatile tickers in
the index, which is the same list every day and therefore not news.

Deliberately not included
-------------------------

- **No ranking by "opportunity".** The output says what moved and by how much
  relative to normal. It does not say whether that is good.
- **No sentiment.** This runs over hundreds of tickers on a schedule; news
  fetches per ticker would blow every rate limit we have. Sentiment stays on
  the single-stock path where a human asked for it.

The payload carries two lists. `movers` are the stocks that cleared the
unusual bar, which on a calm day is none of them. `biggest` is simply the
day's largest moves, always populated, so the page has something to show
without ever calling an ordinary move remarkable.
"""

from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

import numpy as np
import pandas as pd
import yfinance as yf

from app.engines.attribution import decompose, explain as explain_move
from app.engines.describe import describe

logger = logging.getLogger(__name__)

UNIVERSE_PATH = Path(__file__).resolve().parents[3] / "data" / "universe.json"

# Enough history for a 14-day true range plus the 10-day lookback, with room
# for holidays. Kept short deliberately: this is ~500 tickers of OHLC.
HISTORY_PERIOD = "3mo"

# Wilder's default window, matching the ATR used everywhere else in the app.
ATR_WINDOW = 14

# A move must be at least this many times the stock's own average daily range
# before it is called unusual. Measured against the S&P 500, this surfaces a
# handful on an ordinary session and dozens on a volatile one, which is the
# shape we want: the count itself should tell you what kind of day it was.
UNUSUAL_MULTIPLE = 2.0

# On a genuinely calm day nothing clears the bar, and a page with nothing on it
# is a page nobody returns to. So the day's largest moves are always carried
# too, clearly separated — "biggest" is a different claim from "unusual" and
# the UI must not blur them.
BIGGEST_COUNT = 8

# Below this, percentage moves are noise however they compare to a quiet
# stock's range. Without it, a stock that normally moves 0.1% would be
# "unusual" on a 0.3% day, which is true and useless.
MIN_ABSOLUTE_MOVE_PCT = 1.5

# Cheap stocks produce huge percentage moves on small absolute ones, and
# illiquid ones produce them on no volume at all.
MIN_PRICE = 1.0

MAX_RESULTS = 40


def load_universe(path: Path = UNIVERSE_PATH) -> list[dict[str, str]]:
    """The tickers to scan, with their display names."""
    payload = json.loads(path.read_text())
    return payload["constituents"]


def _true_range(frame: pd.DataFrame) -> pd.Series:
    """
    True range per bar, which is what makes a move comparable across stocks.

    The first bar has no previous close, so its true range is genuinely
    undefined rather than zero — the same convention as app/engines/indicators.
    """
    previous_close = frame["Close"].shift(1)
    spans = pd.concat(
        [
            frame["High"] - frame["Low"],
            (frame["High"] - previous_close).abs(),
            (frame["Low"] - previous_close).abs(),
        ],
        axis=1,
    )
    tr = spans.max(axis=1)
    tr.iloc[0] = np.nan
    return tr


def _measure(ticker: str, frame: pd.DataFrame) -> Optional[dict[str, Any]]:
    """
    Reduce one stock's recent bars to the few numbers the scan needs.

    Returns None whenever the data cannot support a claim — too few bars, a
    missing close, or a flat range that would make every move infinitely
    unusual on division.
    """
    frame = frame.dropna(subset=["Close"])
    if len(frame) < ATR_WINDOW + 2:
        return None

    closes = frame["Close"]
    price = float(closes.iloc[-1])
    previous = float(closes.iloc[-2])
    if price < MIN_PRICE or previous <= 0:
        return None

    change_percent = (price - previous) / previous * 100.0

    # Exclude the current bar: "normal for this stock" must not include the
    # move being judged, or a large day partly normalises itself away.
    tr = _true_range(frame).iloc[:-1]
    atr = float(tr.tail(ATR_WINDOW).mean())
    if not np.isfinite(atr) or atr <= 0:
        return None

    typical_pct = atr / previous * 100.0
    if typical_pct <= 0:
        return None

    period_percent = 0.0
    if len(closes) >= 11:
        ten_ago = float(closes.iloc[-11])
        if ten_ago > 0:
            period_percent = (price - ten_ago) / ten_ago * 100.0

    return {
        "ticker": ticker,
        "price": round(price, 2),
        "change_percent": round(change_percent, 2),
        "typical_percent": round(typical_pct, 2),
        "multiple": round(abs(change_percent) / typical_pct, 1),
        "direction": "up" if change_percent > 0 else "down",
        "period_percent": round(period_percent, 2),
        "volume": int(frame["Volume"].iloc[-1]) if "Volume" in frame else 0,
    }


def _headline(move: dict[str, Any], company: str) -> str:
    """
    One sentence, in the same descriptive voice as the single-stock cards.

    States the move, then what makes it notable — which is always the
    comparison to that stock's own normal, never a judgement about it.
    """
    direction = "up" if move["direction"] == "up" else "down"
    return (
        f"{company} is {direction} {abs(move['change_percent']):.1f}% today, "
        f"{move['multiple']:.1f}x its typical {move['typical_percent']:.1f}% daily move."
    )


def scan(universe: Optional[list[dict[str, str]]] = None) -> dict[str, Any]:
    """
    Scan the universe and return the stocks having genuinely unusual days.

    Returns a payload with the scan metadata and the movers, most unusual
    first. An empty `movers` list on a calm day is a valid answer, not a
    failure — the UI says the market was quiet rather than padding the list.
    """
    constituents = universe if universe is not None else load_universe()
    names = {c["ticker"]: c["name"] for c in constituents}
    sectors = {c["ticker"]: c.get("sector", "") for c in constituents}
    symbols = list(names)

    logger.info("Scanning %d tickers", len(symbols))

    try:
        raw = yf.download(
            symbols,
            period=HISTORY_PERIOD,
            progress=False,
            auto_adjust=True,
            threads=True,
            group_by="ticker",
        )
    except Exception as exc:  # noqa: BLE001
        logger.error("Universe download failed: %s", exc)
        return {"available": False, "reason": f"Market data unavailable: {exc}"}

    if raw is None or raw.empty:
        return {"available": False, "reason": "Market data returned nothing."}

    movers: list[dict[str, Any]] = []
    measurements: list[dict[str, Any]] = []

    for ticker in symbols:
        try:
            frame = raw[ticker]
        except KeyError:
            continue
        if not isinstance(frame, pd.DataFrame) or frame.empty:
            continue

        move = _measure(ticker, frame)
        if move is None:
            continue
        measurements.append(move)

        if move["multiple"] < UNUSUAL_MULTIPLE:
            continue
        if abs(move["change_percent"]) < MIN_ABSOLUTE_MOVE_PCT:
            continue

        move["company"] = names.get(ticker, ticker)
        move["sector"] = sectors.get(ticker, "")
        move["headline"] = _headline(move, move["company"])
        movers.append(move)

    movers.sort(key=lambda m: m["multiple"], reverse=True)

    # Ranked by raw percentage, not by multiple: this list answers "what moved
    # most today", which is a plainer question than "what moved unusually".
    biggest = sorted(measurements, key=lambda m: abs(m["change_percent"]), reverse=True)
    for move in biggest[:BIGGEST_COUNT]:
        move.setdefault("company", names.get(move["ticker"], move["ticker"]))
        move.setdefault("sector", sectors.get(move["ticker"], ""))

    # Attribution needs every stock's move, so it runs once over the whole
    # sweep rather than per ticker.
    # Defaults to False, not True: a constituent added without the flag must
    # not silently join the basket that defines "the market".
    benchmark = {c["ticker"] for c in constituents if c.get("benchmark", False)}
    attribution = decompose(measurements, sectors, benchmark=benchmark)

    snapshot = [_snapshot_row(m, names, sectors, attribution) for m in measurements]

    # The feed's own rows carry it too — "it fell with its sector" is often the
    # most useful thing to say about a stock having an unusual day.
    for move in movers + biggest:
        context = explain_move(
            move.get("company", move["ticker"]),
            move["change_percent"],
            attribution.get(move["ticker"]),
        )
        if context:
            move["context"] = context

    as_of = _latest_session(raw)

    return {
        "available": True,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "as_of": as_of,
        "scanned": len(measurements),
        "universe": len(symbols),
        "unusual_count": len(movers),
        "rising": sum(1 for m in movers if m["direction"] == "up"),
        "falling": sum(1 for m in movers if m["direction"] == "down"),
        "movers": movers[:MAX_RESULTS],
        "biggest": biggest[:BIGGEST_COUNT],
        # Every measured ticker, compactly. Split into its own file by the
        # publisher; see _snapshot_row for why it exists.
        "snapshot": snapshot,
        "threshold": {
            "multiple": UNUSUAL_MULTIPLE,
            "min_move_percent": MIN_ABSOLUTE_MOVE_PCT,
        },
    }


def _snapshot_row(
    move: dict[str, Any],
    names: dict[str, str],
    sectors: dict[str, str],
    attribution: Optional[dict[str, dict[str, Any]]] = None,
) -> dict[str, Any]:
    """
    One ticker, reduced to what a page or a widget needs to render it.

    Short keys because this carries all 503 rows and is fetched by clients on
    metered connections; the schema lives in the published file's own `fields`
    block rather than in the key names.

    The headline is generated here rather than client-side so there is exactly
    one implementation of how a move is described. A second one, however small,
    drifts from app/engines/describe.py the first time either changes.
    """
    ticker = move["ticker"]
    company = names.get(ticker, ticker)

    described = describe(
        company=company,
        change_percent=move["change_percent"],
        indicators={
            "price_change_10d": move["period_percent"],
            "atr_percent": move["typical_percent"],
            # The scan does not compute a trend; this only affects the wording
            # when today and the fortnight are both flat, where "sideways" is
            # what the data actually shows.
            "trend": "sideways",
        },
    )

    row = {
        "t": ticker,
        "n": company,
        "s": sectors.get(ticker, ""),
        "p": move["price"],
        "c": move["change_percent"],
        "x": move["multiple"],
        "d": move["typical_percent"],
        "w": move["period_percent"],
        "h": described["headline"],
        "st": described["state"],
    }

    context = (attribution or {}).get(ticker)
    if context:
        sentence = explain_move(company, move["change_percent"], context)
        if sentence:
            row["ctx"] = sentence
        row["mkt"] = context["market_percent"]
        row["sec"] = context["sector_percent"]

    return row


def _latest_session(raw: pd.DataFrame) -> Optional[str]:
    """The date of the most recent bar, so the UI can say what it is showing."""
    try:
        return str(pd.to_datetime(raw.index[-1]).date())
    except Exception:  # noqa: BLE001
        return None
