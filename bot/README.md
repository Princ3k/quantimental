# Discord bot

A tap on `/api/v1/explain`, not a second product. It holds no market data,
computes no figures and writes no descriptions — every sentence it posts came
from the API, which is the surface whose wording is covered by the no-forecast
tests. Anything this bot phrased itself would not be.

## Commands

| | |
|---|---|
| `/help` | What the bot does and what you can ask it. Ephemeral. |
| `/stock TICKER` | What one stock did this session. |
| `/unusual` | Stocks that moved far beyond their own normal today. |
| `/filings` | The 8-Ks companies filed this session. |
| `/market` | What the market as a whole did today. |
| `/misses` | Tickers people asked for that are not covered. Bot owner only. |
| `/stats` | How the bot is being used. Bot owner only. |

One post a day, after the close: unusual moves, 8-K filings, then the server's
watchlist. Each section appears only when it has something, which is what makes
`/watch here` alone enough — unusual moves and filings are about the market,
not about anyone's list. When no section has anything, nothing is posted: a
daily "nothing happened" is how a channel learns to ignore a bot.
| `/watch add TICKER` | Follow a ticker. Manage-server permission. |
| `/watch remove TICKER` | Stop following one. |
| `/watch list` | What this server follows. |
| `/watch here` | Post the daily digest in this channel. |
| `/watch off` | Stop the daily post. The watchlist is kept. |
| `/my add` · `/my remove` · `/my list` · `/my today` · `/my clear` | A watchlist of your own, private to you. |

`/unusual` reads `/api/v1/market/unusual` and `/market` reads
`/api/v1/market/desk` — both cached published files. Note that `/market/desk`
is not `/market/signal-desk`: the latter recomputes from Yahoo and an LLM on
every call, which is not something to put behind a command anyone can spam.

Slash commands, not `@mentions`. That avoids the message-content intent, which
needs Discord's approval past 75 servers and would mean reading every message
in every channel to find the few addressed to us.

## The digest fires by session, not by clock

The sentences are not computed when the bot asks for them. They are baked into
`snapshot.json` by the scan that runs in CI, and the API serves a cached copy.
A bot posting at a fixed time would sometimes repeat the previous session's
wording with no way to tell from its own side.

So: **once per guild per `as_of`**, the first time a scan that *itself ran
after the close* becomes visible. The session being over is not enough — the
hourly scans run at :13 past and the market closes at 20:00 UTC, so at the bell
the newest published scan is 19:13's and its prices are intraday. The earliest
digest therefore uses the 20:13 run, which is final. A missed slot self-heals — the next poll still owes it — and a
session that publishes twice cannot produce two posts. Past 20 hours after the
close the session is abandoned, because posting a day-old digest as today's is
worse than posting nothing. See `schedule.py`.

## Staleness is surfaced, not hidden

`render.stale_notice()` warns in the footer when a scan is overdue. This is
deliberate: the API keeps serving its last good snapshot when a refresh fails
and logs that at warning level, so nothing raises and nothing pages. A consumer
that does not check `generated_at` cannot tell an hourly scan from a broken one.

**Overdue is measured against the schedule, not the clock.** The first version
warned past two wall-clock hours, which fired every morning and all weekend —
scans run weekdays 14:13 to 21:43 UTC, so overnight the last session's close is
the current answer and nothing is late. A warning that is on most of the time
is one nobody reads, and then it is not there on the day a scan has died.

Inside the window the limit is 2.5 hours, roughly two missed hourly slots.
Outside it, 72 hours, which spans a long weekend and still catches a dead scan.

## Cost

One call serves every guild. The scheduled post deduplicates tickers across all
of them and asks once, so the rate-limit cost is the number of distinct
companies anyone follows rather than servers times tickers. `/explain` costs
`tickers x 0.2` units and is served from cache, so a daily post for fifty names
is about ten units. Nothing here calls `/signals/analyze`, which costs 25 a
request and hits Reddit, MarketAux and an LLM.

## Run it

```bash
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
DISCORD_BOT_TOKEN=... WATCHLIST_PATH=./state.json python main.py
```

| Variable | |
|---|---|
| `DISCORD_BOT_TOKEN` | From the Discord developer portal. Required. |
| `WATCHLIST_PATH` | State file. Leave unset on Railway — the default follows the attached volume. |
| `QUANTIMENTAL_API` | Defaults to `https://api.thequantimental.com`. |
| `QUANTIMENTAL_SITE` | Where embeds link to. Defaults to `https://www.thequantimental.com`. |

State is one JSON file written to a temporary file and renamed, so a crash
mid-write leaves the previous file intact.

It needs a Railway **volume**, and the path follows that volume automatically:
Railway sets `RAILWAY_VOLUME_MOUNT_PATH` when one is attached, and the default
state path is derived from it. Do not set `WATCHLIST_PATH` on Railway — hard-
coding a path that does not match the mount is the one way to get this wrong,
and it fails silently. The bot writes happily to container storage, answers
`/watch list` correctly, and loses everything on the next deploy.

`check_durability()` runs at startup and says which case you are in:

```
INFO  State at /app/data/watchlists.json is on the volume mounted at /app/data.
ERROR State path /data/watchlists.json is not inside the mounted volume /app/data.
```

## Tests

```bash
python -m pytest        # 74 tests, no network
```

## Every embed links back

A ticker in a channel is a dead end otherwise. Titles link to the stock page,
tickers in lists are links, and the unusual threshold links to `/method` —
which is where the claim that any of this is descriptive rather than predictive
is actually made good, and therefore the page a sceptic should land on.

URLs are lower-cased, matching what `generateStaticParams` prerenders. Upper
case resolves too, but misses the static route and is not the canonical URL.

## Discord's field limits

A field value over 1024 characters does not get truncated by Discord — the
whole embed is rejected, the post fails, and because a failed send is
deliberately not marked done it retries and fails every fifteen minutes until
the session is abandoned. Six real 8-K filings with EDGAR URLs came to 1221
characters on the first day, so `_fit()` drops whole lines and says how many it
left out. Whole lines only: a truncated markdown link renders as raw text.

## Measuring the universe gap

The covered universe is the S&P 500. The first ticker reached for in testing
was KAZR, which is not in it — and small caps are most of the conversation in a
stock server, so the refusal will be a common first interaction.

Whether to expand, and to what, is a real question, and `misses.py` answers it
the way the 8-K question was answered: by measuring first. Every refused ticker
is recorded — from `/stock` and from a watched ticker the digest could not
cover, which is the stronger signal, since someone wanted it tracked daily
rather than looked up once. `/misses` ranks them, breadth before volume: one
person hammering a ticker is a person, five servers asking once each is a gap.

**Not recorded:** who asked. No user ids, no usernames, no message content.
Servers are counted but not identified — a guild id is stored as an eight-
character digest, so "eleven servers asked for this" is answerable and "which
servers" is not. Most of these requests come from other people's communities,
and the ranked list is the entire point.

One thing to settle before acting on the list: `mkt` in the published snapshot
is the median of the *scanned universe*, so expanding it silently redefines
"the market" in every attribution sentence, Apple's included. Compute the
market median from a fixed benchmark basket first, then grow the universe.

## Personal watchlists, and the identity question

Asked for by the first server that installed the bot: members wanting their own
list rather than the admin-managed one the daily post uses.

Keeping a list per person means recognising that person between commands, which
is the one thing the rest of this bot avoids. So `personal.py` keys on a
SHA-256 of the Discord id, never the id — the file is ticker symbols against
digests and cannot be read as, or turned into, a list of who uses this. A full
digest rather than the 8 characters `misses.json` uses: that one only counts
servers, where a collision is harmless, and here a collision would hand someone
another person's watchlist.

That is pseudonymity, not anonymity, and `/privacy` says so in those words.
Discord ids are not secret, so someone who already holds yours can test for it.
The digest stops the file being a directory; it does not defeat somebody with a
specific person already in mind.

The boundary this draws is the useful part: **a digest cannot be reversed, so
this cannot message anyone.** Every `/my` reply is ephemeral and follows a
command the person just typed. Push delivery would need the real id, and that
is a separate decision with its own consent — not something to slide in behind
this one.

## Counting usage without following anyone

`usage.py` answers whether anyone is using this, what for, and which companies
they ask about — per day, as counts.

Counting distinct people needs a way to tell two commands apart, which is the
one thing the rest of this bot avoids. The digest is therefore made from **the
day and the id together**, so the same person produces a different value
tomorrow. That buys a real answer to "nine people used it on Tuesday" while
making "did any of them come back on Wednesday" unanswerable — not merely
undisclosed, but unreconstructable, because nothing links the two digests and
the id was never held.

So `/stats` reports **person-days, not people**. Returning visitors are counted
again rather than deduplicated, and the readout says so rather than quietly
overstating reach.

Retention would be more useful than reach. It is not worth a per-person history
to get it, and `/privacy` describes this arrangement before any of it is
collected.
