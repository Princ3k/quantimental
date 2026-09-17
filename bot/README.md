# Discord bot

A tap on `/api/v1/explain`, not a second product. It holds no market data,
computes no figures and writes no descriptions — every sentence it posts came
from the API, which is the surface whose wording is covered by the no-forecast
tests. Anything this bot phrased itself would not be.

## Commands

| | |
|---|---|
| `/stock TICKER` | What one stock did this session. |
| `/watch add TICKER` | Follow a ticker. Manage-server permission. |
| `/watch remove TICKER` | Stop following one. |
| `/watch list` | What this server follows. |
| `/watch here` | Post the daily digest in this channel. |

Slash commands, not `@mentions`. That avoids the message-content intent, which
needs Discord's approval past 75 servers and would mean reading every message
in every channel to find the few addressed to us.

## The digest fires by session, not by clock

The sentences are not computed when the bot asks for them. They are baked into
`snapshot.json` by the scan that runs in CI, and the API serves a cached copy.
A bot posting at a fixed time would sometimes repeat the previous session's
wording with no way to tell from its own side.

So: **once per guild per `as_of`**, the first time a scan for a closed session
becomes visible. A missed slot self-heals — the next poll still owes it — and a
session that publishes twice cannot produce two posts. Past 20 hours after the
close the session is abandoned, because posting a day-old digest as today's is
worse than posting nothing. See `schedule.py`.

## Staleness is surfaced, not hidden

`render.stale_notice()` puts a warning in the footer when the scan behind a
response is more than two hours old. This is deliberate: the API keeps serving
its last good snapshot when a refresh fails, and logs that at warning level, so
nothing raises and nothing pages. A consumer that does not check `generated_at`
cannot tell an hourly scan from a broken one.

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
python -m pytest        # 45 tests, no network
```
