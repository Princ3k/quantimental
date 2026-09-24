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

    # Deliberately not next to the published JSON: Railway's root directory is
    # `backend`, so a file at the repository root is not in the deployed image.
    # Beside the other published artefacts, not inside backend/ — see
    # macro_signal_service._versus_history for why that distinction matters.
    _append_history(
        Path(__file__).resolve().parents[2] / "public" / "signal-desk-history.json", desk
    )

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


def _append_history(path: Path, desk: dict) -> None:
    """
    Append a compact daily record of the composite to a rolling history file.

    Kept as an explicit file rather than reconstructed from git history: the
    deployed API has no working tree to read, and depending on commit
    archaeology for product data is fragile in ways that only show up later.

    One record per day — the last write of each day wins, so the file grows by
    roughly 250 entries a year rather than 17,000.
    """
    composite = desk["composite"]
    today = datetime.now(timezone.utc).date().isoformat()

    record = {
        "date": today,
        "score": composite["score"],
        "label": composite["label"],
        "tone": composite["tone"],
    }

    history: list[dict] = []
    if path.exists():
        try:
            history = json.loads(path.read_text())
            if not isinstance(history, list):
                history = []
        except (json.JSONDecodeError, OSError) as exc:
            # A corrupt history should not block today's publish.
            logger.warning("Could not read history (%s); starting a new one", exc)
            history = []

    history = [entry for entry in history if entry.get("date") != today]
    history.append(record)
    history.sort(key=lambda e: e["date"])

    # Two years is plenty of context for "the most risk-off week since…" and
    # keeps the file small enough to ship to a browser.
    history = history[-730:]

    path.write_text(json.dumps(history, indent=2) + "\n")
    logger.info("History now holds %d days", len(history))


if __name__ == "__main__":
    raise SystemExit(main())
