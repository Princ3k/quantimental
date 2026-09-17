"""
Per-guild state: what a server follows, where its digest goes, what it has had.

One JSON file on a Railway volume, written the way the attention archive is
written — to a temporary file beside the target, then `os.replace`, which is
atomic on POSIX. A crash mid-write leaves the previous file intact rather than
a truncated one. The whole file is small and cheap to rewrite, which is why
there is no database: a bot's follow list does not justify Postgres, and this
project's persistence idiom is a file it can read.

The shape is nested per guild rather than one flat map with prefixed keys.
That was the first design here and it was wrong: `channel:123` and `posted:123`
sat alongside the guild ids, so iterating the map yielded channel ids as guild
ids and stored dates as tickers.

    {"guilds": {"123": {"tickers": ["AAPL"], "channel": 456, "posted": "2026-09-17"}}}
"""

from __future__ import annotations

import json
import logging
import os
import threading
from pathlib import Path
from typing import Any, Optional

logger = logging.getLogger(__name__)

def default_path() -> Path:
    """Where state lives when WATCHLIST_PATH does not say.

    Railway sets RAILWAY_VOLUME_MOUNT_PATH itself whenever a volume is attached,
    so deriving the default from it means the file lands on the volume without
    anyone having to make two settings agree. Getting that wrong is silent: the
    bot creates the directory, writes happily to container storage, answers
    /watch list correctly — and loses everything on the next deploy, which is
    exactly what happened the first time this ran.
    """
    mount = os.environ.get("RAILWAY_VOLUME_MOUNT_PATH")
    if mount:
        return Path(mount) / "watchlists.json"
    return Path("/data/watchlists.json")


STORE_PATH = (
    Path(os.environ["WATCHLIST_PATH"])
    if os.environ.get("WATCHLIST_PATH")
    else default_path()
)


def check_durability(path: Path = STORE_PATH) -> bool:
    """Log whether this path will actually survive a redeploy.

    Returns True when the state file is on a mounted volume. Logged at error
    level when it is not, because the alternative is finding out a week later
    that every server's watchlist has been quietly resetting.
    """
    mount = os.environ.get("RAILWAY_VOLUME_MOUNT_PATH")
    if not mount:
        logger.error(
            "No volume is attached (RAILWAY_VOLUME_MOUNT_PATH is unset). State at "
            "%s is on container storage and will be lost on the next deploy.",
            path,
        )
        return False
    try:
        path.resolve().relative_to(Path(mount).resolve())
    except ValueError:
        logger.error(
            "State path %s is not inside the mounted volume %s. It will be lost "
            "on the next deploy. Unset WATCHLIST_PATH to use the volume.",
            path,
            mount,
        )
        return False
    logger.info("State at %s is on the volume mounted at %s.", path, mount)
    return True

# Per guild. High enough that nobody legitimate hits it, low enough that many
# servers together stay well under the endpoint's hundred-ticker cap.
MAX_PER_GUILD = 25


class Watchlists:
    """Guild state, loaded once and written through on every change."""

    def __init__(self, path: Path = STORE_PATH) -> None:
        self._path = path
        self._lock = threading.Lock()
        # Exposed so the startup check can report the path actually in use
        # rather than re-deriving it and possibly disagreeing.
        self.path = path
        self._guilds: dict[str, dict[str, Any]] = self._read()

    # -- reading -----------------------------------------------------------

    def get(self, guild_id: int) -> list[str]:
        with self._lock:
            return list(self._guilds.get(str(guild_id), {}).get("tickers", []))

    def guilds(self) -> list[int]:
        """Guilds with at least one ticker and somewhere to post it."""
        with self._lock:
            return [
                int(gid)
                for gid, state in self._guilds.items()
                if state.get("tickers") and state.get("channel")
            ]

    def every_ticker(self) -> list[str]:
        """Every distinct ticker anyone follows, so one call can serve all."""
        seen: dict[str, None] = {}
        with self._lock:
            for state in self._guilds.values():
                for ticker in state.get("tickers", []):
                    seen.setdefault(ticker, None)
        return list(seen)

    def channel(self, guild_id: int) -> Optional[int]:
        with self._lock:
            got = self._guilds.get(str(guild_id), {}).get("channel")
        return int(got) if got else None

    def get_posted(self, guild_id: int) -> Optional[str]:
        with self._lock:
            return self._guilds.get(str(guild_id), {}).get("posted")

    # -- writing -----------------------------------------------------------

    def add(self, guild_id: int, ticker: str) -> tuple[bool, str]:
        """Returns (changed, message). The message is shown to the user."""
        symbol = clean(ticker)
        if not symbol:
            return False, "That does not look like a ticker."

        with self._lock:
            state = self._guilds.setdefault(str(guild_id), {})
            tickers = state.setdefault("tickers", [])
            if symbol in tickers:
                return False, f"Already watching {symbol}."
            if len(tickers) >= MAX_PER_GUILD:
                return False, f"This server is at the limit of {MAX_PER_GUILD}."
            tickers.append(symbol)
            self._write()
        return True, f"Watching {symbol}."

    def remove(self, guild_id: int, ticker: str) -> tuple[bool, str]:
        symbol = clean(ticker)
        with self._lock:
            tickers = self._guilds.get(str(guild_id), {}).get("tickers", [])
            if symbol not in tickers:
                return False, f"Not watching {symbol or ticker.upper()}."
            tickers.remove(symbol)
            self._write()
        return True, f"Stopped watching {symbol}."

    def set_channel(self, guild_id: int, channel_id: int) -> None:
        with self._lock:
            self._guilds.setdefault(str(guild_id), {})["channel"] = int(channel_id)
            self._write()

    def mark_posted(self, guild_id: int, as_of: Optional[str]) -> None:
        """Record that this guild has had its digest for `as_of`.

        Written only after a send succeeds, so a failed post is retried on the
        next poll rather than being marked done.
        """
        if not as_of:
            return
        with self._lock:
            self._guilds.setdefault(str(guild_id), {})["posted"] = as_of
            self._write()

    # -- persistence -------------------------------------------------------

    def _read(self) -> dict[str, dict[str, Any]]:
        try:
            raw = json.loads(self._path.read_text())
        except FileNotFoundError:
            return {}
        except Exception as exc:  # noqa: BLE001
            # A corrupt file must not stop the bot starting, and must not be
            # silently replaced either: log loudly and leave it on disk so it
            # can be recovered by hand.
            logger.error("State file at %s is unreadable: %s", self._path, exc)
            return {}

        guilds = raw.get("guilds") if isinstance(raw, dict) else None
        if not isinstance(guilds, dict):
            logger.error("State file at %s has no guilds object.", self._path)
            return {}

        cleaned: dict[str, dict[str, Any]] = {}
        for gid, state in guilds.items():
            if not isinstance(state, dict):
                continue
            cleaned[str(gid)] = {
                "tickers": [str(t) for t in state.get("tickers", []) if t],
                "channel": state.get("channel"),
                "posted": state.get("posted"),
            }
        return cleaned

    def _write(self) -> None:
        """Caller holds the lock."""
        self._path.parent.mkdir(parents=True, exist_ok=True)
        staged = self._path.with_name(f".{self._path.name}.tmp")
        staged.write_text(
            json.dumps({"guilds": self._guilds}, indent=2, sort_keys=True) + "\n"
        )
        os.replace(staged, self._path)


def clean(ticker: str) -> str:
    """Upper-case and strip, or "" if it is not a plausible symbol."""
    symbol = (ticker or "").strip().upper().lstrip("$")
    if not symbol or len(symbol) > 6:
        return ""
    if not all(c.isalpha() or c in ".-" for c in symbol):
        return ""
    return symbol
