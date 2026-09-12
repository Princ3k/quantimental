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

    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(result, indent=2) + "\n")

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
