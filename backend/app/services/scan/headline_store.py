"""
The newest headline per stock, as of the last sweep.

Why this is separate from the attention archive
-----------------------------------------------

The archive answers "how much coverage, every day, forever". This answers
"what is the coverage about, right now". They have different shapes and
different lifetimes, and merging them would mean either bloating a file whose
every byte is read to compute a baseline, or teaching `baseline()` to skip
fields it does not care about. The archive's schema is load-bearing; this is
not. So they are two files.

Why it exists at all
--------------------

The sweep runs once, after the close. The other seven scans of the day carry
coverage forward from the archive rather than re-measuring, because measuring
costs three minutes of paced requests against a limiter that has cut us off
before. Headlines have to carry forward the same way or they would appear at
21:43 and vanish at the next morning's first scan — a site that shows you why
a stock is moving overnight and forgets by breakfast.

Why only the latest
-------------------

A day of headlines for the universe is roughly 50KB. Kept forever that is a
file nobody can parse quickly and nothing currently reads. The archive earns
its history because velocity is only meaningful against its own past; a
headline means what it says on the day it is published. When there is a
reason to keep them — and there may be, since this is equally unbuyable after
the fact — it should be a deliberate change with its own sharding, not a
side effect of this one.
"""

from __future__ import annotations

import json
import logging
import os
from pathlib import Path
from typing import Any, Optional

logger = logging.getLogger(__name__)

# Beside the attention archive, in the same private store and for the same
# reason: it is derived from a source we are not licensed to republish
# wholesale, and only one headline per stock ever reaches the public file.
STORE_PATH = Path(
    os.environ.get("HEADLINE_STORE_PATH")
    or Path(__file__).resolve().parents[3] / "data" / "headlines-latest.json"
)

# A headline longer than this is a summary paragraph that some publisher has
# put in the title field. Truncated on the way in, so the published file never
# carries one, and marked so a reader can tell the ellipsis is ours.
MAX_TITLE_CHARS = 180


def _trim(title: str) -> str:
    title = " ".join(title.split())
    if len(title) <= MAX_TITLE_CHARS:
        return title
    return title[: MAX_TITLE_CHARS - 1].rstrip() + "…"


def save(
    headlines: dict[str, dict[str, Any]],
    on: str,
    path: Optional[Path] = None,
) -> None:
    """
    Replace the store with this sweep's headlines.

    Replace, not merge. A ticker that has no headline today has either gone
    quiet or could not be reached, and in both cases last week's headline
    presented as current is worse than no headline at all.

    An empty measurement leaves the file alone, for the same reason the
    attention archive refuses one: the sweep failing is not the universe
    falling silent, and this is the file the next seven scans read.
    """
    path = path or STORE_PATH

    if not headlines:
        logger.error(
            "Refusing to write an empty headline store; keeping the previous "
            "file. A sweep that found nothing is a broken sweep, not a quiet "
            "news day."
        )
        return

    payload = {
        "as_of": on,
        "headlines": {
            ticker: {
                "title": _trim(entry["title"]),
                "publisher": entry.get("publisher") or "",
                "at": entry.get("at") or "",
            }
            for ticker, entry in headlines.items()
            if entry and entry.get("title")
        },
    }

    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(payload, indent=1, sort_keys=True) + "\n")
    tmp.replace(path)
    logger.info(
        "Headline store: %d headlines for %s -> %s",
        len(payload["headlines"]), on, path,
    )


def load(path: Optional[Path] = None) -> dict[str, Any]:
    """
    The stored headlines, or an empty store when there are none to read.

    Never raises. This is an enrichment on top of a price scan; a missing or
    corrupt file must cost the snapshot its headlines and nothing else.
    """
    # Resolved here rather than bound as a default, so that STORE_PATH stays
    # the single answer to "where is this file" even after something swaps it.
    path = path or STORE_PATH

    try:
        payload = json.loads(path.read_text())
    except FileNotFoundError:
        return {"as_of": None, "headlines": {}}
    except (OSError, ValueError) as exc:
        logger.warning("Could not read the headline store: %s", exc)
        return {"as_of": None, "headlines": {}}

    if not isinstance(payload, dict) or not isinstance(payload.get("headlines"), dict):
        logger.warning("Headline store is not in the expected shape; ignoring it.")
        return {"as_of": None, "headlines": {}}
    return payload


def latest(ticker: str, store: Optional[dict[str, Any]] = None) -> Optional[dict[str, Any]]:
    """One stock's stored headline, or None."""
    store = store if store is not None else load()
    entry = store.get("headlines", {}).get(ticker)
    return entry if entry and entry.get("title") else None
