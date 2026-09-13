"""
Form 8-K item codes, in plain English.

The SEC already classifies why a company filed. Every 8-K carries one or more
numbered items from a fixed taxonomy, and EDGAR returns them as structured data
— so naming the catalyst needs no language model, no HTML parsing, and carries
no risk of inventing something the filing does not say.

Two rules govern the wording.

It describes the filing, never the move. "Reported quarterly results" is a fact
about a document; "fell on disappointing earnings" is a causal claim this
product does not make, and a same-day filing is adjacency rather than cause.
The reader is given both and draws the line themselves, which is the same
reason `attribution` prints both percentages instead of their difference.

And it says what the company did, not what the item is called. The official
title of 5.02 runs to twenty-three words covering four unrelated events; a
reader wants "a change among its directors or senior officers".
"""

from __future__ import annotations

from typing import Optional

# Item 9.01 is deliberately absent. It is the exhibit index — it rides along
# with whatever else was filed and means nothing on its own. It was also the
# single most common item in two years of measurement, so a mapping that
# included it would have made "financial statements and exhibits" the most
# frequent explanation on the site.
EXCLUDED_ITEMS = frozenset({"9.01"})

ITEM_PHRASES: dict[str, str] = {
    # Business and operations
    "1.01": "reporting a material agreement",
    "1.02": "reporting the end of a material agreement",
    "1.03": "reporting bankruptcy or receivership",
    "1.04": "reporting a mine safety matter",
    "1.05": "reporting a material cybersecurity incident",
    # Financial information
    "2.01": "reporting a completed acquisition or disposal",
    "2.02": "reporting quarterly results",
    "2.03": "reporting a new financial obligation",
    "2.04": "reporting that a financial obligation has been accelerated",
    "2.05": "reporting costs for exiting or closing part of the business",
    "2.06": "reporting a material write-down",
    # Securities and trading
    "3.01": "reporting a listing or delisting matter",
    "3.02": "reporting an unregistered sale of shares",
    "3.03": "reporting a change to shareholder rights",
    # Accountants and financial statements
    "4.01": "reporting a change of auditor",
    "4.02": "reporting that earlier financial statements cannot be relied on",
    # Governance and management
    "5.01": "reporting a change of control",
    "5.02": "reporting a change among its directors or senior officers",
    "5.03": "reporting a change to its articles, bylaws or fiscal year",
    "5.04": "reporting a trading suspension in its employee benefit plans",
    "5.05": "reporting a change to its code of ethics",
    "5.06": "reporting a change in shell company status",
    "5.07": "reporting the results of a shareholder vote",
    "5.08": "reporting shareholder director nominations",
    # Regulation FD and everything else
    "7.01": "making a Regulation FD disclosure",
    "8.01": "reporting another event",
}

# Which item leads when a filing carries several, most notable first.
#
# Ordered by how rare and consequential the event is, not by item number. A
# restatement outranks earnings; earnings outrank a Regulation FD disclosure,
# which is often just the press release attached to the earnings. Quarterly
# results sit below a change of officer because earnings arrive four times a
# year on a schedule everyone knows, and an officer leaving does not.
ITEM_PRIORITY: tuple[str, ...] = (
    "1.03",  # bankruptcy
    "4.02",  # restatement
    "5.01",  # change of control
    "1.05",  # cybersecurity incident
    "3.01",  # delisting
    "4.01",  # change of auditor
    "2.06",  # write-down
    "2.05",  # restructuring costs
    "5.02",  # officer or director change
    "2.01",  # acquisition or disposal
    "2.02",  # quarterly results
    "1.02",  # agreement ended
    "2.04",  # obligation accelerated
    "3.03",  # shareholder rights
    "3.02",  # unregistered sale
    "1.01",  # material agreement
    "2.03",  # new obligation
    "5.03",  # articles or fiscal year
    "5.07",  # shareholder vote
    "5.08",  # director nominations
    "5.04",  # benefit plan suspension
    "5.05",  # code of ethics
    "5.06",  # shell company status
    "1.04",  # mine safety
    "7.01",  # Regulation FD
    "8.01",  # other
)

_RANK = {item: rank for rank, item in enumerate(ITEM_PRIORITY)}


def meaningful(items: list[str]) -> list[str]:
    """The items worth showing, most notable first."""
    seen = {item.strip() for item in items if item.strip()}
    known = [item for item in seen if item in ITEM_PHRASES and item not in EXCLUDED_ITEMS]
    return sorted(known, key=lambda item: _RANK.get(item, len(ITEM_PRIORITY)))


def describe(items: list[str]) -> Optional[str]:
    """
    One phrase for a filing, or None when nothing in it is worth saying.

    Only the leading item is described. A filing carrying results, a Regulation
    FD disclosure and an exhibit index is, to a reader, the earnings filing —
    listing all three reads as a database dump rather than an explanation.
    """
    ranked = meaningful(items)
    return ITEM_PHRASES[ranked[0]] if ranked else None
