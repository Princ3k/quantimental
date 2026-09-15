"""
Read the attention archive in a shape a person can use.

The archive is stored minified and column-oriented because that is what serves
the scan: one file, one read, one array lookup to answer "what is normal for
this ticker". It is deliberately not built to be read by eye, and reorganising
it so it could be would make it worse at its only job.

So the fix for "I cannot see what is in there" is a view, not a new format.
Nothing here writes; it is safe to run against the live store.

    python scripts/show_attention.py                     # what the archive holds
    python scripts/show_attention.py --day 2026-09-15    # one session, ranked
    python scripts/show_attention.py --ticker NVDA AMZN  # series over time
    python scripts/show_attention.py --csv out.csv       # for a spreadsheet
"""

from __future__ import annotations

import argparse
import csv
import statistics
import sys
from pathlib import Path
from typing import Any, Optional

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.services.scan.attention_archive import (  # noqa: E402
    MIN_HISTORY_FOR_BASELINE,
    UNUSUAL_ATTENTION_MULTIPLE,
    baseline,
    load,
)

DEFAULT_STORE = Path.home() / "code" / "quantimental-data" / "attention-history.json"


def _fmt(value: Optional[float]) -> str:
    """A reading, or a dash. Never 0.0 for a missing one — they are different facts."""
    return "     —" if value is None else f"{value:6.2f}"


def overview(archive: dict[str, Any]) -> None:
    dates, velocity = archive["dates"], archive["velocity"]
    if not dates:
        print("The archive is empty.")
        return

    print(f"{len(dates)} sessions, {len(velocity)} tickers\n")
    print("  session       measured   median   busiest")
    for i, day in enumerate(dates):
        day_values = [s[i] for s in velocity.values() if i < len(s) and s[i] is not None]
        if not day_values:
            print(f"  {day}        0/{len(velocity)}")
            continue
        top = max(
            ((s[i], t) for t, s in velocity.items() if i < len(s) and s[i] is not None),
            default=(0.0, "—"),
        )
        print(
            f"  {day}   {len(day_values):>4}/{len(velocity)}"
            f"   {statistics.median(day_values):6.2f}"
            f"   {top[1]} {top[0]:.0f}/day"
        )

    have = len(dates)
    if have < MIN_HISTORY_FOR_BASELINE:
        short = MIN_HISTORY_FOR_BASELINE - have
        print(
            f"\n  {have}/{MIN_HISTORY_FOR_BASELINE} sessions towards a baseline — "
            f"{short} more before this can call anything unusual."
        )
    else:
        ready = sum(1 for t in velocity if baseline(archive, t) is not None)
        print(f"\n  {ready}/{len(velocity)} tickers now have enough history for a baseline.")


def one_day(archive: dict[str, Any], day: str, limit: int) -> None:
    dates, velocity = archive["dates"], archive["velocity"]
    if day not in dates:
        print(f"No readings for {day}. Held: {dates[0]} to {dates[-1]}.")
        return

    i = dates.index(day)
    rows = [
        (s[i], t) for t, s in velocity.items() if i < len(s) and s[i] is not None
    ]
    rows.sort(reverse=True)

    print(f"{day} — {len(rows)} tickers measured, most covered first\n")
    print("  ticker   articles/day   vs its own normal")
    for value, ticker in rows[:limit]:
        normal = baseline(archive, ticker)
        if normal:
            multiple = value / normal
            mark = "  ← unusual" if multiple >= UNUSUAL_ATTENTION_MULTIPLE else ""
            against = f"{multiple:5.1f}x{mark}"
        else:
            # Honest rather than blank: there is no normal yet to compare with.
            against = "    not enough history"
        print(f"  {ticker:<8} {value:9.2f}      {against}")


def series(archive: dict[str, Any], tickers: list[str]) -> None:
    dates, velocity = archive["dates"], archive["velocity"]
    width = max(8, max((len(t) for t in tickers), default=8) + 1)

    print(" " * width + "".join(f"{d[5:]:>8}" for d in dates) + "   median")
    for raw in tickers:
        ticker = raw.upper()
        s = velocity.get(ticker)
        if s is None:
            print(f"{ticker:<{width}}not in the archive")
            continue
        normal = baseline(archive, ticker, exclude_last=False)
        tail = f"{normal:8.2f}" if normal is not None else "       —"
        print(f"{ticker:<{width}}" + "".join(_fmt(v) + "  " for v in s) + tail)


def to_csv(archive: dict[str, Any], path: Path) -> None:
    """One row per ticker per session — the shape anything else can read."""
    dates, velocity = archive["dates"], archive["velocity"]
    with path.open("w", newline="") as handle:
        writer = csv.writer(handle)
        writer.writerow(["session", "ticker", "articles_per_day"])
        for i, day in enumerate(dates):
            for ticker, s in sorted(velocity.items()):
                if i < len(s) and s[i] is not None:
                    writer.writerow([day, ticker, f"{s[i]:.4f}"])
    print(f"Wrote {path} — {len(dates)} sessions x {len(velocity)} tickers, long format.")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--store", type=Path, default=DEFAULT_STORE,
                        help="Any file inside the data store; its directory is what gets read.")
    parser.add_argument("--day", help="Rank one session, most covered first.")
    parser.add_argument("--ticker", nargs="+", help="Show these tickers over time.")
    parser.add_argument("--csv", type=Path, help="Write the whole archive as long-format CSV.")
    parser.add_argument("--limit", type=int, default=25, help="Rows for --day (default 25).")
    args = parser.parse_args()

    if not args.store.parent.exists():
        print(f"No data store at {args.store.parent}.", file=sys.stderr)
        return 1

    archive = load(args.store)
    if not archive["dates"]:
        print(f"No readings found in {args.store.parent}.", file=sys.stderr)
        return 1

    if args.csv:
        to_csv(archive, args.csv)
    elif args.ticker:
        series(archive, args.ticker)
    elif args.day:
        one_day(archive, args.day, args.limit)
    else:
        overview(archive)
    return 0


if __name__ == "__main__":
    sys.exit(main())
