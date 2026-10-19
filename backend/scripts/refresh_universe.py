#!/usr/bin/env python3
"""
Rebuild backend/data/universe.json from the current S&P 500 constituent list.

Run by hand, occasionally — the index changes a few times a year, and a stale
constituent simply produces no data and is skipped by the scan. It is a script
rather than a step in the scheduled workflow on purpose: a scrape of a
community-edited table should never be able to break the daily scan by
changing a column heading.

    python scripts/refresh_universe.py

Review the diff before committing it.
"""

from __future__ import annotations

import json
import logging
from datetime import date
from io import StringIO
from pathlib import Path

import httpx
import pandas as pd

logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
logger = logging.getLogger("refresh_universe")

SOURCE = "https://en.wikipedia.org/wiki/List_of_S%26P_500_companies"
OUTPUT = Path(__file__).resolve().parent.parent / "data" / "universe.json"

# Anything below this is a parse failure, not an unusually small index.
MIN_EXPECTED = 400


def _non_benchmark_rows(path: Path, refreshed: set[str]) -> list[dict]:
    """
    Rows in the existing universe that this script is not responsible for.

    Only entries without `benchmark` are kept, and only when the refreshed
    index does not already contain that ticker. Those two conditions are what
    stop a company that has just joined the S&P 500 from appearing twice, once
    as a constituent and once as a leftover addition.
    """
    if not path.exists():
        return []
    try:
        existing = json.loads(path.read_text())
    except (OSError, json.JSONDecodeError) as exc:
        # Refusing here would make a corrupt file unfixable by the very script
        # meant to rewrite it; losing additions is the lesser harm, said aloud.
        logger.warning("Could not read the existing universe (%s); additions not carried over.", exc)
        return []

    return [
        row
        for row in existing.get("constituents", [])
        if not row.get("benchmark", False) and row.get("ticker") not in refreshed
    ]


def main() -> int:
    try:
        response = httpx.get(SOURCE, timeout=30.0, headers={"User-Agent": "quantimental/1.0"})
        response.raise_for_status()
        table = pd.read_html(StringIO(response.text))[0]
    except Exception as exc:  # noqa: BLE001
        logger.error("Could not fetch the constituent list: %s", exc)
        return 1

    missing = {"Symbol", "Security", "GICS Sector"} - set(table.columns)
    if missing:
        logger.error("Table layout changed; missing columns: %s", ", ".join(sorted(missing)))
        return 1

    rows = [
        {
            # Yahoo spells class shares with a hyphen: BRK.B is BRK-B.
            "ticker": str(row["Symbol"]).strip().replace(".", "-"),
            "name": str(row["Security"]).strip(),
            "sector": str(row["GICS Sector"]).strip(),
            # This script only ever writes S&P 500 members, and the S&P 500 is
            # the basket "the market" refers to. Anything added to the universe
            # from another source must leave this out.
            "benchmark": True,
        }
        for _, row in table.iterrows()
    ]
    if len(rows) < MIN_EXPECTED:
        logger.error("Only parsed %d constituents; refusing to overwrite.", len(rows))
        return 1

    # Anything in the universe that this script did not put there is carried
    # over. The file is rewritten wholesale, so without this a ticker added
    # from any other source disappears the next time the S&P list is
    # refreshed — silently, and weeks later, with the scan simply covering
    # less than it did the day before.
    #
    # Rows are matched on ticker: a company that joins the index stops being
    # an addition and becomes a constituent, keeping its benchmark flag.
    kept = _non_benchmark_rows(OUTPUT, {row["ticker"] for row in rows})
    if kept:
        logger.info(
            "Carrying over %d ticker(s) from outside the index: %s",
            len(kept), ", ".join(sorted(row["ticker"] for row in kept)),
        )
    rows.extend(kept)
    rows.sort(key=lambda r: r["ticker"])

    OUTPUT.write_text(json.dumps({
        "source": f"S&P 500 constituents, {SOURCE}",
        "captured": date.today().isoformat(),
        "note": (
            "Baked in rather than scraped at runtime: the scan must not fail "
            "because Wikipedia changed a table layout. Refresh with "
            "scripts/refresh_universe.py."
        ),
        "count": len(rows),
        "constituents": rows,
    }, indent=2) + "\n")

    logger.info("Wrote %d constituents to %s", len(rows), OUTPUT)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
