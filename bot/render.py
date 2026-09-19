"""
Turning an Explanation into something Discord shows.

The rule this file exists to hold: nothing is added to the API's own wording.
The sentence it publishes has been through a no-forecast test suite; a summary
written here would not have been. So the embed arranges the API's text and its
numbers, and writes nothing of its own beyond labels.

Two consequences worth stating, because both are easy to undo by accident:

- The disclosure is rendered from the response field, never from a constant
  here. If the API changes what it discloses, the change reaches Discord
  without anyone redeploying the bot.
- A filing is shown beside a move, never as its reason. The API ships a `note`
  saying same-day is adjacency and not cause; that note is rendered with it.
"""

from __future__ import annotations

import os
from datetime import datetime
from typing import Optional

import discord

import schedule
from client import Explanation, staleness_hours

# Every embed links back. A ticker in a channel is a dead end otherwise, and
# the stock page carries the chart, the two-week history and the filing text
# that an embed has no room for — plus /method, which is where the claim that
# any of this is descriptive rather than predictive is actually made good.
SITE = os.environ.get("QUANTIMENTAL_SITE", "https://www.thequantimental.com").rstrip("/")


def stock_url(ticker: str) -> str:
    """The page for one company. Routes are lower-cased."""
    return f"{SITE}/stock/{(ticker or '').strip().lower()}"


def _linked(ticker: str) -> str:
    """A ticker as a markdown link — Discord renders it without showing a URL."""
    return f"[{ticker}]({stock_url(ticker)})"

# The app's own colours, resolved to ints. Green and red mean up and down here
# exactly as they do on the site; nothing else in the embed uses them.
UP = 0x1F7C4B
DOWN = 0xB5432F
FLAT = 0x55524F

# Staleness is measured against whether a scan was due, not against the clock.
#
# The first version warned past two wall-clock hours, which meant it fired every
# morning and all weekend — the scans run weekdays 14:13 to 21:43 UTC, so
# overnight the last session's close is the current answer and nothing is late.
# A warning that is on most of the time is one nobody reads, and then it is not
# there on the day a scan has actually died.
#
# Inside the window, two and a half hours is roughly two missed hourly slots.
# Outside it, three days spans a long weekend and still catches a dead scan.
STALE_DURING_SCANS_HOURS = 2.5
STALE_OUT_OF_HOURS = 72.0

# Discord's cap on one embed field. Going over does not truncate the field — it
# rejects the whole embed, so the post fails to send, and since a failed send is
# deliberately not marked done, it retries and fails every fifteen minutes until
# the session is abandoned. Six 8-K filings with EDGAR URLs came to 1221
# characters on the first day this ran, which is how this limit was found.
FIELD_LIMIT = 1024

# An embed description gets a larger budget than a field does.
DESCRIPTION_LIMIT = 4096

# Room for the "+N more" marker when lines have to be dropped.
_MORE_ALLOWANCE = 24


def _fit(lines: list[str], *, suffix: str = "", limit: int = FIELD_LIMIT) -> str:
    """As many whole lines as fit, then a count of what was left out.

    Never a half-rendered line: a truncated markdown link renders as raw text
    and a truncated URL is a broken one.
    """
    joined = "\n".join(lines) + suffix
    if len(joined) <= limit:
        return joined

    kept: list[str] = []
    used = len(suffix) + _MORE_ALLOWANCE
    for line in lines:
        if used + len(line) + 1 > limit:
            break
        kept.append(line)
        used += len(line) + 1

    dropped = len(lines) - len(kept)
    return "\n".join(kept) + f"\n_+{dropped} more_" + suffix


def _colour(change: Optional[float]) -> int:
    if change is None or abs(change) < 0.5:
        return FLAT
    return UP if change > 0 else DOWN


def _pct(value: Optional[float]) -> str:
    if value is None:
        return "—"
    return f"{value:+.2f}%"


def stale_notice(
    generated_at: Optional[str], *, now: Optional[datetime] = None
) -> Optional[str]:
    """A line to append when a scan is genuinely overdue, else None."""
    hours = staleness_hours(generated_at, now=now)
    if hours is None:
        return None
    limit = (
        STALE_DURING_SCANS_HOURS
        if schedule.scan_expected(now)
        else STALE_OUT_OF_HOURS
    )
    if hours < limit:
        return None
    if hours < 48:
        return f"⚠️ Latest scan is {hours:.0f} hours old."
    return f"⚠️ Latest scan is {hours / 24:.0f} days old."


def one(explanation: Explanation) -> discord.Embed:
    """A single stock, in full."""
    e = explanation
    move = e.movement
    change = move.get("change_percent")

    embed = discord.Embed(
        title=f"{e.ticker} · {e.company}" if e.company else e.ticker,
        url=stock_url(e.ticker),
        description=e.explanation or "No description published for this session.",
        colour=_colour(change),
    )

    price = move.get("price")
    embed.add_field(name="Price", value=f"${price:,.2f}" if price else "—", inline=True)
    embed.add_field(name="Today", value=_pct(change), inline=True)
    embed.add_field(name="Two weeks", value=_pct(move.get("change_percent_2w")), inline=True)

    multiple = move.get("multiple_of_typical")
    if multiple is not None:
        # Stated against the stock's own normal day, which is the only way the
        # number means anything across a utility and a small-cap biotech.
        embed.add_field(
            name="Versus its normal day",
            value=f"{multiple:.1f}x  (typical {_pct(move.get('typical_percent'))})",
            inline=False,
        )

    if e.attribution.get("text"):
        embed.add_field(name="Context", value=e.attribution["text"], inline=False)

    articles = e.coverage.get("articles_per_day")
    if articles is not None:
        coverage = f"{articles:.0f} articles/day"
        normal = e.coverage.get("multiple_of_normal")
        # Absent until the archive holds enough history. Saying nothing is the
        # honest answer then, rather than a multiple of four observations.
        if normal is not None:
            coverage += f" · {normal:.1f}x its normal"
        embed.add_field(name="Coverage", value=coverage, inline=False)

    if e.filing:
        embed.add_field(name="SEC filing", value=_filing(e.filing), inline=False)

    footer = e.disclosure
    notice = stale_notice(e.generated_at)
    if notice:
        footer = f"{notice}\n{footer}" if footer else notice
    if e.as_of:
        footer = f"Session of {e.as_of}\n{footer}" if footer else f"Session of {e.as_of}"
    embed.set_footer(text=footer)
    return embed


def _filing(filing: dict) -> str:
    items = ", ".join(filing.get("items") or []) or "8-K"
    lines = [f"**{items}** — {filing.get('reported') or 'filed this session'}"]
    if filing.get("url"):
        lines.append(f"[Read it on EDGAR]({filing['url']})")
    # The caveat travels with the fact, as the API intends.
    if filing.get("note"):
        lines.append(f"_{filing['note']}_")
    return "\n".join(lines)


def close_post(
    explanations: list[Explanation],
    *,
    as_of: Optional[str],
    generated_at: Optional[str],
    unusual_feed=None,
    filings: Optional[list[dict]] = None,
    missing: Optional[list[str]] = None,
) -> Optional[discord.Embed]:
    """The one post a day, after the close.

    One embed, not three. A server that gets a watchlist post, an unusual-moves
    post and a filings post gets muted; the same content in one block after the
    close is a market summary someone reads.

    Every section is optional and appears only when it has something in it,
    which is what lets this work with no configuration at all: a server that has
    only run `/watch here` still gets unusual moves and filings, because those
    are about the market rather than about their list. Returns None when there
    is nothing in any section, because a daily post saying nothing happened is
    how a bot teaches a channel to ignore it.
    """
    movers = list(getattr(unusual_feed, "movers", None) or [])
    filed = list(filings or [])
    if not explanations and not movers and not filed:
        return None

    embed = discord.Embed(
        title="After the close",
        url=SITE,
        colour=FLAT,
    )

    if movers:
        embed.add_field(
            name="Moved unusually",
            value=_fit([
                f"{'▲' if m.get('direction') == 'up' else '▼'} "
                f"**{_linked(m.get('ticker', ''))}** — {m.get('headline') or ''}".rstrip(" —")
                for m in movers[:8]
            ]),
            inline=False,
        )

    if filed:
        embed.add_field(
            name=f"Filed an 8-K ({len(filed)})",
            # The caveat is carried once for the block rather than on every
            # line, and is passed as a suffix so it survives truncation — it
            # must travel with the facts even when some of them are dropped.
            value=_fit(
                [_filing_line(f) for f in filed],
                suffix="\n_Filed the same session. Same-day is adjacency, not cause._",
            ),
            inline=False,
        )

    if explanations:
        embed.add_field(
            name="Your watchlist",
            value=_watchlist_lines(explanations),
            inline=False,
        )

    if missing:
        embed.add_field(name="Not covered", value=", ".join(missing), inline=False)

    footer = []
    if as_of:
        footer.append(f"Session of {as_of}")
    notice = stale_notice(generated_at)
    if notice:
        footer.append(notice)
    disclosure = next((e.disclosure for e in explanations if e.disclosure), None)
    footer.append(disclosure or "Descriptive only. Not investment advice, and not a forecast.")
    embed.set_footer(text="\n".join(footer))
    return embed


def _filing_line(f: dict) -> str:
    items = ", ".join(f.get("items") or []) or "8-K"
    ticker = _linked(f.get("ticker", ""))
    body = f"**{ticker}** {items} — {f.get('reported') or 'filed this session'}"
    return f"{body} · [EDGAR]({f['url']})" if f.get("url") else body


def _watchlist_lines(explanations: list[Explanation]) -> str:
    ordered = sorted(
        explanations,
        key=lambda e: abs(e.movement.get("change_percent") or 0.0),
        reverse=True,
    )
    lines = []
    for e in ordered:
        change = e.movement.get("change_percent")
        arrow = "▲" if (change or 0) > 0 else "▼" if (change or 0) < 0 else "▬"
        lines.append(
            f"{arrow} **{_linked(e.ticker)}** {_pct(change)} — {e.explanation or ''}".rstrip(" —")
        )
    return _fit(lines)


def digest(
    explanations: list[Explanation],
    *,
    as_of: Optional[str],
    generated_at: Optional[str],
    missing: Optional[list[str]] = None,
) -> discord.Embed:
    """A watchlist on its own. Kept for /watch list-style use and its tests."""
    embed = discord.Embed(
        title="Today's watchlist",
        url=f"{SITE}/stocks",
        colour=FLAT,
    )

    if not explanations:
        embed.description = "Nothing to report — no watched tickers were covered."
    else:
        # Largest absolute move first: the reason to open the post is whatever
        # actually moved, not whichever ticker happens to sort first.
        ordered = sorted(
            explanations,
            key=lambda e: abs(e.movement.get("change_percent") or 0.0),
            reverse=True,
        )
        lines = []
        for e in ordered:
            change = e.movement.get("change_percent")
            arrow = "▲" if (change or 0) > 0 else "▼" if (change or 0) < 0 else "▬"
            lines.append(
                f"{arrow} **{_linked(e.ticker)}** {_pct(change)} — {e.explanation or ''}".rstrip(" —")
            )
        embed.description = "\n".join(lines)

    if missing:
        embed.add_field(
            name="Not covered",
            value=", ".join(missing),
            inline=False,
        )

    footer_parts = []
    if as_of:
        footer_parts.append(f"Session of {as_of}")
    notice = stale_notice(generated_at)
    if notice:
        footer_parts.append(notice)
    if explanations and explanations[0].disclosure:
        footer_parts.append(explanations[0].disclosure)
    embed.set_footer(text="\n".join(footer_parts))
    return embed


def unusual(feed) -> discord.Embed:
    """Today's unusual moves.

    Two rules this holds, both easy to undo by accident:

    - The threshold is stated. "Unusual" is a measured claim — a multiple of
      each stock's own typical daily range — and a reader cannot judge the list
      without knowing what bar it cleared.
    - A quiet day says so. `biggest` is carried by the API but is *not* a list
      of unusual moves, so when nothing qualifies this says nothing qualified
      rather than promoting the largest ordinary move to fill the space. The
      product describes silence; so does this.
    """
    embed = discord.Embed(title="Unusual moves today", url=SITE, colour=FLAT)

    if feed.movers:
        lines = []
        for m in feed.movers:
            arrow = "▲" if m.get("direction") == "up" else "▼"
            # The API's own headline, which already carries the multiple and
            # the typical move. Nothing is rephrased here.
            lines.append(
                f"{arrow} **{_linked(m.get('ticker', ''))}** — {m.get('headline') or ''}".rstrip(" —")
            )
        embed.description = "\n".join(lines)

        for m in feed.movers[:3]:
            if m.get("context"):
                embed.add_field(name=m.get("ticker", "—"), value=m["context"], inline=False)
    else:
        embed.description = (
            "Nothing moved unusually today — no stock cleared the threshold below."
        )
        if feed.biggest:
            largest = feed.biggest[0]
            embed.add_field(
                name="Largest ordinary move",
                value=(
                    f"**{largest.get('ticker')}** {_pct(largest.get('change_percent'))}, "
                    f"{largest.get('multiple')}x its typical "
                    f"{_pct(largest.get('typical_percent'))} day — which is "
                    f"within its normal range."
                ),
                inline=False,
            )

    bar = feed.threshold or {}
    if bar:
        embed.add_field(
            name="What counts as unusual",
            value=(
                f"A move of at least {bar.get('min_move_percent')}% that is also "
                f"{bar.get('multiple')}x the stock's own typical daily range. "
                f"Scanned {feed.scanned or '—'} companies. "
                f"[How this is measured]({SITE}/method)"
            ),
            inline=False,
        )

    footer = []
    if feed.as_of:
        footer.append(f"Session of {feed.as_of}")
    notice = stale_notice(feed.generated_at)
    if notice:
        footer.append(notice)
    if feed.disclosure:
        footer.append(feed.disclosure)
    embed.set_footer(text="\n".join(footer))
    return embed


def desk(payload: dict) -> discord.Embed:
    """The Signal Desk: the market as a whole, as last published."""
    composite = payload.get("composite") or {}
    narrative = payload.get("narrative") or {}
    sectors = payload.get("sectors") or {}

    embed = discord.Embed(
        title="Market today",
        url=SITE,
        description=narrative.get("text") or narrative.get("short") or "",
        colour=FLAT,
    )

    score = composite.get("score")
    if score is not None:
        # Named exactly as the site names it. A number out of 100 with a
        # different label in each place it appears is how two descriptions of
        # one measurement start to disagree.
        embed.add_field(
            name="Risk appetite",
            value=f"**{score}** / 100 · {composite.get('label') or ''}".strip(" ·"),
            inline=False,
        )

    notable = [s for s in (payload.get("signals") or []) if s.get("notable")]
    if notable:
        embed.add_field(
            name="What moved",
            value="\n".join(
                f"{'▲' if s.get('direction') == 'up' else '▼'} {s.get('text')} "
                f"({s.get('delta')})"
                for s in notable[:6]
            ),
            inline=False,
        )

    if sectors.get("available"):
        leaders = ", ".join(s.get("name", "") for s in (sectors.get("leaders") or [])[:3])
        laggards = ", ".join(s.get("name", "") for s in (sectors.get("laggards") or [])[:3])
        if leaders or laggards:
            embed.add_field(
                name="Sectors",
                value=f"Leading: {leaders or '—'}\nLagging: {laggards or '—'}",
                inline=False,
            )

    footer = []
    if payload.get("as_of"):
        footer.append(f"Session of {str(payload['as_of'])[:10]}")
    notice = stale_notice(payload.get("generated_at"))
    if notice:
        footer.append(notice)
    if payload.get("disclosure"):
        footer.append(payload["disclosure"])
    embed.set_footer(text="\n".join(footer))
    return embed


def filings(feed) -> discord.Embed:
    """The 8-Ks companies filed for this session.

    Ordered as the API returns them — by item code, most notable first, which
    is a judgement about the document. Deliberately not re-sorted here by how
    far the stock moved: ordering filings by price action is a causal claim
    made with a sort key, and the whole point is that these two things happened
    on the same day and the reader decides what that means.
    """
    embed = discord.Embed(
        title=f"8-K filings today ({feed.count})" if feed.count else "8-K filings today",
        url=SITE,
        colour=FLAT,
    )

    if not feed.filings:
        embed.description = (
            "No 8-K filings from the covered universe this session. "
            "Quiet days are normal — most companies file a handful a year."
        )
    else:
        embed.description = _fit(
            [_filing_line(f) for f in feed.filings],
            suffix="\n_Filed the same session. Same-day is adjacency, not cause._",
            # Embed descriptions get a larger allowance than fields do.
            limit=DESCRIPTION_LIMIT,
        )

    footer = []
    if feed.as_of:
        footer.append(f"Session of {feed.as_of}")
    notice = stale_notice(feed.generated_at)
    if notice:
        footer.append(notice)
    if feed.disclosure:
        footer.append(feed.disclosure)
    embed.set_footer(text="\n".join(footer))
    return embed


def help_embed() -> discord.Embed:
    """What the bot does, for someone who has just seen it appear in a channel.

    Written for a member, not an operator: what they can type, what the numbers
    mean, and where the claim that none of this is a forecast is made good. The
    admin commands are listed too rather than hidden, because a member who
    cannot use them should still know why a daily post exists and who to ask.
    """
    embed = discord.Embed(
        title="Quantimental",
        url=SITE,
        description=(
            "Describes what the market and your stocks did — and refuses to say "
            "what they will do next. Every sentence here is derived from a "
            "measured number you can check against a chart."
        ),
        colour=FLAT,
    )

    embed.add_field(
        name="Anyone can use",
        value="\n".join([
            "`/stock TICKER` — what one company did this session",
            "`/unusual` — stocks that moved far beyond their *own* normal range",
            "`/market` — what the market as a whole did",
            "`/filings` — the 8-Ks companies filed this session",
        ]),
        inline=False,
    )

    embed.add_field(
        name="Server managers",
        value="\n".join([
            "`/watch here` — post a daily summary in this channel after the close",
            "`/watch add TICKER` · `/watch remove` · `/watch list`",
        ]),
        inline=False,
    )

    embed.add_field(
        name="Your own list",
        value="\n".join([
            "`/my add TICKER` · `/my remove TICKER`",
            "`/my today` — what your stocks did, shown only to you",
            "`/my clear` — delete it and everything stored for you",
            "",
            "Private to you, and nothing is ever sent to you unasked.",
        ]),
        inline=False,
    )

    embed.add_field(
        name='What "unusual" means',
        value=(
            "Measured against each stock's own typical daily range, not a fixed "
            "percentage — so a 3% day counts for a utility and does not for a "
            f"volatile small cap. [How it is measured]({SITE}/method)"
        ),
        inline=False,
    )

    embed.add_field(
        name="Coverage",
        value=(
            "The S&P 500. Ask for anything else and it will say so — those "
            "requests are counted, and what people ask for is how the list grows."
        ),
        inline=False,
    )

    embed.set_footer(text="Descriptive only. Not investment advice, and not a forecast.")
    return embed
