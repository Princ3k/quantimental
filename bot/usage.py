"""
How the bot is being used, counted per day.

The question this answers: is anyone actually using this, what do they use it
for, and which companies do they ask about. At one server that is a sanity
check; at fifty it is the evidence for whether the universe should grow and
whether the DM phase is worth building.

**Counting people without following them.** Counting distinct users needs a way
to tell two commands apart, which is the one thing the rest of this bot avoids.
The digest here is made from the day and the id together, so the same person
produces an entirely different value tomorrow. That buys a real answer to "nine
people used it on Tuesday" while making "did any of them come back on
Wednesday" unanswerable — not merely undisclosed, but unreconstructable, since
nothing links the two digests and we never held the id.

That is a deliberate trade. Retention would be more useful than reach, and it
is not worth building a per-person history to get it while the honest version
of the product is the one that does not.

What is never recorded: usernames, which person asked for which ticker, or any
ordering of one person's requests. The file is a pile of counts.
"""

from __future__ import annotations

import hashlib
import json
import logging
import os
import threading
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Optional

logger = logging.getLogger(__name__)


def default_path() -> Path:
    mount = os.environ.get("RAILWAY_VOLUME_MOUNT_PATH")
    if mount:
        return Path(mount) / "usage.json"
    return Path("/data/usage.json")


USAGE_PATH = (
    Path(os.environ["USAGE_PATH"]) if os.environ.get("USAGE_PATH") else default_path()
)

# Days are kept for a quarter, which is long enough to see a trend and short
# enough that the file stays small and nothing accumulates indefinitely.
RETAIN_DAYS = 90

# Enough to make collisions negligible within a single day's population.
DIGEST_CHARS = 12


def _tag(day: str, value: int) -> str:
    """A digest that is unique within a day and meaningless across days."""
    return hashlib.sha256(f"{day}:{value}".encode()).hexdigest()[:DIGEST_CHARS]


def _today() -> str:
    return datetime.now(timezone.utc).date().isoformat()


class Usage:
    """Per-day counts. Never a per-person history."""

    def __init__(self, path: Path = USAGE_PATH) -> None:
        self.path = path
        self._lock = threading.Lock()
        self._days: dict[str, dict[str, Any]] = self._read()

    # -- recording ---------------------------------------------------------

    def record(
        self,
        command: str,
        *,
        user_id: Optional[int] = None,
        guild_id: Optional[int] = None,
        tickers: Optional[list[str]] = None,
        day: Optional[str] = None,
    ) -> None:
        """One command run. Everything is optional except what it was."""
        when = day or _today()
        with self._lock:
            bucket = self._days.setdefault(when, {})
            counts = bucket.setdefault("commands", {})
            counts[command] = counts.get(command, 0) + 1

            if user_id is not None:
                people = bucket.setdefault("people", [])
                tag = _tag(when, user_id)
                if tag not in people:
                    people.append(tag)

            if guild_id is not None:
                servers = bucket.setdefault("servers", [])
                tag = _tag(when, guild_id)
                if tag not in servers:
                    servers.append(tag)

            for ticker in tickers or []:
                symbol = (ticker or "").strip().upper()
                if not symbol:
                    continue
                asked = bucket.setdefault("tickers", {})
                asked[symbol] = asked.get(symbol, 0) + 1

            self._prune()
            self._write()

    # -- reading -----------------------------------------------------------

    def summary(self, days: int = 7) -> dict[str, Any]:
        """Totals over the last `days`, plus today on its own."""
        cutoff = (datetime.now(timezone.utc).date() - timedelta(days=days - 1)).isoformat()
        commands: dict[str, int] = {}
        tickers: dict[str, int] = {}
        people = 0
        servers = 0
        active_days = 0

        with self._lock:
            today = dict(self._days.get(_today(), {}))
            for when, bucket in self._days.items():
                if when < cutoff:
                    continue
                active_days += 1
                for name, n in (bucket.get("commands") or {}).items():
                    commands[name] = commands.get(name, 0) + n
                for symbol, n in (bucket.get("tickers") or {}).items():
                    tickers[symbol] = tickers.get(symbol, 0) + n
                # Summed across days, not deduplicated — the digests cannot be
                # compared between days by design, so this is "person-days",
                # and calling it anything else would overstate what we know.
                people += len(bucket.get("people") or [])
                servers += len(bucket.get("servers") or [])

        return {
            "window_days": days,
            "days_with_activity": active_days,
            "commands": dict(sorted(commands.items(), key=lambda kv: -kv[1])),
            "total_commands": sum(commands.values()),
            "tickers": dict(sorted(tickers.items(), key=lambda kv: -kv[1])),
            "distinct_tickers": len(tickers),
            "person_days": people,
            "server_days": servers,
            "today": {
                "commands": sum((today.get("commands") or {}).values()),
                "people": len(today.get("people") or []),
                "servers": len(today.get("servers") or []),
            },
        }

    def daily_counts(self, days: int = 14) -> list[tuple[str, int, int]]:
        """(day, commands, people) newest last, for seeing a trend."""
        cutoff = (datetime.now(timezone.utc).date() - timedelta(days=days - 1)).isoformat()
        with self._lock:
            rows = [
                (
                    when,
                    sum((b.get("commands") or {}).values()),
                    len(b.get("people") or []),
                )
                for when, b in self._days.items()
                if when >= cutoff
            ]
        return sorted(rows)

    # -- persistence -------------------------------------------------------

    def _prune(self) -> None:
        """Caller holds the lock."""
        cutoff = (datetime.now(timezone.utc).date() - timedelta(days=RETAIN_DAYS)).isoformat()
        for when in [d for d in self._days if d < cutoff]:
            del self._days[when]

    def _read(self) -> dict[str, dict[str, Any]]:
        try:
            raw = json.loads(self.path.read_text())
        except FileNotFoundError:
            return {}
        except Exception as exc:  # noqa: BLE001
            logger.error("Usage file at %s is unreadable: %s", self.path, exc)
            return {}
        days = raw.get("days") if isinstance(raw, dict) else None
        return days if isinstance(days, dict) else {}

    def _write(self) -> None:
        """Caller holds the lock."""
        self.path.parent.mkdir(parents=True, exist_ok=True)
        staged = self.path.with_name(f".{self.path.name}.tmp")
        staged.write_text(json.dumps({"days": self._days}, indent=2, sort_keys=True) + "\n")
        os.replace(staged, self.path)
