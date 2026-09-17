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

from typing import Optional

import discord

from client import Explanation, staleness_hours

# The app's own colours, resolved to ints. Green and red mean up and down here
# exactly as they do on the site; nothing else in the embed uses them.
UP = 0x1F7C4B
DOWN = 0xB5432F
FLAT = 0x55524F

# Past this, the scan behind a response is old enough that saying "today" would
# be a claim we cannot support. Two hours covers an hourly scan missing a slot.
STALE_AFTER_HOURS = 2.0


def _colour(change: Optional[float]) -> int:
    if change is None or abs(change) < 0.5:
        return FLAT
    return UP if change > 0 else DOWN


def _pct(value: Optional[float]) -> str:
    if value is None:
        return "—"
    return f"{value:+.2f}%"


def stale_notice(generated_at: Optional[str]) -> Optional[str]:
    """A line to append when the underlying scan is old, else None."""
    hours = staleness_hours(generated_at)
    if hours is None or hours < STALE_AFTER_HOURS:
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


def digest(
    explanations: list[Explanation],
    *,
    as_of: Optional[str],
    generated_at: Optional[str],
    missing: Optional[list[str]] = None,
) -> discord.Embed:
    """The daily post: one embed for a whole watchlist.

    One embed rather than one per stock. Twenty separate embeds is a wall that
    nobody reads and that Discord rate-limits; a single ordered list is the
    shape someone actually scans over morning coffee.
    """
    embed = discord.Embed(
        title="Today's watchlist",
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
            lines.append(f"{arrow} **{e.ticker}** {_pct(change)} — {e.explanation or ''}".rstrip(" —"))
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
    embed = discord.Embed(title="Unusual moves today", colour=FLAT)

    if feed.movers:
        lines = []
        for m in feed.movers:
            arrow = "▲" if m.get("direction") == "up" else "▼"
            # The API's own headline, which already carries the multiple and
            # the typical move. Nothing is rephrased here.
            lines.append(f"{arrow} **{m.get('ticker')}** — {m.get('headline') or ''}".rstrip(" —"))
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
                f"Scanned {feed.scanned or '—'} companies."
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
