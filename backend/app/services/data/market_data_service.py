"""
Market Data Service

Fetches price and company data from Yahoo Finance and hands it to the Quant
Engine for indicator calculation.

Two things matter here beyond the fetch itself:

1. **Caching.** The dashboard asks for ~15 tickers and refreshes periodically.
   Without a cache that is 15 uncached Yahoo calls per refresh per viewer,
   which gets rate-limited quickly. Quotes are cached briefly; company profiles
   are cached for much longer because they barely change.

2. **Honest failure.** When Yahoo has no data for a symbol we return a result
   with `available: False` rather than inventing numbers. The API layer turns
   that into a clear "we couldn't price this" instead of a fabricated signal.
"""

from __future__ import annotations

import logging
import threading
import time
from datetime import datetime, timezone
from typing import Any, Optional

import pandas as pd
import yfinance as yf

from app.engines.quant import quant_engine
from app.utils.ttl_cache import TTLCache

logger = logging.getLogger(__name__)

# A year of daily bars. Two reasons for this specific window:
#   - SMA-200 and therefore Golden/Death Cross detection need 200 bars.
#   - Wilder-smoothed indicators (RSI/ATR/ADX) and MACD need ~125 bars before
#     their warm-up bias decays to nothing.
# Three months, which this service used to request, satisfied neither.
HISTORY_PERIOD = "1y"

QUOTE_TTL_SECONDS = 60
PROFILE_TTL_SECONDS = 24 * 60 * 60


# Kept as a module-level alias so existing references still resolve.
_TTLCache = TTLCache


class MarketDataService:
    """Fetches real market data from Yahoo Finance."""

    def __init__(self) -> None:
        self._quote_cache = _TTLCache(QUOTE_TTL_SECONDS)
        self._profile_cache = _TTLCache(PROFILE_TTL_SECONDS)

    # ------------------------------------------------------------------
    # Fetching
    # ------------------------------------------------------------------

    def get_historical_data(self, ticker: str, period: str = HISTORY_PERIOD) -> pd.DataFrame:
        """
        Fetch daily OHLCV bars. Returns an empty frame when unavailable.

        Rows with no closing price are dropped. Yahoo returns a row for the
        current session as soon as it opens, with volume but a NaN close, so
        during market hours the newest bar is incomplete. Left in place, that
        NaN propagates through every indicator and the whole signal becomes
        NaN, so the partial bar is removed before any maths happens.
        """
        try:
            history = yf.Ticker(ticker).history(period=period, auto_adjust=True)
        except Exception as exc:
            logger.error("Error fetching history for %s: %s", ticker, exc)
            return pd.DataFrame()

        if history.empty:
            logger.warning("No price history returned for %s", ticker)
            return history

        if "Close" in history:
            cleaned = history.dropna(subset=["Close"])
            dropped = len(history) - len(cleaned)
            if dropped:
                logger.debug("Dropped %d incomplete bar(s) for %s", dropped, ticker)
            return cleaned

        return history

    def get_company_info(self, ticker: str) -> dict[str, Any]:
        """
        Fetch the company profile (name, sector, market cap).

        Cached for a day: this data is effectively static, and `yf.Ticker.info`
        is by far the slowest call in the service.
        """
        symbol = ticker.upper()
        cached = self._profile_cache.get(symbol)
        if cached is not None:
            return cached

        profile = {"name": symbol, "sector": None, "industry": None, "market_cap": None}
        try:
            info = yf.Ticker(symbol).info or {}
            profile = {
                "name": info.get("longName") or info.get("shortName") or symbol,
                "sector": info.get("sector"),
                "industry": info.get("industry"),
                "market_cap": info.get("marketCap"),
            }
        except Exception as exc:
            # A missing profile is cosmetic — the ticker symbol is a fine
            # fallback name, so log and carry on rather than failing the quote.
            logger.warning("Could not fetch company profile for %s: %s", symbol, exc)

        self._profile_cache.set(symbol, profile)
        return profile

    # ------------------------------------------------------------------
    # Composition
    # ------------------------------------------------------------------

    def get_quote(self, ticker: str) -> dict[str, Any]:
        """
        Fetch a complete quote: price, company profile, and technical indicators.

        Returns a dict with `available` set to False when Yahoo has no usable
        data for the symbol. Callers must check it before reading `price`.
        """
        symbol = ticker.upper()

        cached = self._quote_cache.get(symbol)
        if cached is not None:
            return cached

        history = self.get_historical_data(symbol)

        if history.empty or "Close" not in history:
            result = {
                "ticker": symbol,
                "available": False,
                "reason": f"No market data available for {symbol}. Check the symbol is correct.",
                "price": None,
                "company": {"name": symbol},
                "indicators": {},
                "timestamp": datetime.now(timezone.utc).isoformat(),
            }
            # Cache the miss too: a bad symbol shouldn't re-hit Yahoo on every
            # keystroke of a search box.
            self._quote_cache.set(symbol, result)
            return result

        closes = history["Close"].to_numpy(dtype=float)
        highs = history["High"].to_numpy(dtype=float) if "High" in history else None
        lows = history["Low"].to_numpy(dtype=float) if "Low" in history else None
        volumes = history["Volume"].to_numpy(dtype=float) if "Volume" in history else None

        indicators = quant_engine.calculate_indicators(closes, highs, lows, volumes)

        # Recent closes power the sparkline on each card. Sent as plain floats
        # so the frontend needs no date handling for a decorative chart.
        price_history = [round(float(c), 2) for c in closes[-30:]]

        result = {
            "ticker": symbol,
            "available": True,
            "price": float(closes[-1]),
            "previous_close": float(closes[-2]) if len(closes) > 1 else None,
            "company": self.get_company_info(symbol),
            "indicators": indicators,
            "price_history": price_history,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }
        self._quote_cache.set(symbol, result)
        return result

    def clear_cache(self) -> None:
        """Drop all cached data. Used by tests and the admin refresh path."""
        self._quote_cache.clear()
        self._profile_cache.clear()


market_data_service = MarketDataService()
