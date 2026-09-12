"""
Describe Engine — "what is happening to this stock, and why?"

This replaces the five-point buy/sell verdict as the thing the product leads
with. The reason is evidentiary, not stylistic.

A verdict is a claim about the future. A walk-forward backtest of 1,888
observations found no statistically significant edge in ours (t-stats between
-1.98 and 1.32), and the sentiment half of the score — 55% of its weight — has
never been tested at all, because no archive of historical sentiment exists to
test it against. Leading with "Buy" asserts something we cannot support.

Everything in here is instead a statement about the present or the past, and
every one of them is checkable against the chart or the headlines the reader
can see on the same screen. The rules that follow from that:

- **No forecasts.** No "expect", "likely", "should", "poised to", "set to".
- **Numbers carry their own units and windows.** "down 6.3% over two weeks",
  never "weak".
- **Unusual is measured, not asserted.** A move is called large only relative
  to that stock's own recent daily range, so a 3% day is remarkable for a
  utility and unremarkable for a small-cap biotech.
- **Silence is stated.** When there is nothing notable, the description says
  the stock has been quiet rather than manufacturing drama.
"""

from __future__ import annotations

from typing import Any, Optional

# A day's move is called out only when it is this many times the stock's own
# average daily range. Below it, the move is ordinary for this stock, whatever
# it looks like in absolute percent.
UNUSUAL_MOVE_MULTIPLE = 1.8

# Below this, a percentage move is noise and gets described as "little changed"
# rather than given a direction it does not really have.
FLAT_THRESHOLD_PCT = 0.5

# Two weeks of trading, which is the window price_change_10d covers.
PERIOD_LABEL = "two weeks"

TREND_PHRASES: dict[str, str] = {
    "strong_uptrend": "has been climbing steadily",
    "uptrend": "has drifted upward",
    "sideways": "has moved sideways",
    "downtrend": "has drifted downward",
    "strong_downtrend": "has been falling steadily",
}


def _direction(pct: float) -> str:
    if pct > FLAT_THRESHOLD_PCT:
        return "up"
    if pct < -FLAT_THRESHOLD_PCT:
        return "down"
    return "flat"


def _move_phrase(pct: float) -> str:
    """'up 2.1%' / 'down 2.1%' / 'little changed'."""
    direction = _direction(pct)
    if direction == "flat":
        return "little changed"
    return f"{direction} {abs(pct):.1f}%"


def describe(
    company: str,
    change_percent: float,
    indicators: dict[str, Any],
    sentiment: Optional[dict[str, Any]] = None,
) -> dict[str, Any]:
    """
    Build a factual description of where this stock stands.

    Args:
        company: Display name, used to open the headline sentence.
        change_percent: Today's move, as a percentage.
        indicators: The QuantEngine indicator dict.
        sentiment: The sentiment record, which may be unavailable.

    Returns:
        headline    — one sentence a reader can check against the chart
        state       — 'rising' | 'falling' | 'steady', over two weeks
        today       — {direction, percent, unusual}
        period      — {direction, percent, label}
        notable     — short factual observations, most significant first
        attention   — what coverage looks like, or None when unknown
    """
    period_pct = float(indicators.get("price_change_10d", 0.0) or 0.0)
    typical_daily = float(indicators.get("atr_percent", 0.0) or 0.0)

    # "Unusual" is relative to this stock's own behaviour, not an absolute
    # percentage. A fixed threshold would flag every volatile small-cap daily
    # and never flag a mega-cap having a genuinely remarkable day.
    unusual_today = bool(
        typical_daily > 0 and abs(change_percent) >= typical_daily * UNUSUAL_MOVE_MULTIPLE
    )

    period_direction = _direction(period_pct)
    state = {"up": "rising", "down": "falling", "flat": "steady"}[period_direction]

    return {
        "headline": _headline(company, change_percent, period_pct, unusual_today, indicators),
        "state": state,
        "today": {
            "direction": _direction(change_percent),
            "percent": round(change_percent, 2),
            "unusual": unusual_today,
        },
        "period": {
            "direction": period_direction,
            "percent": round(period_pct, 2),
            "label": PERIOD_LABEL,
        },
        "notable": _notable(indicators, change_percent, unusual_today, typical_daily),
        "attention": _attention(sentiment),
    }


def _headline(
    company: str,
    change_percent: float,
    period_pct: float,
    unusual_today: bool,
    indicators: dict[str, Any],
) -> str:
    """
    One sentence: what this stock did today, and how that sits against the
    past two weeks.

    The two clauses are joined by "and" or "but" depending on whether they
    agree, because "down today but up over two weeks" is a materially different
    situation from "down today and down over two weeks" — and that distinction
    is the single most useful thing a glance can carry.
    """
    today = _move_phrase(change_percent)
    period = _move_phrase(period_pct)

    today_dir = _direction(change_percent)
    period_dir = _direction(period_pct)

    # Both flat: nothing happened, and saying so plainly beats inventing a story.
    if today_dir == "flat" and period_dir == "flat":
        trend = TREND_PHRASES.get(indicators.get("trend", "sideways"), "has moved sideways")
        return f"{company} is little changed today, and {trend} over the past {PERIOD_LABEL}."

    opening = f"{company} is {today} today"
    if unusual_today:
        opening += " — a bigger move than usual for this stock"

    if period_dir == "flat":
        return f"{opening}, though it is {period} over the past {PERIOD_LABEL}."

    # Agreement reinforces; disagreement is the more interesting case.
    joiner = "and" if today_dir == period_dir or today_dir == "flat" else "but"
    return f"{opening}, {joiner} {period} over the past {PERIOD_LABEL}."


def _notable(
    indicators: dict[str, Any],
    change_percent: float,
    unusual_today: bool,
    typical_daily: float,
) -> list[str]:
    """
    Facts worth flagging, most significant first.

    Each is a statement about what has already happened. Where a marker is
    widely watched, that is said plainly rather than implying it works — a
    golden cross is notable because many people act on it, which is a fact
    about the market, not a claim about the stock.
    """
    notable: list[str] = []

    if unusual_today and typical_daily > 0:
        notable.append(
            f"Today's {abs(change_percent):.1f}% move is larger than this stock's "
            f"typical {typical_daily:.1f}% daily range."
        )

    if indicators.get("golden_cross"):
        notable.append(
            "Its 50-day average has just crossed above its 200-day average, "
            "a marker many traders watch."
        )
    elif indicators.get("death_cross"):
        notable.append(
            "Its 50-day average has just crossed below its 200-day average, "
            "a marker many traders watch."
        )

    price = float(indicators.get("price", 0.0) or 0.0)
    upper = float(indicators.get("bollinger_upper", price) or price)
    lower = float(indicators.get("bollinger_lower", price) or price)
    if upper > lower and price > 0:
        position = (price - lower) / (upper - lower)
        if position > 0.9:
            notable.append("It is trading at the top of its recent range.")
        elif position < 0.1:
            notable.append("It is trading at the bottom of its recent range.")

    volatility = indicators.get("volatility", "moderate")
    if volatility == "high":
        notable.append("Daily swings have been larger than usual recently.")
    elif volatility == "low":
        notable.append("Daily swings have been unusually small recently.")

    return notable


def _attention(sentiment: Optional[dict[str, Any]]) -> Optional[dict[str, Any]]:
    """
    How much is being written about this stock.

    Returns None rather than a zero when sentiment could not be gathered —
    "nobody is talking about it" and "we could not find out" are different
    statements, and only one of them is true.
    """
    if not sentiment or not sentiment.get("available"):
        return None

    mentions = int(sentiment.get("mentions", 0) or 0)
    velocity = sentiment.get("mention_velocity", "steady")

    if mentions == 0:
        summary = "No recent coverage found."
    else:
        article = "article" if mentions == 1 else "articles and posts"
        summary = f"{mentions:,} recent {article}"
        if velocity == "rising":
            summary += ", and coverage is picking up."
        elif velocity == "falling":
            summary += ", and coverage is fading."
        else:
            summary += "."

    return {"mentions": mentions, "velocity": velocity, "summary": summary}
