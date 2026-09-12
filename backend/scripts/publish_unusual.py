#!/usr/bin/env python3
"""
Scan the universe for unusual moves and write the result to a JSON file.

Run on a schedule by .github/workflows/unusual-scan.yml, which commits the
result. The frontend fetches that static file rather than calling a live
server.

Same reasoning as publish_signal_desk.py: this payload is identical for every
viewer and changes only when the market does, so it is a *file*, not a request.
Serving it statically costs nothing, never cold-starts, and does not put a
503-ticker download on the critical path of somebody opening the page.

    python scripts/publish_unusual.py public/unusual.json

Writes a second file beside it — `snapshot.json` — carrying every measured
ticker rather than only the notable ones. That is what the per-stock pages and
any home-screen widget read: a page for AAPL needs AAPL's numbers whether or
not AAPL had an interesting day, and fetching them per visitor would put an
unauthenticated API call behind every page view and every widget refresh.
"""

from __future__ import annotations

import json
import logging
import sys
from pathlib import Path

# Make `app` importable when run from the repository's backend directory.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.services.scan.unusual_service import scan  # noqa: E402

logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
logger = logging.getLogger("publish_unusual")

DEFAULT_OUTPUT = Path("public/unusual.json")


def main() -> int:
    output = Path(sys.argv[1]) if len(sys.argv) > 1 else DEFAULT_OUTPUT

    result = scan()

    if not result.get("available"):
        # Publishing an "unavailable" payload would replace a good file with a
        # broken one on any transient upstream failure. Keep the previous
        # snapshot instead — stale data beats no data here.
        logger.error("Scan failed: %s", result.get("reason"))
        logger.error("Leaving the existing file untouched.")
        return 1

    # A scan that measured almost nothing usually means the download returned
    # empty frames rather than that the market vanished. Publishing it would
    # quietly replace a real reading with "0 of 503 scanned".
    if result["scanned"] < result["universe"] * 0.5:
        logger.error(
            "Only %d of %d tickers produced usable data; not publishing.",
            result["scanned"], result["universe"],
        )
        return 1

    # The snapshot is an order of magnitude larger than the feed and is read by
    # different clients, so it ships as its own file. Anything fetching the
    # feed for five headlines should not pay for 503 rows.
    snapshot_rows = result.pop("snapshot", [])

    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(result, indent=2) + "\n")

    snapshot_path = output.parent / "snapshot.json"
    snapshot_path.write_text(json.dumps({
        "as_of": result["as_of"],
        "generated_at": result["generated_at"],
        "count": len(snapshot_rows),
        # Short keys keep this small; this block is the schema.
        "fields": {
            "t": "ticker", "n": "company name", "s": "sector",
            "p": "price", "c": "change percent today",
            "x": "multiple of this stock's typical daily move",
            "d": "typical daily move percent", "w": "change percent over two weeks",
            "h": "one-sentence description", "st": "rising | falling | steady",
        },
        "stocks": snapshot_rows,
    }, separators=(",", ":")) + "\n")

    logger.info("Wrote %s — %d tickers", snapshot_path, len(snapshot_rows))
    logger.info(
        "Scanned %d tickers for %s: %d unusual (%d up, %d down)",
        result["scanned"], result["as_of"],
        result["unusual_count"], result["rising"], result["falling"],
    )
    for move in result["movers"][:5]:
        logger.info("  %s", move["headline"])

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
