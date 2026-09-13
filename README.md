# Quantimental

**Why stocks moved today, described rather than predicted.**

<https://www.thequantimental.com>

Quantimental reads price action, news volume and SEC filings, and says what
happened in one sentence a reader can check against the chart. It does not
rate stocks, score them, or tell you what to do — for a measured reason, below.

```
Oracle Corporation is down 1.7% today, and down 1.1% over the past two weeks.

The market rose 0.5% today and Information Technology rose 1.9%
 — so Oracle did not follow its sector.
It filed an 8-K with the SEC reporting quarterly results after the previous close.
New stories about it appear roughly 41 times a day.
```

---

## Why there are no buy and sell ratings

There used to be. Five levels, a confidence figure, the lot.

Then they were backtested, walk-forward, over five years and **3,792
observations**:

| | |
| --- | --- |
| Directional accuracy | **48.5%** — worse than a coin flip |
| `strong_buy` | **−0.93pp** against baseline — statistically significant |
| `strong_sell` | **+1.70pp** against baseline — statistically significant |

The only two significant results pointed the **wrong way**. So the ratings were
deleted rather than tuned, and the test that killed them is published at
[/method](https://www.thequantimental.com/method) instead of buried.
`backend/scripts/backtest.py` reproduces it.

What survived is description: what moved, how unusual that was for this
particular stock, whether its sector moved too, and what the company told the
SEC that day.

---

## Quick start

You need **Python 3.11+** and **Node 20+**. Nothing else — no database, no
API keys, no native libraries.

**Terminal 1 — backend**

```bash
cd backend
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
PYTHONPATH=$(pwd) uvicorn app.main:app --reload --port 8000
```

**Terminal 2 — frontend**

```bash
cd frontend
npm install
npm run dev
```

Open <http://localhost:3000>. API docs are at <http://localhost:8000/docs>.

---

## What's in the box

| Path | What it is |
| --- | --- |
| `backend/` | FastAPI service: market data, indicators, description, attribution |
| `frontend/` | Next.js app: the dashboard, 503 stock pages, 11 sector pages |
| `.github/workflows/` | Scheduled scans that publish static JSON the site reads |
| `docker-compose.yml` | Optional Postgres and Kafka for the archive and batch pipeline |

### How a sentence gets built

**Describe** (`backend/app/engines/describe.py`) — *"What happened?"*
Today's move and the fortnight behind it, with "unusual" judged against this
stock's own typical day rather than a fixed percentage. A mega-cap moving 3%
is news; a small-cap moving 3% is Tuesday.

**Attribution** (`backend/app/engines/attribution.py`) — *"Was it this company?"*
Medians, not a factor model. Both the market's move and the sector's are
printed so the reader can do the subtraction. Measured across two years:
**70.9%** of moves track the market, **20.5%** are company-specific, **5.9%**
go against their own sector.

**Attention** (`backend/app/services/scan/attention_archive.py`) — *"Is anyone watching?"*
A daily record of how much news coverage each company gets. Nobody sells
historical news volume, so this exists only because it has been written down
since day one — and the baseline needs 20 trading days before it will claim
anything is unusual.

**Filings** (`backend/app/services/ingestion/filings/`) — *"What did they say?"*
SEC 8-K item codes, which are structured data, so naming a catalyst needs no
language model and cannot invent anything. A filing on the same day is
adjacency, never cause, and the copy never joins the two in one sentence.

---

## Design rules

These are the constraints the code is written to hold. They are worth knowing
before changing anything.

**1. Nothing is invented.** If a stock has no news coverage, the app says so
and describes it on price action alone. It never substitutes a neutral
placeholder and presents it as a measurement. Missing readings are `null`,
never `0`.

**2. Identical inputs give identical outputs.** No randomness anywhere in the
path from market data to sentence.

**3. It describes, it does not forecast.** A test bans forecast verbs across
the generated copy. It has caught two real leaks, so it stays.

**4. No bare jargon on screen.** Terms appear only beside a plain-English
definition, worded once in the backend so two surfaces cannot contradict
each other.

**5. Missing infrastructure degrades, it does not break.** No database, no API
keys, no Kafka: the API still starts and still serves. `/health` reports which
subsystems are live — and what each source *actually did*, not merely whether
a key is set.

**6. No native dependencies.** Indicators are implemented in
`backend/app/engines/indicators.py` with NumPy and pandas rather than TA-Lib,
which needs a C library installed out-of-band. They are verified against
TA-Lib's output in the test suite.

---

## Optional features

Each of these is off until you configure it.

<details>
<summary><strong>Live sentiment</strong> (needs API keys)</summary>

Add any of `MARKETAUX_API_KEY`, `TWITTER_API_KEY`, or `GROQ_API_KEY` to
`backend/.env`. Reddit works with no credentials at all over its RSS endpoints.
Sources you do not configure are skipped, and the response says which ones it
used.
</details>

<details>
<summary><strong>SEC filings</strong> (needs a contact address, not a key)</summary>

Set `SEC_CONTACT_EMAIL`. EDGAR is free and public domain, but it asks for a
contact in the User-Agent and throttles traffic it cannot trace.
</details>

<details>
<summary><strong>Error reporting</strong></summary>

Set `SENTRY_DSN`. Every event is scrubbed through `app/core/redaction.py`
before it leaves the process. Leave it blank and the SDK never starts.
</details>

<details>
<summary><strong>News archive and caching</strong> (needs Postgres)</summary>

```bash
docker compose up -d
cd backend
cp env.example .env          # then uncomment DATABASE_URL
PYTHONPATH=$(pwd) alembic upgrade head
```
</details>

<details>
<summary><strong>Transformer sentiment models</strong> (~800MB)</summary>

```bash
pip install -r backend/requirements-ml.txt
```

Adds FinBERT for news and Twitter RoBERTa for social posts. Without them,
sentiment falls back to VADER and the Groq-hosted LLM.
</details>

---

## API

| Method | Endpoint | What it does |
| --- | --- | --- |
| `GET` | `/api/v1/explain/{ticker}` | One stock, described. The embeddable one. |
| `GET` | `/api/v1/explain?tickers=` | The same for a watchlist, up to 100. |
| `GET` | `/api/v1/signals/search?q=` | Find tickers by symbol or company name. |
| `POST` | `/api/v1/signals/analyze` | Deep analysis of one stock, including sentiment. Slow. |
| `GET` | `/api/v1/market/signal-desk` | Rates, credit, FX, commodities and volatility. |
| `GET` | `/health` | Status, and what each subsystem actually did. |

`/api/v1/explain` is the one meant to be depended on by other people's code:
narrow on purpose, no field whose meaning could drift between releases, and a
`disclosure` string carried on every response so the caveat travels with the
text wherever it is rendered.

```bash
curl https://api.thequantimental.com/api/v1/explain/NVDA
```

Requests are rate limited by work rather than by count — a batch costs what it
reads.

---

## Tests

```bash
cd backend && PYTHONPATH=$(pwd) python -m pytest     # 400 tests
cd frontend && npm run check                         # types + lint
```

The load-bearing ones are the indicator tests, which verify the pure-Python
implementations that replaced a C library, and the copy guards, which assert
that nothing generated forecasts or claims causation.

---

## Deploying

**Backend** — Railway, Render, Fly, or any container host. `backend/railway.json`
is set up for Railway. Set `CORS_ORIGINS` to your frontend's origin.

**Frontend** — Vercel or any Next.js host. Set `NEXT_PUBLIC_API_URL` to your
deployed backend and `NEXT_PUBLIC_SITE_URL` to your own origin.

Scheduled scans run in GitHub Actions and commit static JSON the frontend
fetches directly, so opening a page never waits on a 503-ticker download.

---

## This is not financial advice

Quantimental describes public data. It does not predict the future, it does not
know your circumstances, and it can be wrong. Do your own research.
