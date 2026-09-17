"""
Ticker to CIK, which is how EDGAR names a company.

EDGAR indexes everything by Central Index Key, so nothing else here works until
a ticker can be turned into one. The SEC publishes the whole mapping as a
single file — about 10,400 companies, 800KB — which is small enough to hold in
memory and slow enough to change that refetching it more than monthly is waste.

One wrinkle worth naming: EDGAR writes class shares with a dash where the price
feed uses a dot. BRK.B here is BRK-B there. Every lookup tries both, because
missing the ~20 dual-class names in the index would be a silent hole rather
than an error.
"""

from __future__ import annotations

import json
import logging
import os
import threading
from datetime import date
from pathlib import Path
from typing import Optional

from app.services.ingestion.filings.edgar_client import get_json

logger = logging.getLogger(__name__)

TICKER_MAP_URL = "https://www.sec.gov/files/company_tickers.json"

CACHE_PATH = Path(
    os.environ.get("SEC_CIK_CACHE_PATH")
    or Path(__file__).resolve().parents[4] / "data" / "cik-map.json"
)

# How old the file may get before the log starts complaining. Companies are
# added and renamed, not hourly, so a month is frequent enough to catch index
# changes and rare enough that the file is effectively static.
STALE_AFTER_DAYS = 30

_memory: Optional[dict[str, int]] = None
_lock = threading.Lock()


def _download() -> dict[str, int]:
    raw = get_json(TICKER_MAP_URL)
    mapping = {
        str(row["ticker"]).upper(): int(row["cik_str"])
        for row in raw.values()
        if row.get("ticker") and row.get("cik_str")
    }
    if not mapping:
        raise RuntimeError("The SEC ticker file parsed to nothing.")
    return mapping


def write(path: Path = CACHE_PATH) -> dict[str, int]:
    """Fetch the mapping from the SEC and write it down. Used by the refresh script."""
    mapping = _download()
    path.parent.mkdir(parents=True, exist_ok=True)
    staged = path.with_name(f".{path.name}.tmp")
    staged.write_text(
        json.dumps(
            {
                "source": TICKER_MAP_URL,
                "captured": date.today().isoformat(),
                "note": (
                    "Baked in rather than fetched at runtime, for the same reason as "
                    "universe.json: the scan must not depend on a live download to "
                    "name a company. Refresh with scripts/refresh_cik_map.py."
                ),
                "count": len(mapping),
                "ciks": mapping,
            },
            separators=(",", ":"),
        )
    )
    os.replace(staged, path)
    logger.info("Wrote %s — %d companies", path, len(mapping))
    return mapping


def _read(path: Path) -> tuple[dict[str, int], Optional[str]]:
    """The mapping and the day it was captured, tolerating the older flat shape."""
    payload = json.loads(path.read_text())
    if isinstance(payload.get("ciks"), dict):
        return payload["ciks"], payload.get("captured")
    # The first version of this file was a bare {ticker: cik} object with no
    # date in it. Readable, just undatable.
    return payload, None


def load(refresh: bool = False) -> dict[str, int]:
    """
    The whole mapping.

    Read from the file rather than fetched, and deliberately not on a runtime
    TTL. The previous version compared the file's mtime against a month, which
    is always false under CI: `actions/checkout` sets mtime to checkout time,
    so the committed map looked newly written on every single run and the
    refresh it promised never once happened.

    Keying the age on a date inside the file fixes the check, but a runtime
    refresh is the wrong shape anyway — once the file did age past the limit,
    every scan of the day would pull the same 800KB from the SEC to reach the
    same answer. So this is an input like universe.json: refreshed by running
    a script, and noisy in the log when it is getting old.
    """
    global _memory

    with _lock:
        if _memory is not None and not refresh:
            return _memory

    if refresh or not CACHE_PATH.exists():
        mapping = write()
        with _lock:
            _memory = mapping
        return mapping

    try:
        mapping, captured = _read(CACHE_PATH)
    except (ValueError, OSError, AttributeError) as exc:
        logger.warning("CIK map at %s unreadable (%s); fetching a fresh one.", CACHE_PATH, exc)
        mapping = write()
        with _lock:
            _memory = mapping
        return mapping

    age = _age_days(captured)
    if age is None:
        logger.warning(
            "CIK map carries no capture date, so its age is unknown. "
            "Refresh it with scripts/refresh_cik_map.py."
        )
    elif age > STALE_AFTER_DAYS:
        # Loud rather than silent: a company that changed ticker since simply
        # stops having filings attached, and nothing else would report it.
        logger.warning(
            "CIK map is %d days old (captured %s). Companies that changed ticker "
            "since will silently have no filings. Refresh with "
            "scripts/refresh_cik_map.py.",
            age, captured,
        )
    else:
        logger.info("CIK map: %d companies, captured %s", len(mapping), captured)

    with _lock:
        _memory = mapping
    return mapping


def _age_days(captured: Optional[str]) -> Optional[int]:
    if not captured:
        return None
    try:
        return (date.today() - date.fromisoformat(captured)).days
    except ValueError:
        return None


def cik_for(ticker: str, mapping: Optional[dict[str, int]] = None) -> Optional[int]:
    """One ticker's CIK, trying the dash spelling EDGAR uses for class shares."""
    table = mapping if mapping is not None else load()
    symbol = ticker.strip().upper()
    return table.get(symbol) or table.get(symbol.replace(".", "-"))


def ciks_for(tickers: list[str]) -> dict[str, int]:
    """Every ticker we can name, skipping those EDGAR does not list."""
    table = load()
    found = {t: cik_for(t, table) for t in tickers}
    return {t: cik for t, cik in found.items() if cik is not None}


def reset_cache() -> None:
    """Drop the in-memory map. For tests."""
    global _memory
    with _lock:
        _memory = None
