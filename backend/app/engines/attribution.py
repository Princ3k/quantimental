"""
Move attribution — how much of today's move was this company, and how much was
everything else?

The gap this fills
------------------

"NVDA is down 4%" is the same sentence whether the whole market fell or NVDA
alone was hit, and those are completely different situations for someone
holding it. Every tool shows the same -4%. A list of headlines does not
separate them either, which is why a general-purpose assistant currently
answers "why is NVDA down?" better than a headline feed does.

Separating them requires knowing what every *other* stock did on the same day.
The scan already downloads all 503 constituents, so the answer is arithmetic on
data that is already in memory — and it is something no assistant can produce
without running the same sweep.

The claim, kept narrow
----------------------

This deliberately does **not** estimate beta or run a factor model. A proper
risk decomposition would regress each stock on the market, and the residual
could then be called "company-specific". That is a stronger claim resting on an
estimated parameter, and it is not one this product needs.

What is reported instead is a comparison anyone can check against two other
numbers on the same page: the sector moved this much, the stock moved that
much. Whether the difference is *meaningful* is judged against the stock's own
typical daily range, the same yardstick the rest of the app uses — a 0.4-point
gap is noise for a stock that swings 6% a day and a real divergence for one
that swings 0.5%.

Medians, not means: one company halving on an earnings miss should not redefine
what its whole sector did that day.
"""

from __future__ import annotations

import logging
import statistics
from typing import Any, Iterable, Optional

logger = logging.getLogger(__name__)

# How large the gap between a stock and its sector must be, relative to that
# stock's own typical daily move, before it is called a divergence rather than
# noise. Half a normal day's range is a low bar deliberately: the interesting
# claim is "this tracked its sector", and that should not be asserted loosely.
DIVERGENCE_FRACTION = 0.5

# Below this many members, a sector median describes a handful of companies
# rather than a sector. The S&P's smallest is Energy at 21.
MIN_SECTOR_MEMBERS = 8

# Moves smaller than this are described as flat rather than given a direction
# they do not really have. Matches app/engines/describe.py.
FLAT_THRESHOLD_PCT = 0.5

# Below this many benchmark members present in a scan, the basket describes a
# handful of companies rather than a market, and the whole scan is the better
# estimate. Set well under 503 so an ordinary day of missing prices does not
# trip it, and well over the point where a median stops meaning anything.
MIN_BENCHMARK_MEMBERS = 100


def _phrase(pct: float) -> str:
    if pct > FLAT_THRESHOLD_PCT:
        return f"rose {pct:.1f}%"
    if pct < -FLAT_THRESHOLD_PCT:
        return f"fell {abs(pct):.1f}%"
    return "was flat"


def _market_move(
    measurements: list[dict[str, Any]],
    benchmark: Optional[Iterable[str]],
) -> float:
    """The market's move: the median of a named basket, not of whatever ran.

    These are the same number today, and will not stay that way. "The market
    was flat" has been the median of the scanned universe, so the day the scan
    adds small caps that sentence quietly starts describing a different market
    — in Apple's row as much as in the new ones, with nothing on the page to
    show the word changed meaning. Someone checking "the market was flat"
    against the index on their own screen would find the two disagreeing and
    have no way to see why.

    Pinning it to a basket lets the universe grow without redefining the term.
    A basket too thin to be a market falls back to the whole scan and says so,
    because a median of eleven companies is worse than the alternative.
    """
    moves = [m["change_percent"] for m in measurements]
    if benchmark:
        wanted = set(benchmark)
        in_basket = [
            m["change_percent"] for m in measurements if m["ticker"] in wanted
        ]
        if len(in_basket) >= MIN_BENCHMARK_MEMBERS:
            return statistics.median(in_basket)
        logger.warning(
            "Only %d of %d benchmark members were scanned; falling back to the "
            "whole universe for the market median.",
            len(in_basket),
            len(wanted),
        )
    return statistics.median(moves)


def decompose(
    measurements: list[dict[str, Any]],
    sectors: dict[str, str],
    benchmark: Optional[Iterable[str]] = None,
) -> dict[str, dict[str, Any]]:
    """
    Attribute each stock's move against the market and its sector.

    Args:
        measurements: Scan rows, each with `ticker`, `change_percent` and
            `typical_percent`.
        sectors: Ticker to GICS sector.
        benchmark: The tickers that define "the market". Omit and the whole
            scan is used, which is correct only while the two are the same
            set — see `_market_move`.

    Returns:
        Per ticker: the market move, the sector move, the gap between the stock
        and its sector, whether that gap is a real divergence, and a sentence.
        Tickers in a sector too small to summarise are omitted rather than
        given a median of four companies.
    """
    if not measurements:
        return {}

    market = _market_move(measurements, benchmark)

    by_sector: dict[str, list[float]] = {}
    for row in measurements:
        sector = sectors.get(row["ticker"], "")
        if sector:
            by_sector.setdefault(sector, []).append(row["change_percent"])

    sector_moves = {
        sector: statistics.median(moves)
        for sector, moves in by_sector.items()
        if len(moves) >= MIN_SECTOR_MEMBERS
    }

    result: dict[str, dict[str, Any]] = {}
    for row in measurements:
        ticker = row["ticker"]
        sector = sectors.get(ticker, "")
        if sector not in sector_moves:
            continue

        sector_move = sector_moves[sector]
        gap = row["change_percent"] - sector_move

        # Judged against this stock's own normal day, not a fixed threshold.
        typical = row.get("typical_percent") or 0.0
        diverged = typical > 0 and abs(gap) >= typical * DIVERGENCE_FRACTION

        result[ticker] = {
            "market_percent": round(market, 2),
            "sector": sector,
            "sector_percent": round(sector_move, 2),
            "gap": round(gap, 2),
            "diverged": diverged,
        }

    return result


def _ends(text: str) -> str:
    """Close a sentence without doubling a period the last word already has.

    Thirty of the S&P 500 are named "... Inc." or "... Corp.", so a template
    that appends its own period rendered "specific to Apple Inc.." on six
    percent of rows — on the site, in the API, and anywhere the sentence was
    embedded.
    """
    return text if text.endswith((".", "!", "?")) else text + "."


def explain(
    company: str,
    change_percent: float,
    attribution: Optional[dict[str, Any]],
) -> Optional[str]:
    """
    One sentence putting the move in context, or None when there is none.

    Both numbers are stated so the reader can do the subtraction themselves —
    which is also why this avoids saying "2.8% more than its sector". That
    difference is in percentage points, and writing it as a percentage would be
    wrong in a way most readers would never catch.
    """
    if not attribution:
        return None

    sector = attribution["sector"]
    sector_pct = attribution["sector_percent"]
    market_pct = attribution["market_percent"]

    context = f"The market {_phrase(market_pct)} today and {sector} {_phrase(sector_pct)}"

    if not attribution["diverged"]:
        return _ends(
            f"{context}, so this move tracked the market rather than anything specific to {company}"
        )

    stock_up = change_percent > FLAT_THRESHOLD_PCT
    stock_down = change_percent < -FLAT_THRESHOLD_PCT
    sector_up = sector_pct > FLAT_THRESHOLD_PCT
    sector_down = sector_pct < -FLAT_THRESHOLD_PCT

    # Opposite directions is the sharper observation, and worth saying plainly.
    if (stock_up and sector_down) or (stock_down and sector_up):
        return f"{context} — so {company} moved against its sector."

    # A stock that stayed put while its sector moved is the case the generic
    # wording got wrong: "most of this was specific to Nvidia" is nonsense
    # about a 0.03% day. Not participating is the story, so say that.
    if not stock_up and not stock_down and (sector_up or sector_down):
        return f"{context} — so {company} did not follow its sector."

    return _ends(f"{context}, so most of this was specific to {company}")
