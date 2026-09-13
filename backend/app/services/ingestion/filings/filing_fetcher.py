"""
Which of our companies filed an 8-K for a given session, and about what.

Two requests find the candidates and a handful more describe them. EDGAR
publishes a daily index of everything filed on a date, so one fetch narrows
10,400 possible filers to the twenty-odd in our universe, and only those get
looked up individually. The alternative — asking every company in turn — is 503
requests to answer a question two can.

Session, not date
-----------------

A filing accepted at 16:20 belongs to tomorrow's session, not today's: the
market was shut when it landed. So the sweep reads two days of index — the
session itself and the trading day before it — and keeps whatever falls in the
window between the two closes. Getting this wrong would put earnings filed
after Monday's bell against Monday's flat tape instead of Tuesday's move, which
is precisely the case the feature exists to cover.

Acceptance timestamps are UTC. They are converted at a fixed -4, correct for
EDT and an hour out through the winter; the error only reaches a filing
accepted between 16:00 and 17:00 ET on a December afternoon, which is a
narrower failure than a timezone database is worth here.
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from typing import Any, Optional

import httpx

from app.services.ingestion.filings import cik_map, items as item_table
from app.services.ingestion.filings.edgar_client import (
    EdgarBlocked,
    get_json,
    get_text,
    new_client,
)

logger = logging.getLogger(__name__)

DAILY_INDEX_URL = (
    "https://www.sec.gov/Archives/edgar/daily-index/{year}/QTR{quarter}/form.{stamp}.idx"
)
SUBMISSIONS_URL = "https://data.sec.gov/submissions/CIK{cik:010d}.json"
DOCUMENT_URL = "https://www.sec.gov/Archives/edgar/data/{cik}/{accession}/{document}"

FORM = "8-K"
MARKET_CLOSE_HOUR_ET = 16
ET_OFFSET_HOURS = -4

# How far back to look for the previous trading day before giving up. Four
# clears a long weekend; anything longer is a market closure this will not see.
MAX_LOOKBACK_DAYS = 5

# A row of the daily index: form, company (spaces and all), CIK, date, path.
_INDEX_ROW = re.compile(r"^(\S+)\s+(.+?)\s+(\d+)\s+(\d{8})\s+(\S+)\s*$")


@dataclass
class Filing:
    """One 8-K, reduced to what a reader needs."""

    ticker: str
    items: list[str]
    phrase: Optional[str]
    accepted_at: str
    session: str
    url: Optional[str] = None

    def as_row(self) -> dict[str, Any]:
        """The compact form carried in snapshot.json."""
        return {
            "i": self.items,
            "p": self.phrase,
            "a": self.accepted_at,
            "u": self.url,
        }


def _quarter(day: date) -> int:
    return (day.month - 1) // 3 + 1


def _index_url(day: date) -> str:
    return DAILY_INDEX_URL.format(
        year=day.year, quarter=_quarter(day), stamp=day.strftime("%Y%m%d")
    )


def filers_on(day: date, client: Optional[httpx.Client] = None) -> set[int]:
    """
    Every CIK that filed an 8-K on one date.

    A date the market was shut has no index and returns nothing — that is the
    normal answer for a weekend, not a failure.
    """
    try:
        body = get_text(_index_url(day), client=client)
    except EdgarBlocked:
        raise
    except Exception as exc:  # noqa: BLE001
        logger.debug("No daily index for %s (%s)", day, exc)
        return set()

    ciks: set[int] = set()
    for line in body.splitlines():
        match = _INDEX_ROW.match(line)
        if match and match.group(1) == FORM:
            ciks.add(int(match.group(3)))
    return ciks


def _previous_trading_day(
    session: date, client: Optional[httpx.Client] = None
) -> tuple[Optional[date], set[int]]:
    """The last day before `session` that EDGAR published an index for."""
    for back in range(1, MAX_LOOKBACK_DAYS + 1):
        day = session - timedelta(days=back)
        if day.weekday() >= 5:
            continue
        filers = filers_on(day, client=client)
        if filers:
            return day, filers
    return None, set()


def _session_of(accepted_utc: str) -> Optional[date]:
    """The trading session a filing landed in, by its acceptance time."""
    try:
        stamp = datetime.fromisoformat(accepted_utc.replace("Z", "+00:00"))
    except ValueError:
        return None

    et = stamp.astimezone(timezone.utc) + timedelta(hours=ET_OFFSET_HOURS)
    day = et.date()
    if et.hour >= MARKET_CLOSE_HOUR_ET:
        day += timedelta(days=1)
    # A filing accepted over a weekend belongs to Monday.
    while day.weekday() >= 5:
        day += timedelta(days=1)
    return day


def _filings_for_company(
    ticker: str, cik: int, session: date, client: Optional[httpx.Client]
) -> Optional[Filing]:
    """This company's 8-K for that session, if it had one."""
    try:
        recent = get_json(SUBMISSIONS_URL.format(cik=cik), client=client)["filings"]["recent"]
    except EdgarBlocked:
        raise
    except Exception as exc:  # noqa: BLE001
        logger.warning("Could not read filings for %s: %s", ticker, exc)
        return None

    forms = recent.get("form") or []
    for index, form in enumerate(forms):
        if form != FORM:
            continue
        accepted = (recent.get("acceptanceDateTime") or [])[index]
        if _session_of(accepted) != session:
            continue

        raw = (recent.get("items") or [])[index] or ""
        codes = item_table.meaningful([piece for piece in raw.split(",")])
        return Filing(
            ticker=ticker,
            items=codes,
            phrase=item_table.describe(codes),
            accepted_at=accepted,
            session=session.isoformat(),
            url=_document_url(cik, recent, index),
        )
    return None


def _document_url(cik: int, recent: dict[str, Any], index: int) -> Optional[str]:
    """
    A link to the filing itself on EDGAR.

    Item 8.01 is "Other Events", which is a quarter of what gets filed and says
    nothing at all — the code carries no meaning, only the text does. Rather
    than dress that up or drop it, the reader gets the document. It also means
    every phrase here is checkable against its source in one click, which is
    the same reason the method page publishes the backtest.
    """
    accession = (recent.get("accessionNumber") or [])[index]
    document = (recent.get("primaryDocument") or [])[index]
    if not accession or not document:
        return None
    return DOCUMENT_URL.format(
        cik=cik, accession=accession.replace("-", ""), document=document
    )


def filings_for_session(tickers: list[str], session: str) -> dict[str, Filing]:
    """
    Every 8-K our universe filed for one session, keyed by ticker.

    Returns what it managed to read. EDGAR being unreachable means a scan with
    no filings on it, never a scan that does not publish — the price data is
    the product and this decorates it.
    """
    try:
        day = date.fromisoformat(session)
    except ValueError:
        logger.warning("Not a session date: %r", session)
        return {}

    try:
        ciks = cik_map.ciks_for(tickers)
    except Exception as exc:  # noqa: BLE001
        logger.warning("No CIK map, so no filings this run: %s", exc)
        return {}

    by_cik = {cik: ticker for ticker, cik in ciks.items()}
    found: dict[str, Filing] = {}

    with new_client() as client:
        try:
            candidates = filers_on(day, client=client)
            previous_day, previous_filers = _previous_trading_day(day, client=client)
            if previous_day:
                candidates |= previous_filers
        except EdgarBlocked as exc:
            logger.error("%s", exc)
            return {}

        ours = candidates & set(by_cik)
        logger.info(
            "EDGAR: %d 8-K filers for %s, %d of them ours", len(candidates), session, len(ours)
        )

        for cik in sorted(ours):
            ticker = by_cik[cik]
            try:
                filing = _filings_for_company(ticker, cik, day, client)
            except EdgarBlocked as exc:
                logger.error("%s", exc)
                break
            if filing:
                found[ticker] = filing

    logger.info("Filings attached to this session: %d", len(found))
    return found
