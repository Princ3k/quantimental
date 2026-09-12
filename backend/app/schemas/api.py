"""
API request/response schemas.

Validation lives here rather than in the route bodies, so a malformed ticker is
rejected at the edge with a clear 422 instead of becoming a confusing failure
deeper in the stack (or, worse, an outbound request to Yahoo for "'; DROP").
"""

from __future__ import annotations

import re
from typing import Any, Optional

from pydantic import BaseModel, Field, field_validator

# Covers ordinary US symbols plus the dot/hyphen classes (BRK.B, RDS-A).
TICKER_PATTERN = re.compile(r"^[A-Z][A-Z0-9.\-]{0,9}$")

# A batch request fans out to one Yahoo call per ticker, run concurrently and
# served from a 60s cache. Capping it keeps a single request from being able to
# trigger a rate-limit ban for everyone; 60 covers a serious watchlist while
# still completing in a couple of seconds cold.
MAX_BATCH_SIZE = 60


def _normalize_ticker(value: str) -> str:
    """Uppercase, trim, and validate a single ticker symbol."""
    symbol = value.strip().upper()
    if not TICKER_PATTERN.match(symbol):
        raise ValueError(
            f"'{value}' is not a valid ticker symbol. "
            "Use 1-10 letters or digits, for example AAPL or BRK.B."
        )
    return symbol


class AnalyzeRequest(BaseModel):
    """Request a full analysis of one ticker."""

    ticker: str = Field(..., description="Stock symbol, e.g. AAPL")

    @field_validator("ticker")
    @classmethod
    def validate_ticker(cls, value: str) -> str:
        return _normalize_ticker(value)


class AnalyzeMultipleRequest(BaseModel):
    """Request analyses for several tickers at once."""

    tickers: list[str] = Field(..., min_length=1, max_length=MAX_BATCH_SIZE)

    @field_validator("tickers")
    @classmethod
    def validate_tickers(cls, values: list[str]) -> list[str]:
        symbols = [_normalize_ticker(v) for v in values]
        # Preserve caller order while removing duplicates, so asking for
        # [AAPL, AAPL] costs one fetch rather than two.
        return list(dict.fromkeys(symbols))


class SignalFailure(BaseModel):
    """A ticker that could not be analyzed, and why."""

    ticker: str
    reason: str


class AnalyzeResponse(BaseModel):
    """Response for a single-ticker analysis."""

    signal: Optional[dict[str, Any]] = None
    success: bool
    error: Optional[str] = None
    processing_time_ms: float


class AnalyzeMultipleResponse(BaseModel):
    """Response for a batch analysis."""

    signals: list[dict[str, Any]]
    failed: list[SignalFailure]
    success: bool
    total_processed: int
    processing_time_ms: float


class SearchResult(BaseModel):
    """One match from ticker search."""

    ticker: str
    name: str
    exchange: Optional[str] = None
    type: Optional[str] = None


class SearchResponse(BaseModel):
    """Response for a ticker search query."""

    query: str
    results: list[SearchResult]
