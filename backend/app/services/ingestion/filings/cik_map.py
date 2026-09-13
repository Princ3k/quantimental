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
import time
from pathlib import Path
from typing import Optional

from app.services.ingestion.filings.edgar_client import get_json

logger = logging.getLogger(__name__)

TICKER_MAP_URL = "https://www.sec.gov/files/company_tickers.json"

CACHE_PATH = Path(
    os.environ.get("SEC_CIK_CACHE_PATH")
    or Path(__file__).resolve().parents[5] / "data" / "cik-map.json"
)

# Companies are added and renamed, not hourly. A month is frequent enough to
# catch index changes and rare enough that the file is effectively static.
CACHE_TTL_SECONDS = 30 * 24 * 3600.0

_memory: Optional[dict[str, int]] = None
_lock = threading.Lock()


def _fresh(path: Path) -> bool:
    try:
        return (time.time() - path.stat().st_mtime) < CACHE_TTL_SECONDS
    except OSError:
        return False


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


def load(refresh: bool = False) -> dict[str, int]:
    """
    The whole mapping, from memory, then disk, then the SEC.

    A failed refresh falls back to the cached file however old it is. A stale
    map costs us the handful of companies that changed ticker since; no map at
    all costs every filing that day.
    """
    global _memory

    with _lock:
        if _memory is not None and not refresh:
            return _memory

    if not refresh and CACHE_PATH.exists() and _fresh(CACHE_PATH):
        try:
            mapping = json.loads(CACHE_PATH.read_text())
            with _lock:
                _memory = mapping
            return mapping
        except (ValueError, OSError) as exc:
            logger.warning("Cached CIK map unreadable (%s); refetching.", exc)

    try:
        mapping = _download()
    except Exception as exc:  # noqa: BLE001
        if CACHE_PATH.exists():
            logger.warning("Could not refresh the CIK map (%s); using the cached one.", exc)
            mapping = json.loads(CACHE_PATH.read_text())
        else:
            raise

    CACHE_PATH.parent.mkdir(parents=True, exist_ok=True)
    staged = CACHE_PATH.with_name(f".{CACHE_PATH.name}.tmp")
    staged.write_text(json.dumps(mapping, separators=(",", ":")))
    os.replace(staged, CACHE_PATH)

    with _lock:
        _memory = mapping
    logger.info("CIK map: %d companies", len(mapping))
    return mapping


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
