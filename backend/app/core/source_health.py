"""
What each upstream source is actually doing.

`/health` used to answer this from configuration alone — `bool(TWITTER_API_KEY)`
— and was wrong in both directions at once:

- **twitter: true** while every request returned HTTP 401. A key being present
  says nothing about whether the provider accepts it.
- **reddit: false** while Reddit was returning posts perfectly well, because
  the RSS path needs no credentials at all. The check was reading fields that
  path never uses.

A health endpoint that reports the opposite of reality on two of four sources
is worse than having none: it sends you looking in the wrong place. So this
records what each source *did*, the last time anything actually asked it, and
health reports that alongside — not instead of — whether credentials are set.

The two facts are kept separate on purpose. "Configured" is a deployment
question, "working" is an operational one, and collapsing them is what caused
the problem. A source can be unconfigured and working (Reddit), configured and
broken (Twitter), or configured and never yet exercised, which is reported as
unknown rather than guessed.

State is in-process and resets on restart, which is the honest scope: after a
deploy we genuinely have not observed anything yet.
"""

from __future__ import annotations

import threading
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Optional

# Statuses the fetchers emit. `disabled` means we chose not to ask, which is
# not a fault; `empty` means the source answered and had nothing, which is a
# working source.
WORKING_STATUSES = frozenset({"ok", "empty"})


@dataclass(frozen=True)
class Observation:
    status: str
    detail: Optional[str]
    at: datetime


class SourceHealth:
    """Last observed outcome per source. Small, thread-safe, bounded."""

    def __init__(self) -> None:
        self._seen: dict[str, Observation] = {}
        self._lock = threading.Lock()

    def record(self, source: str, status: str, detail: Optional[str] = None) -> None:
        with self._lock:
            self._seen[source] = Observation(status, detail, datetime.now(timezone.utc))

    def record_all(self, source_status: dict[str, dict[str, Any]]) -> None:
        """Record a whole `source_status` block from one sentiment fetch."""
        for source, info in (source_status or {}).items():
            if isinstance(info, dict) and info.get("status"):
                self.record(source, info["status"], info.get("detail"))

    def describe(self, source: str, configured: bool) -> dict[str, Any]:
        """
        Both facts about one source, kept apart.

        `working` is None until something has actually asked the source. A
        guess would be how the old check went wrong.
        """
        with self._lock:
            observed = self._seen.get(source)

        if observed is None:
            return {
                "configured": configured,
                "working": None,
                "last_result": None,
                "detail": None,
                "observed_at": None,
            }

        return {
            "configured": configured,
            "working": observed.status in WORKING_STATUSES,
            "last_result": observed.status,
            "detail": observed.detail,
            "observed_at": observed.at.isoformat(),
        }

    def reset(self) -> None:
        """Drop all observations. For tests."""
        with self._lock:
            self._seen.clear()


source_health = SourceHealth()
