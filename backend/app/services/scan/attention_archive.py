"""
The attention archive — a diary of how much coverage each stock was getting.

This file is the moat. Everything else this project reads is public and
reconstructable: anyone can backfill a year of prices from Yahoo for nothing.
Nobody can backfill *how much was being written about NVDA on 3 March*, because
no one sells that and the sources only serve the present. It exists only if
someone was writing it down, and it becomes more valuable every day it runs.

What it enables is the price scan's own trick applied to coverage — "this stock
is getting four times its normal attention" — which requires knowing what
normal is for that stock, which requires having watched.

Shape
-----

Column-oriented rather than one record per day: dates in one list, and a
velocity series per ticker aligned to it. That keeps the file small (503
tickers x 180 days of floats) and makes the only query that matters — this
ticker's recent history — a single array lookup rather than a scan of every
day.

Missing readings are `null` rather than 0.0. A stock we failed to measure and a
stock nobody wrote about are different facts, and conflating them would poison
exactly the median this archive exists to compute.
"""

from __future__ import annotations

import json
import logging
import os
import statistics
from datetime import date
from pathlib import Path
from typing import Any, Optional

logger = logging.getLogger(__name__)

# The archive lives outside this repository.
#
# It is the one asset here that cannot be reconstructed from public sources —
# nobody sells historical news volume — so publishing it daily to a public git
# log would hand away the thing it exists to accumulate. Worse, git history is
# permanent: every day it stayed public would stay public even after a move.
#
# So it is written to a private store, and only the *derived* figures (`v` and
# `vx` in snapshot.json) are published. ATTENTION_ARCHIVE_PATH points at the
# checkout in CI; the local default is gitignored for development.
ARCHIVE_PATH = Path(
    os.environ.get("ATTENTION_ARCHIVE_PATH")
    or Path(__file__).resolve().parents[3] / "data" / "attention-history.json"
)

# Six months. Long enough that a median means something across earnings cycles,
# short enough that the file stays small and a company that changed character a
# year ago is not still setting its own baseline.
MAX_DAYS = 180

# Below this many observations, a median is not a baseline, it is an anecdote.
MIN_HISTORY_FOR_BASELINE = 20

# How far above its own median a stock's coverage must sit to be called
# unusual. Coverage is far burstier than price, so this is deliberately higher
# than the 2.0x the price scan uses.
UNUSUAL_ATTENTION_MULTIPLE = 3.0


def load(path: Path = ARCHIVE_PATH) -> dict[str, Any]:
    """Read the archive, or an empty one on first run."""
    if not path.exists():
        return {"dates": [], "velocity": {}}
    try:
        payload = json.loads(path.read_text())
        if not isinstance(payload.get("dates"), list):
            raise ValueError("malformed archive")
        payload.setdefault("velocity", {})
        return payload
    except (ValueError, OSError) as exc:
        # Refusing to start over silently: an unreadable archive is a bug worth
        # seeing, and overwriting it would destroy the only copy of data that
        # cannot be regenerated.
        raise RuntimeError(f"Attention archive at {path} is unreadable: {exc}") from exc


def record(
    measurements: dict[str, dict[str, Any]],
    on: Optional[str] = None,
    path: Path = ARCHIVE_PATH,
) -> dict[str, Any]:
    """
    Append (or replace) one day's readings.

    The scan runs several times a session, so a same-day rerun overwrites that
    day's column rather than adding a second one — the archive holds one
    observation per trading day, and the last run of the day is the one that
    saw a complete session.
    """
    archive = load(path)
    today = on or date.today().isoformat()

    dates: list[str] = archive["dates"]
    velocity: dict[str, list[Optional[float]]] = archive["velocity"]

    if dates and dates[-1] == today:
        index = len(dates) - 1
    else:
        dates.append(today)
        index = len(dates) - 1
        for series in velocity.values():
            series.append(None)

    for ticker, reading in measurements.items():
        series = velocity.setdefault(ticker, [None] * len(dates))
        # A ticker first seen today starts with nulls for every prior day, so
        # every series stays aligned to `dates` by position.
        while len(series) < len(dates):
            series.append(None)
        series[index] = reading["velocity"]

    # Tickers that dropped out of the universe still need their series padded,
    # or a later append would write into the wrong day.
    for series in velocity.values():
        while len(series) < len(dates):
            series.append(None)

    if len(dates) > MAX_DAYS:
        excess = len(dates) - MAX_DAYS
        archive["dates"] = dates[excess:]
        for ticker in velocity:
            velocity[ticker] = velocity[ticker][excess:]

    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(archive, separators=(",", ":")) + "\n")

    logger.info(
        "Archive now holds %d days for %d tickers",
        len(archive["dates"]), len(velocity),
    )
    return archive


def baseline(archive: dict[str, Any], ticker: str, exclude_last: bool = True) -> Optional[float]:
    """
    This stock's normal coverage, as the median of its history.

    Median rather than mean because coverage is spiky: one earnings day at 40x
    would drag a mean far enough that the next genuine spike looks ordinary.

    `exclude_last` drops today from its own baseline — otherwise a large day
    partly normalises itself away, the same mistake the price scan avoids.
    """
    series = archive.get("velocity", {}).get(ticker)
    if not series:
        return None

    history = series[:-1] if exclude_last and len(series) > 1 else series
    observed = [v for v in history if v is not None]

    if len(observed) < MIN_HISTORY_FOR_BASELINE:
        return None
    return statistics.median(observed)


def attention_multiple(
    archive: dict[str, Any],
    ticker: str,
    velocity: float,
) -> Optional[float]:
    """
    How today's coverage compares to this stock's own normal.

    Returns None until there is enough history to say — which is the honest
    answer for the archive's first few weeks, and better than a confident
    number computed from four data points.
    """
    normal = baseline(archive, ticker)
    if normal is None or normal <= 0:
        return None
    return round(velocity / normal, 1)
