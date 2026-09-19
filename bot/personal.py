"""
Watchlists that belong to a person rather than to a server.

Asked for by the first server that installed the bot: members wanting their own
list rather than the admin-managed one the daily post uses.

**The identity question, and how it is answered.** Keeping a list per person
means recognising that person between commands, which is the one thing the rest
of this bot deliberately avoids — the privacy policy says no user ids, and it
says so because that has been true. So the key here is a one-way digest of the
Discord id, never the id itself. The file is ticker symbols against digests; it
cannot be read as a list of who uses this, and it cannot produce one.

That is pseudonymity, not anonymity, and the policy says so in those words.
Discord ids are not secret, so someone who already holds yours can test for it.
What the digest buys is that the file is not a directory — not that a
determined party with a specific person in mind is defeated by it.

The practical consequence is the feature boundary: a digest cannot be reversed,
so this cannot send anyone a message. Nothing here reaches a person who has not
just typed a command. Push delivery would need the real id, and that is a
separate decision with its own consent, not something to slide in behind this.
"""

from __future__ import annotations

import hashlib
import json
import logging
import os
import threading
from pathlib import Path
from typing import Any, Optional

from store import clean

logger = logging.getLogger(__name__)


def default_path() -> Path:
    """Beside the other state, on the same volume."""
    mount = os.environ.get("RAILWAY_VOLUME_MOUNT_PATH")
    if mount:
        return Path(mount) / "personal.json"
    return Path("/data/personal.json")


PERSONAL_PATH = (
    Path(os.environ["PERSONAL_PATH"])
    if os.environ.get("PERSONAL_PATH")
    else default_path()
)

# Same cap as a server list. Long enough for a real watchlist, short enough that
# one person cannot make the shared lookup call exceed the endpoint's limit.
MAX_PER_PERSON = 25

# A full SHA-256 rather than the shortened digest misses.json uses. That one
# only has to count distinct servers, so collisions are harmless; here a
# collision would handed someone else's watchlist to the wrong person.
def tag(user_id: int) -> str:
    return hashlib.sha256(str(user_id).encode()).hexdigest()


class Personal:
    """Digest -> tickers. Nothing else is stored about anyone."""

    def __init__(self, path: Path = PERSONAL_PATH) -> None:
        self.path = path
        self._lock = threading.Lock()
        self._rows: dict[str, list[str]] = self._read()

    def get(self, user_id: int) -> list[str]:
        with self._lock:
            return list(self._rows.get(tag(user_id), []))

    def add(self, user_id: int, ticker: str) -> tuple[bool, str]:
        symbol = clean(ticker)
        if not symbol:
            return False, "That does not look like a ticker."
        key = tag(user_id)
        with self._lock:
            current = self._rows.setdefault(key, [])
            if symbol in current:
                return False, f"{symbol} is already on your list."
            if len(current) >= MAX_PER_PERSON:
                return False, f"Your list is at the limit of {MAX_PER_PERSON}."
            current.append(symbol)
            self._write()
        return True, f"Added {symbol} to your list."

    def remove(self, user_id: int, ticker: str) -> tuple[bool, str]:
        symbol = clean(ticker)
        key = tag(user_id)
        with self._lock:
            current = self._rows.get(key, [])
            if symbol not in current:
                return False, f"{symbol or ticker.upper()} is not on your list."
            current.remove(symbol)
            if not current:
                # An empty list is an empty row. Leaving the digest behind would
                # mean the file still recorded that this person had ever used
                # the bot, which is more than the policy says is kept.
                self._rows.pop(key, None)
            self._write()
        return True, f"Removed {symbol} from your list."

    def clear(self, user_id: int) -> bool:
        """Delete everything stored for this person. Returns whether there was any."""
        key = tag(user_id)
        with self._lock:
            existed = key in self._rows
            self._rows.pop(key, None)
            if existed:
                self._write()
        return existed

    def people(self) -> int:
        """How many lists exist. A count, never the keys."""
        with self._lock:
            return len(self._rows)

    def _read(self) -> dict[str, list[str]]:
        try:
            raw = json.loads(self.path.read_text())
        except FileNotFoundError:
            return {}
        except Exception as exc:  # noqa: BLE001
            logger.error("Personal list file at %s is unreadable: %s", self.path, exc)
            return {}
        rows = raw.get("lists") if isinstance(raw, dict) else None
        if not isinstance(rows, dict):
            return {}
        return {
            str(k): [str(t) for t in v]
            for k, v in rows.items()
            if isinstance(v, list) and v
        }

    def _write(self) -> None:
        """Caller holds the lock."""
        self.path.parent.mkdir(parents=True, exist_ok=True)
        staged = self.path.with_name(f".{self.path.name}.tmp")
        staged.write_text(json.dumps({"lists": self._rows}, indent=2, sort_keys=True) + "\n")
        os.replace(staged, self.path)
