"""
The Quantimental Discord bot.

A tap on an API that already exists, not a second product. It holds no market
data, computes no figures and writes no descriptions: every sentence it posts
came from `/api/v1/explain`, which is the endpoint built to be embedded
elsewhere and the one whose wording is covered by the no-forecast tests.

Commands are slash commands. That avoids the message-content intent, which
needs Discord's approval past seventy-five servers and would mean reading every
message in every channel to find the few addressed to us.
"""

from __future__ import annotations

import asyncio
import logging
import os
import sys

import discord
from discord import app_commands
from discord.ext import tasks

import render
import schedule
from client import ApiUnavailable, QuantimentalClient
from misses import Misses
from personal import MAX_PER_PERSON, Personal
from store import MAX_PER_GUILD, Watchlists, check_durability

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s %(message)s",
)
logger = logging.getLogger("quantimental.bot")

TOKEN = os.environ.get("DISCORD_BOT_TOKEN", "")

# How often to check whether a new session has published. The scan runs hourly
# at most, so anything tighter is spent re-reading a file that has not changed.
POLL_MINUTES = 15


class QuantimentalBot(discord.Client):
    def __init__(self) -> None:
        # No privileged intents: this never reads message content, member lists
        # or presence. Guilds alone is enough to resolve a channel to post in.
        super().__init__(intents=discord.Intents(guilds=True))
        self.tree = app_commands.CommandTree(self)
        self.api = QuantimentalClient()
        self.lists = Watchlists()
        # Which tickers people ask for that the universe does not cover.
        self.misses = Misses()
        # Watchlists that belong to a person, keyed by a digest of their id.
        self.personal = Personal()

    async def setup_hook(self) -> None:
        # Says in the deploy logs whether watchlists will survive a redeploy.
        # It does not refuse to start: a bot that answers /stock is still worth
        # running, and the operator is the one who can fix the mount.
        check_durability(self.lists.path)
        await self.tree.sync()
        self.daily.start()

    async def on_guild_remove(self, guild: discord.Guild) -> None:
        """Forget a server the moment the bot is removed from it."""
        if self.lists.forget(guild.id):
            logger.info("Removed from a guild; its watchlist has been deleted.")

    # -- the scheduled post ------------------------------------------------

    @tasks.loop(minutes=POLL_MINUTES)
    async def daily(self) -> None:
        """Post each guild's close summary once per session, when one is ready."""
        guilds = self.lists.guilds()
        if not guilds:
            return

        # Market-wide first: these need no watchlist, and are the reason a
        # server that has only run /watch here still gets something every day.
        try:
            unusual = await self.api.unusual()
            filings = await self.api.filings()
        except ApiUnavailable as exc:
            logger.warning("Skipping this round; API unavailable: %s", exc)
            return

        # One explain call serves every guild. Cost is the number of distinct
        # companies anyone follows, not servers times tickers.
        rows: dict = {}
        batch = None
        wanted = self.lists.every_ticker()
        if wanted:
            try:
                batch = await self.api.explain(wanted[:100])
                rows = batch.by_ticker()
            except ApiUnavailable as exc:
                # The market-wide half is still worth posting without it.
                logger.warning("Watchlists unavailable this round: %s", exc)

        as_of = unusual.as_of
        generated_at = unusual.generated_at
        for guild_id in guilds:
            last = self.lists.get_posted(guild_id)
            if not schedule.should_post(as_of, generated_at, last):
                continue
            await self._post_close(guild_id, as_of, generated_at, unusual, filings, rows)

    async def _post_close(
        self, guild_id: int, as_of, generated_at, unusual, filings, rows
    ) -> None:
        channel_id = self.lists.channel(guild_id)
        if not channel_id:
            return
        channel = self.get_channel(channel_id)
        if channel is None:
            logger.warning("Guild %s: channel %s is gone.", guild_id, channel_id)
            return

        watched = self.lists.get(guild_id)
        mine = [rows[t] for t in watched if t in rows]
        missing = [t for t in watched if t not in rows]
        # A watched ticker that is never covered is the stronger signal: someone
        # wanted it tracked daily, not just looked up once.
        for ticker in missing:
            self.misses.record(ticker, guild_id)

        embed = render.close_post(
            mine,
            as_of=as_of,
            generated_at=generated_at,
            unusual_feed=unusual,
            filings=filings.filings,
            missing=missing,
        )
        if embed is None:
            # Nothing unusual, nothing filed, nothing watched. A daily post
            # saying so is how a channel learns to ignore the bot — but the
            # session is still marked done, so this does not retry all evening.
            self.lists.mark_posted(guild_id, as_of)
            return

        try:
            await channel.send(embed=embed)
        except discord.DiscordException as exc:
            logger.warning("Guild %s: could not post: %s", guild_id, exc)
            return
        # Recorded only after a successful send, so a failed post is retried on
        # the next poll rather than being marked done.
        self.lists.mark_posted(guild_id, as_of)

    @daily.before_loop
    async def _wait(self) -> None:
        await self.wait_until_ready()


bot = QuantimentalBot()


@bot.tree.command(description="What one stock did this session.")
@app_commands.describe(ticker="Ticker symbol, e.g. AAPL")
async def stock(interaction: discord.Interaction, ticker: str) -> None:
    await interaction.response.defer()
    try:
        batch = await bot.api.explain([ticker])
    except ApiUnavailable:
        await interaction.followup.send("Quantimental is unreachable right now.")
        return

    found = batch.by_ticker().get(ticker.strip().upper())
    if not found:
        # The answer to "should the universe expand, and to what" is this list.
        bot.misses.record(ticker, interaction.guild_id)
        await interaction.followup.send(
            f"{ticker.upper()} is not in the covered universe (the S&P 500) yet. "
            "It has been noted — what people ask for is how the universe grows."
        )
        return
    await interaction.followup.send(embed=render.one(found))


@bot.tree.command(description="Stocks that moved far beyond their own normal today.")
async def unusual(interaction: discord.Interaction) -> None:
    await interaction.response.defer()
    try:
        feed = await bot.api.unusual()
    except ApiUnavailable:
        await interaction.followup.send("Quantimental is unreachable right now.")
        return
    await interaction.followup.send(embed=render.unusual(feed))


@bot.tree.command(description="What this bot does and what you can ask it.")
async def help(interaction: discord.Interaction) -> None:
    """Ephemeral: a channel does not need everyone's help output in it."""
    await interaction.response.send_message(embed=render.help_embed(), ephemeral=True)


@bot.tree.command(description="The 8-K filings companies made this session.")
async def filings(interaction: discord.Interaction) -> None:
    await interaction.response.defer()
    try:
        feed = await bot.api.filings()
    except ApiUnavailable:
        await interaction.followup.send("Quantimental is unreachable right now.")
        return
    await interaction.followup.send(embed=render.filings(feed))


@bot.tree.command(description="What the market as a whole did today.")
async def market(interaction: discord.Interaction) -> None:
    await interaction.response.defer()
    try:
        payload = await bot.api.desk()
    except ApiUnavailable:
        await interaction.followup.send("Quantimental is unreachable right now.")
        return
    await interaction.followup.send(embed=render.desk(payload))


@bot.tree.command(description="Tickers people asked for that are not covered. Bot owner only.")
async def misses(interaction: discord.Interaction) -> None:
    """Data left on a volume nobody reads is data nobody acts on."""
    app = await bot.application_info()
    owner = app.team.owner_id if app.team else app.owner.id
    if interaction.user.id != owner:
        await interaction.response.send_message(
            "That one is for whoever runs the bot.", ephemeral=True
        )
        return

    ranked = bot.misses.ranked()
    if not ranked:
        await interaction.response.send_message(
            "Nothing asked for yet that is outside the universe.", ephemeral=True
        )
        return

    lines = [
        f"**{ticker}** — {row['count']}x across {len(row['guilds'])} server(s), "
        f"first {row['first']}"
        for ticker, row in ranked
    ]
    body = (
        f"{bot.misses.distinct()} tickers, {bot.misses.total()} requests.\n\n"
        + "\n".join(lines)
    )
    await interaction.response.send_message(body[:1900], ephemeral=True)


mine = app_commands.Group(name="my", description="Your own watchlist, private to you.")


@mine.command(name="add", description="Add a ticker to your own list.")
async def my_add(interaction: discord.Interaction, ticker: str) -> None:
    _, message = bot.personal.add(interaction.user.id, ticker)
    await interaction.response.send_message(message, ephemeral=True)


@mine.command(name="remove", description="Take a ticker off your own list.")
async def my_remove(interaction: discord.Interaction, ticker: str) -> None:
    _, message = bot.personal.remove(interaction.user.id, ticker)
    await interaction.response.send_message(message, ephemeral=True)


@mine.command(name="clear", description="Delete your list and everything stored for you.")
async def my_clear(interaction: discord.Interaction) -> None:
    had = bot.personal.clear(interaction.user.id)
    await interaction.response.send_message(
        "Your list is deleted. Nothing of yours is stored now."
        if had
        else "There was nothing stored for you.",
        ephemeral=True,
    )


@mine.command(name="today", description="What your own stocks did this session.")
async def my_today(interaction: discord.Interaction) -> None:
    watched = bot.personal.get(interaction.user.id)
    if not watched:
        await interaction.response.send_message(
            "Your list is empty. Add one with `/my add TICKER`.", ephemeral=True
        )
        return

    await interaction.response.defer(ephemeral=True)
    try:
        batch = await bot.api.explain(watched)
    except ApiUnavailable:
        await interaction.followup.send("Quantimental is unreachable right now.", ephemeral=True)
        return

    rows = batch.by_ticker()
    found = [rows[t] for t in watched if t in rows]
    missing = [t for t in watched if t not in rows]
    for ticker in missing:
        bot.misses.record(ticker, interaction.guild_id)

    embed = render.digest(
        found, as_of=batch.as_of, generated_at=batch.generated_at, missing=missing
    )
    embed.title = "Your watchlist"
    # Ephemeral throughout: a personal list is shown to the person who asked and
    # to nobody else, which is also what the privacy page promises.
    await interaction.followup.send(embed=embed, ephemeral=True)


bot.tree.add_command(mine)


watch = app_commands.Group(name="watch", description="The tickers this server follows.")


@watch.command(name="add", description="Follow a ticker.")
async def watch_add(interaction: discord.Interaction, ticker: str) -> None:
    if not _is_manager(interaction):
        await interaction.response.send_message(
            "Only members who can manage the server can change the watchlist.",
            ephemeral=True,
        )
        return
    _, message = bot.lists.add(interaction.guild_id, ticker)
    await interaction.response.send_message(message)


@watch.command(name="remove", description="Stop following a ticker.")
async def watch_remove(interaction: discord.Interaction, ticker: str) -> None:
    if not _is_manager(interaction):
        await interaction.response.send_message(
            "Only members who can manage the server can change the watchlist.",
            ephemeral=True,
        )
        return
    _, message = bot.lists.remove(interaction.guild_id, ticker)
    await interaction.response.send_message(message)


@watch.command(name="list", description="Show what this server follows.")
async def watch_list(interaction: discord.Interaction) -> None:
    tickers = bot.lists.get(interaction.guild_id)
    if not tickers:
        await interaction.response.send_message(
            "Nothing yet. Add one with `/watch add TICKER`."
        )
        return
    await interaction.response.send_message(
        f"Watching {len(tickers)}/{MAX_PER_GUILD}: " + ", ".join(tickers)
    )


@watch.command(name="here", description="Post the daily digest in this channel.")
async def watch_here(interaction: discord.Interaction) -> None:
    if not _is_manager(interaction):
        await interaction.response.send_message(
            "Only members who can manage the server can set the channel.",
            ephemeral=True,
        )
        return
    bot.lists.set_channel(interaction.guild_id, interaction.channel_id)
    await interaction.response.send_message(
        "The daily digest will be posted here, once per session after the close."
    )


bot.tree.add_command(watch)


def _is_manager(interaction: discord.Interaction) -> bool:
    """Changing what a whole server sees is a moderator action."""
    perms = getattr(interaction.user, "guild_permissions", None)
    return bool(perms and (perms.manage_guild or perms.administrator))


def run() -> int:
    if not TOKEN:
        logger.error("DISCORD_BOT_TOKEN is not set.")
        return 1
    bot.run(TOKEN, log_handler=None)
    return 0


if __name__ == "__main__":
    sys.exit(run())
