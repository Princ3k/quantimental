"""
Ticker Search Service

Backs the search box. Yahoo's search endpoint is the source of truth; a small
curated list of well-known companies powers the empty state so a new user has
somewhere obvious to start rather than a blank box.
"""

from __future__ import annotations

import logging
from typing import Any

import yfinance as yf

from app.services.data.market_data_service import _TTLCache

logger = logging.getLogger(__name__)

SEARCH_TTL_SECONDS = 15 * 60
MAX_RESULTS = 8

# Shown before the user types anything. Deliberately mainstream and diversified
# across sectors — these are for orientation, not recommendations.
POPULAR_TICKERS: list[dict[str, str]] = [
    {"ticker": "AAPL", "name": "Apple Inc."},
    {"ticker": "MSFT", "name": "Microsoft Corporation"},
    {"ticker": "NVDA", "name": "NVIDIA Corporation"},
    {"ticker": "GOOGL", "name": "Alphabet Inc."},
    {"ticker": "AMZN", "name": "Amazon.com, Inc."},
    {"ticker": "TSLA", "name": "Tesla, Inc."},
    {"ticker": "META", "name": "Meta Platforms, Inc."},
    {"ticker": "JPM", "name": "JPMorgan Chase & Co."},
    {"ticker": "V", "name": "Visa Inc."},
    {"ticker": "JNJ", "name": "Johnson & Johnson"},
    {"ticker": "WMT", "name": "Walmart Inc."},
    {"ticker": "DIS", "name": "The Walt Disney Company"},
]

_cache = _TTLCache(SEARCH_TTL_SECONDS)


def search_tickers(query: str, limit: int = MAX_RESULTS) -> list[dict[str, Any]]:
    """
    Search for tickers by symbol or company name.

    Returns an empty list rather than raising when the upstream search fails:
    a search box that silently finds nothing is a far better failure mode than
    one that shows an error dialog.
    """
    cleaned = query.strip()
    if not cleaned:
        return POPULAR_TICKERS[:limit]

    cache_key = f"{cleaned.lower()}:{limit}"
    cached = _cache.get(cache_key)
    if cached is not None:
        return cached

    results: list[dict[str, Any]] = []
    try:
        search = yf.Search(cleaned, max_results=limit)
        for quote in search.quotes or []:
            symbol = quote.get("symbol")
            if not symbol:
                continue
            results.append(
                {
                    "ticker": symbol,
                    "name": quote.get("longname") or quote.get("shortname") or symbol,
                    "exchange": quote.get("exchange"),
                    "type": quote.get("quoteType"),
                }
            )
    except Exception as exc:
        logger.warning("Ticker search failed for %r: %s", cleaned, exc)
        # Fall back to matching the curated list, so search still does
        # something useful when Yahoo's endpoint is unreachable.
        needle = cleaned.lower()
        results = [
            dict(entry)
            for entry in POPULAR_TICKERS
            if needle in entry["ticker"].lower() or needle in entry["name"].lower()
        ]

    results = results[:limit]
    _cache.set(cache_key, results)
    return results
