"""
The explanation endpoint.

One stock, one factual sentence, and the numbers behind it. This is the part of
the API built to be embedded in somebody else's product, so it is deliberately
narrower than `/signals/analyze`: no scores, no ratings, no verdict, and no
field whose meaning could drift between releases.

Nothing here recommends anything. That is a product decision before it is a
compliance one — the buy/sell version was measured over five years and 3,792
observations, was 48.5% directionally accurate, and its only two significant
buckets pointed the wrong way. What survived that test is description, so
description is what this serves, and `DISCLOSURE` rides along on every
response to say so wherever the text ends up rendered.
"""

from __future__ import annotations

import asyncio
import logging
from typing import Any, Optional

from fastapi import APIRouter, HTTPException, Query

from app.schemas.explain import (
    Attribution,
    Coverage,
    Explanation,
    ExplanationBatch,
    Movement,
)
from app.services.data import snapshot_service

logger = logging.getLogger(__name__)

router = APIRouter()

# A whole index in one call is reasonable; a scrape of everything is not.
MAX_BATCH = 100


def _explanation(row: dict[str, Any], snapshot: snapshot_service.Snapshot) -> Explanation:
    """Turn one published snapshot row into the contract.

    The snapshot's keys are single letters because it carries 503 rows over a
    CDN. That is the right trade for a file and the wrong one for an API, so
    the names are spelled out here and the mapping lives in exactly this
    function.
    """
    return Explanation(
        ticker=row["t"],
        company=row.get("n"),
        as_of=snapshot.as_of,
        generated_at=snapshot.generated_at,
        explanation=row.get("h"),
        movement=Movement(
            price=row.get("p"),
            change_percent=row.get("c"),
            change_percent_2w=row.get("w"),
            typical_percent=row.get("d"),
            multiple_of_typical=row.get("x"),
            state=row.get("st"),
        ),
        attribution=Attribution(
            text=row.get("ctx"),
            market_percent=row.get("mkt"),
            sector=row.get("s"),
            sector_percent=row.get("sec"),
        ),
        coverage=Coverage(
            articles_per_day=row.get("v"),
            multiple_of_normal=row.get("vx"),
        ),
    )


async def _snapshot() -> snapshot_service.Snapshot:
    snapshot = await asyncio.to_thread(snapshot_service.get_snapshot)
    if snapshot is None:
        # Never fetched and the refresh failed. A cached copy would have been
        # served instead, so this really is "we have nothing".
        raise HTTPException(
            status_code=503,
            detail="No published scan is available yet. Try again shortly.",
        )
    return snapshot


@router.get("/{ticker}", response_model=Explanation)
async def explain_stock(ticker: str) -> Explanation:
    """
    What happened to one stock today, described rather than rated.

    Answers from the most recent published scan, so it is fast and every caller
    gets the same sentence. `as_of` names the session it describes.
    """
    symbol = ticker.strip().upper()
    snapshot = await _snapshot()

    row = snapshot.rows.get(symbol)
    if row is None:
        raise HTTPException(
            status_code=404,
            detail=f"{symbol} was not in the most recent scan.",
        )

    return _explanation(row, snapshot)


@router.get("", response_model=ExplanationBatch)
async def explain_stocks(
    tickers: str = Query(
        ...,
        description=f"Comma-separated symbols, up to {MAX_BATCH}.",
        examples=["AAPL,MSFT,NVDA"],
    ),
) -> ExplanationBatch:
    """
    The same thing for a list of stocks — a watchlist, a newsletter's universe.

    Unknown symbols come back in `not_found` rather than failing the call: a
    caller rendering forty positions should get the thirty-eight that worked.
    """
    requested: list[str] = []
    seen: set[str] = set()
    for raw in tickers.split(","):
        symbol = raw.strip().upper()
        if symbol and symbol not in seen:
            seen.add(symbol)
            requested.append(symbol)

    if not requested:
        raise HTTPException(status_code=422, detail="No tickers given.")
    if len(requested) > MAX_BATCH:
        raise HTTPException(
            status_code=422,
            detail=f"Too many tickers: {len(requested)} requested, {MAX_BATCH} is the limit.",
        )

    snapshot = await _snapshot()

    found = [
        _explanation(snapshot.rows[symbol], snapshot)
        for symbol in requested
        if symbol in snapshot.rows
    ]
    missing = [symbol for symbol in requested if symbol not in snapshot.rows]

    return ExplanationBatch(
        as_of=snapshot.as_of,
        generated_at=snapshot.generated_at,
        count=len(found),
        explanations=found,
        not_found=missing,
    )
