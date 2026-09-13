"""
Response models for the explanation endpoint.

Kept separate from `schemas/api.py` because this is the one part of the API
that is meant to be depended on by somebody else's code. Everything here is a
published contract: fields get added, never renamed or repurposed, and the
shape is flat enough to render without unpacking.
"""

from __future__ import annotations

from typing import Optional

from pydantic import BaseModel, Field

# Carried on every response so it reaches whatever renders the sentence.
# The product makes no forecast and no recommendation, and a consumer
# embedding this beside a position needs that to travel with the text rather
# than live in a contract they read once.
DISCLOSURE = "Descriptive only. Not investment advice, and not a forecast."


class Attribution(BaseModel):
    """Where the move came from, against the market and the sector."""

    text: Optional[str] = Field(
        None,
        description="One sentence placing the move against its sector and the market.",
    )
    market_percent: Optional[float] = Field(
        None, description="The market's move today, as the median of the universe."
    )
    sector: Optional[str] = Field(None, description="GICS sector.")
    sector_percent: Optional[float] = Field(
        None, description="This sector's move today, as the median of its members."
    )


class Coverage(BaseModel):
    """How much is being written about the company."""

    articles_per_day: Optional[float] = Field(
        None, description="News articles per day, measured over the recent window."
    )
    multiple_of_normal: Optional[float] = Field(
        None,
        description=(
            "Today's coverage against this company's own median. Null until "
            "there is enough history to say — which is the honest answer, not "
            "a missing value."
        ),
    )


class Filing(BaseModel):
    """An 8-K this company filed for the session being described."""

    items: list[str] = Field(
        default_factory=list,
        description="SEC Form 8-K item codes, most notable first (e.g. 2.02).",
    )
    reported: Optional[str] = Field(
        None, description="What the filing reported, in plain English."
    )
    accepted_at: Optional[str] = Field(
        None, description="When EDGAR accepted it (UTC, ISO 8601)."
    )
    url: Optional[str] = Field(
        None, description="The filing on EDGAR, so the wording can be checked."
    )
    note: str = Field(
        "Filed on the same session. Same-day is adjacency, not cause.",
        description=(
            "Carried so the caveat travels with the fact. The filing and the "
            "move happened on the same day; nothing here claims one produced "
            "the other."
        ),
    )


class Movement(BaseModel):
    """The move itself."""

    price: Optional[float] = None
    change_percent: Optional[float] = Field(None, description="Today's move, percent.")
    change_percent_2w: Optional[float] = Field(
        None, description="Change over the past two weeks, percent."
    )
    typical_percent: Optional[float] = Field(
        None, description="This stock's typical daily move, percent."
    )
    multiple_of_typical: Optional[float] = Field(
        None, description="Today's move as a multiple of that typical day."
    )
    state: Optional[str] = Field(None, description="rising | falling | steady, over two weeks.")


class Explanation(BaseModel):
    """What happened to one stock, and why, in language safe to render."""

    ticker: str
    company: Optional[str] = None
    as_of: Optional[str] = Field(None, description="The trading session measured.")
    generated_at: Optional[str] = Field(
        None, description="When the scan that produced this ran (UTC, ISO 8601)."
    )
    explanation: Optional[str] = Field(
        None, description="One factual sentence a reader can check against the chart."
    )
    movement: Movement
    attribution: Attribution
    coverage: Coverage
    filing: Optional[Filing] = Field(
        None, description="The 8-K filed for this session, when there was one."
    )
    disclosure: str = DISCLOSURE


class ExplanationBatch(BaseModel):
    """Several at once, plus whatever was asked for and not found."""

    as_of: Optional[str] = None
    generated_at: Optional[str] = None
    count: int
    explanations: list[Explanation]
    not_found: list[str] = Field(
        default_factory=list,
        description="Requested tickers the most recent scan did not cover.",
    )
    disclosure: str = DISCLOSURE
