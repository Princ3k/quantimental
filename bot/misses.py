"""
Which tickers people ask for that the universe does not cover.

The covered universe is the S&P 500. The first ticker anyone reached for in
testing was KAZR, which is not in it — and in a stock server, small caps are
most of the conversation. So the question "should the universe expand, and to
what" is real, and the honest way to answer it is the same way the 8-K question
was answered: measure first, rather than spending the Yahoo news budget on two
thousand names nobody asked about.

This records the misses. Nothing else. One line per ticker, a count, and the
dates it was first and last asked for.

**What is deliberately not recorded:** who asked. No user ids, no usernames, no
message content. Servers are counted, not identified — a guild id is stored as
a short digest so that "eleven servers asked for this" is answerable and "which
servers" is not. That matters because most of these requests will come from
other people's communities, and a ranked list of tickers is the entire point;
knowing who typed them adds nothing to it.
"""

from __future__ import annotations

import hashlib
import json
import logging
import os
import threading
from datetime import date
from pathlib import Path
from typing import Any, Optional

logger = logging.getLogger(__name__)


def default_path() -> Path:
    """Beside the watchlists, on the same volume."""
    mount = os.environ.get("RAILWAY_VOLUME_MOUNT_PATH")
    if mount:
        return Path(mount) / "misses.json"
    return Path("/data/misses.json")


MISSES_PATH = (
    Path(os.environ["MISSES_PATH"]) if os.environ.get("MISSES_PATH") else default_path()
)

# Enough to distinguish servers, far too little to identify one.
DIGEST_CHARS = 8


def _tag(guild_id: Optional[int]) -> Optional[str]:
    if guild_id is None:
        return None
    return hashlib.sha256(str(guild_id).encode()).hexdigest()[:DIGEST_CHARS]


class Misses:
    """Ticker -> how often it was asked for, and by how many servers."""

    def __init__(self, path: Path = MISSES_PATH) -> None:
        self.path = path
        self._lock = threading.Lock()
        self._rows: dict[str, dict[str, Any]] = self._read()

    def record(self, ticker: str, guild_id: Optional[int] = None) -> None:
        symbol = (ticker or "").strip().upper()
        if not symbol:
            return
        today = date.today().isoformat()
        tag = _tag(guild_id)
        with self._lock:
            row = self._rows.setdefault(
                symbol, {"count": 0, "guilds": [], "first": today, "last": today}
            )
            row["count"] += 1
            row["last"] = today
            if tag and tag not in row["guilds"]:
                row["guilds"].append(tag)
            self._write()

    def ranked(self, limit: int = 20) -> list[tuple[str, dict[str, Any]]]:
        """Most-asked-for first, then by how many servers wanted it.

        Servers break the tie rather than raw count, because one person
        hammering a ticker is a person, and five servers asking once each is a
        universe gap.
        """
        with self._lock:
            rows = list(self._rows.items())
        rows.sort(key=lambda kv: (len(kv[1].get("guilds", [])), kv[1]["count"]), reverse=True)
        return rows[:limit]

    def total(self) -> int:
        with self._lock:
            return sum(r["count"] for r in self._rows.values())

    def distinct(self) -> int:
        with self._lock:
            return len(self._rows)

    def _read(self) -> dict[str, dict[str, Any]]:
        try:
            raw = json.loads(self.path.read_text())
        except FileNotFoundError:
            return {}
        except Exception as exc:  # noqa: BLE001
            logger.error("Misses file at %s is unreadable: %s", self.path, exc)
            return {}
        rows = raw.get("requests") if isinstance(raw, dict) else None
        if not isinstance(rows, dict):
            return {}
        cleaned: dict[str, dict[str, Any]] = {}
        for ticker, row in rows.items():
            if not isinstance(row, dict):
                continue
            cleaned[str(ticker).upper()] = {
                "count": int(row.get("count", 0)),
                "guilds": [str(g) for g in row.get("guilds", [])],
                "first": row.get("first"),
                "last": row.get("last"),
            }
        return cleaned

    def _write(self) -> None:
        """Caller holds the lock."""
        self.path.parent.mkdir(parents=True, exist_ok=True)
        staged = self.path.with_name(f".{self.path.name}.tmp")
        staged.write_text(
            json.dumps({"requests": self._rows}, indent=2, sort_keys=True) + "\n"
        )
        os.replace(staged, self.path)
