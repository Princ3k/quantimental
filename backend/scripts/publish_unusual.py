#!/usr/bin/env python3
"""
Scan the universe for unusual moves and write the result to a JSON file.

Run on a schedule by .github/workflows/unusual-scan.yml, which commits the
result. The frontend fetches that static file rather than calling a live
server.

Same reasoning as publish_signal_desk.py: this payload is identical for every
viewer and changes only when the market does, so it is a *file*, not a request.
Serving it statically costs nothing, never cold-starts, and does not put a
503-ticker download on the critical path of somebody opening the page.

    python scripts/publish_unusual.py public/unusual.json [--attention]

The price scan is cheap and runs hourly. `--attention` additionally sweeps
every ticker's news to measure and archive coverage, which takes about nine
minutes and is worth doing once a day, after the close: the archive keeps one
observation per trading day, so the other eight runs would spend the same
Yahoo budget to overwrite the same row.

Writes a second file beside it — `snapshot.json` — carrying every measured
ticker rather than only the notable ones. That is what the per-stock pages and
any home-screen widget read: a page for AAPL needs AAPL's numbers whether or
not AAPL had an interesting day, and fetching them per visitor would put an
unauthenticated API call behind every page view and every widget refresh.
"""

from __future__ import annotations

import json
import logging
import sys
from pathlib import Path

# Make `app` importable when run from the repository's backend directory.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.services.scan import attention_archive  # noqa: E402
from app.services.scan.attention_service import (  # noqa: E402
    SWEEP_COMPLETE_FRACTION,
    measure_attention,
)
from app.services.ingestion.filings import filing_fetcher  # noqa: E402
from app.services.scan.unusual_service import UNUSUAL_MULTIPLE, scan  # noqa: E402

logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
logger = logging.getLogger("publish_unusual")

DEFAULT_OUTPUT = Path("public/unusual.json")


def main() -> int:
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    flags = {a for a in sys.argv[1:] if a.startswith("--")}

    output = Path(args[0]) if args else DEFAULT_OUTPUT
    with_attention = "--attention" in flags
    with_filings = "--filings" in flags

    result = scan()

    if not result.get("available"):
        # Publishing an "unavailable" payload would replace a good file with a
        # broken one on any transient upstream failure. Keep the previous
        # snapshot instead — stale data beats no data here.
        logger.error("Scan failed: %s", result.get("reason"))
        logger.error("Leaving the existing file untouched.")
        return 1

    # A scan that measured almost nothing usually means the download returned
    # empty frames rather than that the market vanished. Publishing it would
    # quietly replace a real reading with "0 of 503 scanned".
    if result["scanned"] < result["universe"] * 0.5:
        logger.error(
            "Only %d of %d tickers produced usable data; not publishing.",
            result["scanned"], result["universe"],
        )
        return 1

    # The snapshot is an order of magnitude larger than the feed and is read by
    # different clients, so it ships as its own file. Anything fetching the
    # feed for five headlines should not pay for 503 rows.
    snapshot_rows = result.pop("snapshot", [])

    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(result, indent=2) + "\n")

    # Measure and archive coverage before writing anything, so the published
    # files and the archive describe the same session.
    archive_days: int | None = None

    # The workflow asks for a sweep on the post-close run. Whether one is
    # *needed* is a question about what the archive already holds, not about
    # which trigger fired — see _already_swept.
    sweep = with_attention and not _already_swept(result["as_of"], len(snapshot_rows))

    if sweep:
        attention = _record_attention(snapshot_rows, result["as_of"])
        archive_days = _archive_days()
        for row in snapshot_rows:
            reading = attention.get(row["t"])
            if reading:
                row["v"] = reading["velocity"]
                if reading.get("multiple") is not None:
                    row["vx"] = reading["multiple"]

        # A sweep that measured nothing must not erase what the last one found.
        # measure_attention omits tickers it could not reach rather than zeroing
        # them, so a row with no `v` here means "we failed to look", never "no
        # coverage" — and the archive's last reading is a better answer than the
        # field vanishing from the snapshot.
        #
        # This is not hypothetical. On 2026-09-26 GitHub started the post-close
        # cron 2h24m late, after the sweep had already run on time; the second
        # sweep came back empty, published a snapshot with no coverage on any of
        # 503 rows, and — being the last publish before the weekend — left the
        # site that way for two days.
        _carry_forward_attention(snapshot_rows, result["as_of"])
    else:
        # Carry forward the last sweep's figures rather than dropping them —
        # coverage moves slowly enough that yesterday's reading beats none, and
        # an hourly run publishing a snapshot with no `v` field would make the
        # attention data appear and disappear through the day.
        #
        # This is also where a skipped sweep lands. The carry-forward reads this
        # session's own readings back out of the archive, so the snapshot comes
        # out the same as a re-sweep would have made it, without spending
        # another nine minutes of Yahoo's budget to get there.
        _carry_forward_attention(snapshot_rows, result["as_of"])
        archive_days = _archive_days()

    # Filings are decoration on the price scan, never a reason it fails to
    # publish. Phase 0 measured a filing on 35.7% of moves worth 2x a stock's
    # typical day against 5.1% of days overall, which is why this is attached
    # to every row rather than computed as a signal of its own: the scan
    # already knows which moves were unusual.
    if with_filings:
        _attach_filings(snapshot_rows, result["as_of"])

    snapshot_path = output.parent / "snapshot.json"
    snapshot_path.write_text(json.dumps({
        "as_of": result["as_of"],
        "generated_at": result["generated_at"],
        "count": len(snapshot_rows),
        # How many sessions the attention archive holds — the number, never the
        # readings. It is what tells a reader whether `vx` is missing because
        # coverage was ordinary or because there is not yet enough history to
        # say, and publishing a count gives away nothing the archive protects.
        "archive_days": archive_days,
        "archive_days_needed": attention_archive.MIN_HISTORY_FOR_BASELINE,
        # Short keys keep this small; this block is the schema.
        "fields": {
            "t": "ticker", "n": "company name", "s": "sector",
            "p": "price", "c": "change percent today",
            "x": "multiple of this stock's typical daily move",
            "d": "typical daily move percent", "w": "change percent over two weeks",
            "h": "one-sentence description", "st": "rising | falling | steady",
            "ctx": "how this move compares to its sector and the market",
            "mkt": "the market's move today (median of the universe)",
            "sec": "this sector's move today (median of its members)",
            "v": "news articles per day",
            "vx": "multiple of this stock's normal coverage (absent until "
                  "there is enough history to say)",
            "f": "the 8-K this company filed for this session, if any: "
                 "{i: item codes, p: what it reported, a: when EDGAR accepted "
                 "it}. A filing on the same day is adjacency, not cause.",
        },
        "stocks": snapshot_rows,
    }, separators=(",", ":")) + "\n")

    logger.info("Wrote %s — %d tickers", snapshot_path, len(snapshot_rows))
    logger.info(
        "Scanned %d tickers for %s: %d unusual (%d up, %d down)",
        result["scanned"], result["as_of"],
        result["unusual_count"], result["rising"], result["falling"],
    )
    for move in result["movers"][:5]:
        logger.info("  %s", move["headline"])

    return 0


def _archive_days() -> int | None:
    """How many sessions the attention archive holds, or None if unreadable."""
    try:
        return len(attention_archive.load()["dates"])
    except Exception as exc:  # noqa: BLE001
        logger.warning("Could not measure the archive: %s", exc)
        return None


def _attach_filings(rows: list[dict], as_of: str | None) -> None:
    """
    Hang each company's 8-K for this session on its row.

    Nothing here says a filing caused a move, and the wording downstream must
    not either — the two happened on the same day, which the reader can see and
    judge. What this adds is the fact that a reader would otherwise have to go
    to EDGAR for.
    """
    if not as_of:
        return

    # A stock that moved unusually is checked even when no index lists it —
    # the intraday index does not exist yet, and those are the rows where a
    # filing is most likely and most worth having.
    flagged = [row["t"] for row in rows if (row.get("x") or 0) >= UNUSUAL_MULTIPLE]

    try:
        filings = filing_fetcher.filings_for_session(
            [row["t"] for row in rows], as_of, always_check=flagged
        )
    except Exception as exc:  # noqa: BLE001
        logger.warning("Could not read filings: %s", exc)
        return

    attached = 0
    for row in rows:
        filing = filings.get(row["t"])
        # A filing whose only items were exhibit housekeeping has nothing to
        # say, so it is left off rather than rendered as an empty explanation.
        if filing and filing.phrase:
            row["f"] = filing.as_row()
            attached += 1

    logger.info("Attached %d filings to the snapshot", attached)


def _carry_forward_attention(rows: list[dict], as_of: str | None) -> None:
    """
    Fill each row's velocity from the most recent archived reading.

    Only rows that have none. A row already carrying `v` was measured by this
    run, and today's reading always beats the archive's.
    """
    missing = [row for row in rows if row.get("v") is None]
    if not missing:
        return

    try:
        # Only enough history to compute a baseline. This runs hourly and the
        # store is kept forever, so reading every shard would mean parsing
        # years of readings to answer a question about the last six months.
        archive = attention_archive.load(
            window=attention_archive.BASELINE_WINDOW_DAYS
        )
    except Exception as exc:  # noqa: BLE001
        logger.warning("Could not read the attention archive: %s", exc)
        return

    if not archive.get("dates"):
        return

    filled = 0
    for row in missing:
        series = archive["velocity"].get(row["t"]) or []
        latest = next((v for v in reversed(series) if v is not None), None)
        if latest is None:
            continue
        row["v"] = latest
        multiple = attention_archive.attention_multiple(archive, row["t"], latest)
        if multiple is not None:
            row["vx"] = multiple
        filled += 1

    # Said out loud, and at warning level when it is most of the universe. A
    # fallback that repairs the snapshot silently is a fallback that hides a
    # sweep which has stopped working.
    if filled:
        log = logger.warning if len(missing) > len(rows) * 0.2 else logger.info
        log(
            "Carried coverage forward for %d of %d rows that this run did not "
            "measure.",
            filled, len(rows),
        )


def _already_swept(as_of: str | None, universe: int) -> bool:
    """
    Whether the archive already holds a complete reading for this session.

    The sweep is meant to run once a day, after the close, and the workflow used
    to enforce that by checking which cron fired. That cannot work: the scan is
    triggered from two places, and on 2026-09-26 GitHub started the post-close
    cron 2h24m late — after the external dispatcher had already swept on time.
    The run swept a second time, measured nothing, and published a snapshot with
    no coverage on any of 503 rows. Asking the archive what it holds is a
    question that stays correct however late a trigger arrives.

    A partial reading is not enough to skip on. A sweep the limiter cut off is
    precisely the case where measuring again is worth the budget, so the bar is
    the same fraction attention_service uses to call a sweep short.
    """
    if not as_of:
        return False

    try:
        # One day is all this asks about, and `load` truncates each series to
        # the same window — so a ticker measured earlier today ends in its
        # reading, and one that was missed ends in None.
        archive = attention_archive.load(window=1)
    except Exception as exc:  # noqa: BLE001
        logger.warning("Could not read the attention archive: %s", exc)
        return False

    dates = archive.get("dates") or []
    if not dates or dates[-1] != as_of:
        return False

    measured = sum(
        1
        for series in archive["velocity"].values()
        if series and series[-1] is not None
    )

    if measured < universe * SWEEP_COMPLETE_FRACTION:
        logger.info(
            "The archive holds only %d of %d readings for %s — sweeping again.",
            measured, universe, as_of,
        )
        return False

    logger.info(
        "The archive already holds %d readings for %s; skipping the sweep and "
        "carrying them forward instead.",
        measured, as_of,
    )
    return True


def _record_attention(rows: list[dict], as_of: str | None) -> dict[str, dict]:
    """
    Measure today's coverage, append it to the archive, and return it enriched
    with each stock's multiple of its own normal.

    Failures here must not stop the scan from publishing. Price data is the
    product; attention is an addition to it, and losing a day of the archive is
    a smaller harm than replacing a good published file with nothing.
    """
    tickers = [row["t"] for row in rows]
    try:
        measurements = measure_attention(tickers, on=as_of)
    except Exception as exc:  # noqa: BLE001
        logger.error("Attention measurement failed: %s", exc)
        return {}

    logger.info("Attention archive: %s", attention_archive.ARCHIVE_PATH)
    try:
        archive = attention_archive.record(measurements, on=as_of)
    except Exception as exc:  # noqa: BLE001
        logger.error("Could not write the attention archive: %s", exc)
        return measurements

    unusual = 0
    for ticker, reading in measurements.items():
        multiple = attention_archive.attention_multiple(
            archive, ticker, reading["velocity"]
        )
        reading["multiple"] = multiple
        if multiple and multiple >= attention_archive.UNUSUAL_ATTENTION_MULTIPLE:
            unusual += 1

    days = len(archive.get("dates", []))
    if days < attention_archive.MIN_HISTORY_FOR_BASELINE:
        logger.info(
            "Attention archive holds %d of the %d days needed before coverage "
            "can be called unusual.",
            days, attention_archive.MIN_HISTORY_FOR_BASELINE,
        )
    else:
        logger.info("%d stocks are getting unusual coverage", unusual)

    return measurements


if __name__ == "__main__":
    raise SystemExit(main())
