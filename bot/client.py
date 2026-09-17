"""
The Quantimental API, as this bot uses it.

Only `/api/v1/explain` — the endpoint built to be embedded in somebody else's
product. Nothing here calls `/signals/analyze`: that path hits Reddit,
MarketAux and an LLM, costs twenty-five rate-limit units a request, and would
turn a channel of idle `/stock` calls into real upstream load.

One call serves every guild. The scheduled post deduplicates tickers across all
of them and asks once, so the cost is the number of distinct companies anyone
follows rather than the number of servers times the number they follow. Guild
fifty is free.
"""

from __future__ import annotations

import logging
import os
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Optional

import httpx

logger = logging.getLogger(__name__)

API_BASE = os.environ.get("QUANTIMENTAL_API", "https://api.thequantimental.com")

# The endpoint accepts a hundred at a time. Asking for more is a scrape.
MAX_PER_CALL = 100

TIMEOUT_SECONDS = 15.0


class ApiUnavailable(RuntimeError):
    """The API could not be reached, or answered with something unusable."""


@dataclass(frozen=True)
class Explanation:
    """One stock's row, as the API published it.

    Field names mirror the API's own rather than being re-abbreviated here, so
    that a reader comparing this to the documented contract does not have to
    hold a translation in their head.
    """

    ticker: str
    company: Optional[str]
    as_of: Optional[str]
    generated_at: Optional[str]
    explanation: Optional[str]
    movement: dict[str, Any]
    attribution: dict[str, Any]
    coverage: dict[str, Any]
    filing: Optional[dict[str, Any]]
    disclosure: str

    @classmethod
    def from_payload(cls, row: dict[str, Any]) -> "Explanation":
        return cls(
            ticker=row.get("ticker", ""),
            company=row.get("company"),
            as_of=row.get("as_of"),
            generated_at=row.get("generated_at"),
            explanation=row.get("explanation"),
            movement=row.get("movement") or {},
            attribution=row.get("attribution") or {},
            coverage=row.get("coverage") or {},
            filing=row.get("filing"),
            # Never defaulted to a string of our own. If the API stops sending
            # a disclosure we want that visible, not papered over with a copy
            # that no longer tracks whatever the API is actually saying.
            disclosure=row.get("disclosure", ""),
        )


@dataclass(frozen=True)
class Batch:
    """What one call returned, and what it could not answer."""

    as_of: Optional[str]
    generated_at: Optional[str]
    explanations: list[Explanation]
    not_found: list[str]

    def by_ticker(self) -> dict[str, Explanation]:
        return {e.ticker.upper(): e for e in self.explanations}


def staleness_hours(generated_at: Optional[str]) -> Optional[float]:
    """How old the scan behind a response is, in hours.

    Worth measuring rather than trusting. The API serves a cached copy of the
    published snapshot and, when a refresh fails, keeps serving the last good
    one indefinitely — the failure is logged at warning level, so nothing
    raises and nothing pages. A consumer that does not check `generated_at`
    cannot tell an hourly scan from a broken one.
    """
    if not generated_at:
        return None
    try:
        when = datetime.fromisoformat(generated_at)
    except ValueError:
        return None
    if when.tzinfo is None:
        when = when.replace(tzinfo=timezone.utc)
    return (datetime.now(timezone.utc) - when).total_seconds() / 3600.0


class QuantimentalClient:
    """Thin, synchronous-free wrapper. One instance for the bot's lifetime."""

    def __init__(self, base: str = API_BASE, timeout: float = TIMEOUT_SECONDS) -> None:
        self._base = base.rstrip("/")
        self._timeout = timeout

    async def explain(self, tickers: list[str]) -> Batch:
        """Explanations for up to MAX_PER_CALL tickers, in one request."""
        wanted = _normalise(tickers)
        if not wanted:
            return Batch(None, None, [], [])
        if len(wanted) > MAX_PER_CALL:
            raise ValueError(f"{len(wanted)} tickers; the endpoint caps at {MAX_PER_CALL}")

        url = f"{self._base}/api/v1/explain"
        try:
            async with httpx.AsyncClient(timeout=self._timeout) as http:
                response = await http.get(url, params={"tickers": ",".join(wanted)})
                response.raise_for_status()
                payload = response.json()
        except Exception as exc:  # noqa: BLE001
            logger.warning("explain(%d tickers) failed: %s", len(wanted), exc)
            raise ApiUnavailable(str(exc)) from exc

        rows = payload.get("explanations") or []
        return Batch(
            as_of=payload.get("as_of"),
            generated_at=payload.get("generated_at"),
            explanations=[Explanation.from_payload(r) for r in rows],
            not_found=[t.upper() for t in (payload.get("not_found") or [])],
        )


def _normalise(tickers: list[str]) -> list[str]:
    """Upper-cased, de-duplicated, order preserved."""
    seen: dict[str, None] = {}
    for raw in tickers:
        cleaned = (raw or "").strip().upper()
        if cleaned:
            seen.setdefault(cleaned, None)
    return list(seen)
