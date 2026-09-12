"""
Signal endpoints.

Thin HTTP wrappers around LiveSignalService. All scoring logic lives in the
engines; these handlers only validate input, choose a depth, and time the call.
"""

from __future__ import annotations

import asyncio
import logging
import time
from typing import Literal

from fastapi import APIRouter, HTTPException, Query

from app.schemas.api import (
    AnalyzeMultipleRequest,
    AnalyzeMultipleResponse,
    AnalyzeRequest,
    AnalyzeResponse,
    SearchResponse,
)
from app.services.data.ticker_search_service import search_tickers
from app.services.signals.live_signal_service import (
    DEPTH_FAST,
    DEPTH_FULL,
    live_signal_service,
)

logger = logging.getLogger(__name__)

router = APIRouter()


@router.post("/analyze", response_model=AnalyzeResponse)
async def analyze_stock(request: AnalyzeRequest) -> AnalyzeResponse:
    """
    Full analysis of a single stock: technicals plus ML sentiment.

    This is the deep path — it queries Reddit, news and Twitter, so expect it
    to take a few seconds. Use `/batch` for dashboards.
    """
    started = time.perf_counter()

    try:
        signal = await live_signal_service.generate(request.ticker, depth=DEPTH_FULL)
    except Exception as exc:
        logger.error("Analysis failed for %s: %s", request.ticker, exc, exc_info=True)
        raise HTTPException(
            status_code=502,
            detail=f"Could not complete analysis for {request.ticker}. Please try again.",
        ) from exc

    elapsed_ms = (time.perf_counter() - started) * 1000

    if not signal.get("available"):
        # The ticker is well-formed but has no market data — that is a "not
        # found", not a server error.
        raise HTTPException(status_code=404, detail=signal.get("reason", "No data available."))

    return AnalyzeResponse(signal=signal, success=True, processing_time_ms=round(elapsed_ms, 1))


@router.post("/batch", response_model=AnalyzeMultipleResponse)
async def analyze_batch(
    request: AnalyzeMultipleRequest,
    depth: Literal["fast", "full"] = Query(
        DEPTH_FAST,
        description="'fast' skips sentiment for speed; 'full' runs the whole pipeline.",
    ),
) -> AnalyzeMultipleResponse:
    """
    Analyze several stocks at once.

    Defaults to `fast` depth, which is what dashboards want: real prices and
    technicals for a dozen tickers in about a second. Tickers that cannot be
    priced are returned in `failed` with a reason rather than silently dropped.
    """
    started = time.perf_counter()

    signals, failures = await live_signal_service.generate_many(request.tickers, depth=depth)

    elapsed_ms = (time.perf_counter() - started) * 1000

    return AnalyzeMultipleResponse(
        signals=signals,
        failed=failures,
        success=True,
        total_processed=len(signals),
        processing_time_ms=round(elapsed_ms, 1),
    )


@router.get("/search", response_model=SearchResponse)
async def search(
    q: str = Query("", max_length=64, description="Symbol or company name"),
    limit: int = Query(8, ge=1, le=20),
) -> SearchResponse:
    """
    Find tickers by symbol or company name.

    An empty query returns a curated list of well-known companies, so the
    search box is useful before the user has typed anything.
    """
    # search_tickers is blocking (network I/O), so keep it off the event loop.
    results = await asyncio.to_thread(search_tickers, q, limit)
    return SearchResponse(query=q, results=results)
