"""
Refresh the ticker-to-CIK map from the SEC.

The map is an input rather than a cache — baked in for the same reason as
universe.json, so a scan never depends on a live download to name a company.
That means it goes stale unless somebody refreshes it, and this is how.

    python scripts/refresh_cik_map.py

Then commit the result. Worth doing when the log starts complaining about the
map's age, or after an index reshuffle. A company that changed ticker since the
last capture simply has no filings attached, and nothing else reports it.
"""

from __future__ import annotations

import logging
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.services.ingestion.filings import cik_map  # noqa: E402

logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")


def main() -> int:
    before, captured = (None, None)
    if cik_map.CACHE_PATH.exists():
        try:
            before, captured = cik_map._read(cik_map.CACHE_PATH)
        except Exception:  # noqa: BLE001
            pass

    mapping = cik_map.write()

    if before:
        added = set(mapping) - set(before)
        gone = set(before) - set(mapping)
        print(f"\nWas {len(before)} companies, captured {captured or 'unknown'}.")
        print(f"Now {len(mapping)}.")
        if added:
            print(f"  added ({len(added)}): {', '.join(sorted(added)[:12])}"
                  f"{' …' if len(added) > 12 else ''}")
        if gone:
            print(f"  gone  ({len(gone)}): {', '.join(sorted(gone)[:12])}"
                  f"{' …' if len(gone) > 12 else ''}")
        if not added and not gone:
            print("  no change in the set of tickers.")
    print(f"\nWrote {cik_map.CACHE_PATH}. Commit it.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
