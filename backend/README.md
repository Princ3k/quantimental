# Quantimental Backend

FastAPI service that turns market data into explained signals.
See the [repository README](../README.md) for the project overview.

## Run it

```bash
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
PYTHONPATH=$(pwd) uvicorn app.main:app --reload --port 8000
```

No database or API keys needed. Docs at <http://localhost:8000/docs>.

## Layout

```
app/
├── main.py                  FastAPI app, CORS, health
├── core/config.py           All settings, read from the environment once
├── engines/
│   ├── indicators.py        Pure NumPy/pandas technical indicators
│   ├── quant.py             Indicators → chart score + plain-English notes
│   ├── psych.py             Text → sentiment
│   └── hybrid.py            Both → verdict, confidence, explanation
├── services/
│   ├── data/                Market data and ticker search, with caching
│   ├── signals/             LiveSignalService — the one place a signal is built
│   ├── ingestion/           Fetching from Reddit, news and Twitter
│   ├── enrichment/          Sentiment classification workers
│   └── orchestration/       Batch scheduler
├── api/routes/              HTTP layer — thin wrappers over the services
└── db/                      SQLAlchemy models and optional session management
```

## How a signal is built

`LiveSignalService.generate()` is the only path that produces one, so the
dashboard and the single-stock view can never disagree.

1. **Fetch** a year of daily bars from Yahoo Finance (cached 60s per ticker).
   A year specifically: SMA-200 needs 200 bars, and the Wilder-smoothed
   indicators need ~125 before their warm-up bias decays to nothing.
2. **Clean** — rows with no close are dropped. Yahoo emits a row for the
   current session as soon as it opens, with volume but a `NaN` close; left in,
   that NaN propagates through every indicator.
3. **Score** the chart via `QuantEngine` → indicators, a 0-100 rating, notes.
4. **Score** the mood via the sentiment pipeline — but only at `full` depth,
   and only if it returns actual mentions. See [Sentiment sources](#sentiment-sources).
5. **Combine** via `HybridEngine`. With no sentiment the weighting falls back
   to 100% technical rather than blending against a fabricated neutral 50,
   which would drag every score toward the middle.
6. **Assemble** the JSON contract the frontend consumes.

### Sentiment sources

Sentiment works with **no API keys**. Yahoo Finance headlines are the default
source and cover every market `yfinance` does, including non-US listings like
`RACE.MI` and `SHOP.TO`. Keys add sources; they are never required.

| Source | Needs a key | Notes |
| --- | --- | --- |
| Yahoo Finance | no | Default. ~10 stories/ticker, cached 5 min. |
| Reddit | recommended | See below. |
| MarketAux | yes | Adds publisher-scored sentiment. Free tier: 100 req/day. |
| Twitter/X | yes | Two resellers supported; set `TWITTER_API_PROVIDER`. See below. |

Two decisions here are worth knowing about, because both were arrived at the
expensive way.

**Reddit needs credentials to be dependable.** Reddit's `/search.json` endpoint
now returns HTTP 403 to unauthenticated clients regardless of User-Agent. The
`.rss` feeds still work and are what we use without credentials, but anonymous
access is limited to roughly *one request per minute* — measured by probing it,
not guessed. Under any real traffic most calls are refused, so the source backs
off for five minutes after a 429 rather than digging the hole deeper. Setting
`REDDIT_CLIENT_ID` and `REDDIT_CLIENT_SECRET` (a free "script" app at
<https://www.reddit.com/prefs/apps>) switches to the OAuth API: ~100 requests a
minute, and post scores, which RSS omits.

**Twitter needs its provider named.** Two companies resell Twitter/X search —
twitterapi.io and ScrapeBadger — and their keys are not interchangeable. Each
rejects the other's with a bare HTTP 401, and nothing in that response suggests
the provider is the problem. This repo previously hard-coded ScrapeBadger while
`env.example` told you to sign up at twitterapi.io, which guaranteed a 401 for
anyone who followed the documentation. Set `TWITTER_API_PROVIDER` to wherever
the key actually came from; the 401 now names the host it was sent to.

**A source that fails says so.** Every fetcher used to swallow its errors into
an empty list, so "MarketAux rejected our API key" and "this company had a quiet
week" produced byte-identical output — the app told users a stock had no
coverage when the truth was that our own credentials were being refused. Each
source now reports `ok` / `empty` / `disabled` / `error` with a detail string,
surfaced on `sentiment_analysis.sources`:

```json
"sources": {
  "yahoo_finance": { "status": "ok",       "count": 10, "detail": null },
  "reddit":        { "status": "error",    "count": 0,  "detail": "HTTP 429 — rate limited by Reddit; ..." },
  "marketaux":     { "status": "disabled", "count": 0,  "detail": "MARKETAUX_API_KEY is not set" }
}
```

`disabled` is a choice, not a fault — it means no key was configured. Only
`error` indicates something is wrong, and the UI distinguishes the two rather
than blaming the stock.

### Two depths

| Depth | Sources | Speed | Used by |
| --- | --- | --- | --- |
| `fast` | Yahoo Finance | ~150ms/ticker, parallel | Dashboard |
| `full` | + Reddit, MarketAux, Twitter | seconds | Single-stock analysis |

## Indicators

`app/engines/indicators.py` implements RSI, SMA, EMA, MACD, Bollinger Bands,
Stochastic, ATR and ADX directly in NumPy and pandas.

This replaced TA-Lib, which is a C library needing `brew install ta-lib` (or an
apt package, or a custom Nixpacks layer) before `pip install TA-Lib` will even
build — the single biggest obstacle to setting the project up or deploying it.

The implementations follow Wilder's original definitions and match TA-Lib to
about 1e-6 on the bars that are actually read, given the year of history the
service fetches. `tests/unit/test_indicators.py` covers them.

## Tests

```bash
PYTHONPATH=$(pwd) python -m pytest
```

114 tests, about 1.5 seconds, no network access. Market data is stubbed in the
API tests so CI is deterministic.

## Configuration

Every setting is optional — see `env.example`. Missing credentials disable the
matching source rather than failing a request; `/health` reports what is live.
