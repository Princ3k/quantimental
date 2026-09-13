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
velocity series per ticker aligned to it. That keeps the files small and makes
the only query that matters — this ticker's recent history — a single array
lookup rather than a scan of every day.

Split into one file per calendar year, because this is append-only and kept
forever. A finished year never changes again, so the evening commit only ever
rewrites the current one. `load` joins them back into a single aligned view
and, given a window, keeps only the recent end of it.

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

# Retention and the baseline window used to be the same constant. They are
# different questions and it was a mistake to answer both with one number.
#
# The window is a statistical judgement, and 180 days was the right one: long
# enough that a median spans earnings cycles, short enough that a company which
# changed character a year ago is not still setting its own normal. Unchanged.
#
# Retention is not a statistical question. Dropping the 181st day was free when
# the archive was an input to a feature; it is not free now that the archive is
# the asset. Nobody sells historical news volume, so a day deleted is gone for
# good, and the horizon that makes this data worth anything is measured in
# years. So nothing is deleted. The window only narrows what `baseline` reads.
BASELINE_WINDOW_DAYS = 180

# One file per calendar year rather than one growing file.
#
# The store is committed every evening, and a single minified JSON line does
# not delta-compress — three years in, each daily commit would rewrite several
# megabytes and the repository would be mostly its own history. A year shard
# stops changing on 31 December, so the daily diff stays bounded by the current
# year however long this runs. A year is also the unit anyone licensing this
# would expect to be handed.
SHARD_TEMPLATE = "attention-{year}.json"

# Below this many observations, a median is not a baseline, it is an anecdote.
MIN_HISTORY_FOR_BASELINE = 20

# How far above its own median a stock's coverage must sit to be called
# unusual. Coverage is far burstier than price, so this is deliberately higher
# than the 2.0x the price scan uses.
UNUSUAL_ATTENTION_MULTIPLE = 3.0


def _empty() -> dict[str, Any]:
    return {"dates": [], "velocity": {}}


def _read(path: Path) -> Optional[dict[str, Any]]:
    """One file, or None if it is not there."""
    if not path.exists():
        return None
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


def _write(path: Path, payload: dict[str, Any]) -> None:
    """
    Write to a sibling and rename.

    A runner killed part-way through the write would otherwise leave a
    truncated file for the commit step to push, and `_read` deliberately
    refuses to start over from a corrupt archive, so the sweep would stay down
    until someone restored from git history. os.replace is atomic within a
    filesystem, so what is on disk is always the whole old file or the whole
    new one; the temporary lands beside it to keep that true.
    """
    staged = path.with_name(f".{path.name}.tmp")
    staged.write_text(json.dumps(payload, separators=(",", ":")) + "\n")
    os.replace(staged, path)


def _shard_path(year: int, directory: Path) -> Path:
    return directory / SHARD_TEMPLATE.format(year=year)


def _shards(directory: Path) -> list[Path]:
    """Every year shard in the store, oldest first."""
    if not directory.exists():
        return []
    prefix, suffix = SHARD_TEMPLATE.split("{year}")
    found: list[tuple[int, Path]] = []
    for candidate in directory.iterdir():
        name = candidate.name
        if not name.startswith(prefix) or not name.endswith(suffix):
            continue
        year = name[len(prefix): len(name) - len(suffix)]
        if year.isdigit():
            found.append((int(year), candidate))
    return [path for _, path in sorted(found)]


def _concat(chunks: list[dict[str, Any]]) -> dict[str, Any]:
    """
    Join year shards, oldest first, onto one date list.

    Shards are independent files, so a ticker measured in 2027 but not 2026 has
    no series in the older one. Every ticker is padded across every chunk, or
    position would stop meaning day — which is the single assumption the whole
    column format rests on.
    """
    dates: list[str] = []
    velocity: dict[str, list[Optional[float]]] = {}

    for chunk in chunks:
        added = len(chunk["dates"])
        if not added:
            continue

        for series in velocity.values():
            series.extend([None] * added)
        for ticker in chunk["velocity"]:
            if ticker not in velocity:
                velocity[ticker] = [None] * (len(dates) + added)

        base = len(dates)
        for ticker, series in chunk["velocity"].items():
            target = velocity[ticker]
            for offset, value in enumerate(series[:added]):
                target[base + offset] = value

        dates.extend(chunk["dates"])

    return {"dates": dates, "velocity": velocity}


def _migrate(path: Path, directory: Path) -> None:
    """
    Move a pre-shard archive into year shards, once.

    Guarded on there being no shards yet: a half-finished migration that left
    the legacy file behind must not run again and overwrite shards that have
    since collected newer readings.
    """
    if _shards(directory) or not path.exists():
        return

    legacy = _read(path)
    if not legacy or not legacy["dates"]:
        path.unlink()
        return

    by_year: dict[int, list[int]] = {}
    for index, day in enumerate(legacy["dates"]):
        by_year.setdefault(int(day[:4]), []).append(index)

    for year, indices in by_year.items():
        _write(_shard_path(year, directory), {
            "dates": [legacy["dates"][i] for i in indices],
            "velocity": {
                ticker: [series[i] if i < len(series) else None for i in indices]
                for ticker, series in legacy["velocity"].items()
            },
        })

    path.unlink()
    logger.info("Migrated the archive into %d year shards", len(by_year))


def load(
    path: Path = ARCHIVE_PATH,
    window: Optional[int] = None,
) -> dict[str, Any]:
    """
    Read the archive, or an empty one on first run.

    `window` keeps only that many of the most recent days, which is what a scan
    wants — it needs enough history to compute a baseline and nothing more.
    None reads everything, which is what an export wants.
    """
    directory = path.parent
    shards = _shards(directory)
    # Shards win once they exist; the legacy file is only read before the first
    # `record` has migrated it, and is deleted by that migration.
    chunks = [_read(shard) for shard in shards] if shards else [_read(path)]
    archive = _concat([chunk for chunk in chunks if chunk])

    if window is not None and len(archive["dates"]) > window:
        archive["dates"] = archive["dates"][-window:]
        for ticker, series in archive["velocity"].items():
            archive["velocity"][ticker] = series[-window:]

    return archive


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

    Only the current year's shard is touched. The archive returned spans the
    whole baseline window, which matters most in January: a shard read alone
    would hold a handful of days and every baseline would disappear for a
    month at each New Year.
    """
    directory = path.parent
    directory.mkdir(parents=True, exist_ok=True)

    # A staging file only survives a process killed mid-write, in which case
    # this run is the one that cleans it up. Left alone it would be committed —
    # `git add -A` takes dotfiles too.
    for stale in directory.glob(".*.tmp"):
        stale.unlink()

    _migrate(path, directory)

    today = on or date.today().isoformat()
    shard_path = _shard_path(int(today[:4]), directory)
    shard = _read(shard_path) or _empty()

    dates: list[str] = shard["dates"]
    velocity: dict[str, list[Optional[float]]] = shard["velocity"]

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

    _write(shard_path, shard)

    archive = load(path, window=BASELINE_WINDOW_DAYS)
    logger.info(
        "Archive now holds %d days for %d tickers (%d shards)",
        len(archive["dates"]), len(archive["velocity"]), len(_shards(directory)),
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
    # The archive keeps everything; a baseline reads the recent window. A
    # company that changed character three years ago should not still be
    # setting its own normal.
    observed = [v for v in history[-BASELINE_WINDOW_DAYS:] if v is not None]

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
