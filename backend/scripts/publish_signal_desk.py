#!/usr/bin/env python3
"""
Compute the Signal Desk and write it to a JSON file.

Run on a schedule by .github/workflows/signal-desk.yml, which commits the
result. The portfolio then fetches that static file instead of calling a live
server.

Why this exists: the desk payload is identical for every viewer and changes
slowly, so it is a *file*, not a request. Serving it statically costs nothing,
never cold-starts, and cannot go down independently of the site that embeds it
— which a free-tier server that sleeps after 15 minutes very much can.

    python scripts/publish_signal_desk.py public/signal-desk.json
"""

from __future__ import annotations

import json
import logging
import sys
from datetime import datetime, timezone
from pathlib import Path

# Make `app` importable when run from the repository's backend directory.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.services.data.macro_signal_service import macro_signal_service  # noqa: E402
from app.services.data.narrative_service import narrative_service  # noqa: E402

logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
logger = logging.getLogger("publish_signal_desk")

DEFAULT_OUTPUT = Path("public/signal-desk.json")


def main() -> int:
    output = Path(sys.argv[1]) if len(sys.argv) > 1 else DEFAULT_OUTPUT

    desk = macro_signal_service.get_desk()

    if not desk.get("available"):
        # Publishing an "unavailable" payload would replace a good file with a
        # broken one on any transient upstream failure. Keep the previous
        # snapshot instead — stale data beats no data for this panel.
        logger.error("Market data unavailable: %s", desk.get("reason"))
        logger.error("Leaving the existing file untouched.")
        return 1

    desk["narrative"] = narrative_service.generate(desk)
    desk["generated_at"] = datetime.now(timezone.utc).isoformat()

    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(desk, indent=2) + "\n")

    composite = desk["composite"]
    logger.info(
        "Wrote %s — %s %s/100, %d signals, narrative via %s",
        output,
        composite["label"],
        composite["score"],
        len(desk["signals"]),
        desk["narrative"]["source"],
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
