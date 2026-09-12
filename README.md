# Quantimental

**Market signals that make sense to humans.**

Quantimental reads a stock's price chart and the mood around it in news and
social posts, combines the two into a single verdict, and explains the
reasoning in ordinary English — for people who have never heard of an RSI.

```
Government bond yields climbed sharply while corporate debt prices fell,
signaling a shift toward caution. Energy stocks led the market, while
health care and materials lagged behind.

↑ RATES    Long-term rates climbing            +2.0σ
↓ CREDIT   High-yield credit under pressure    −1.7σ
↑ COMMOD   Crude pushing higher                +9.4%

Risk appetite  23 / 100 · Risk-off
```

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
| `backend/` | FastAPI service: market data, indicators, scoring, explanations |
| `frontend/` | Next.js app: the dashboard people actually look at |
| `docker-compose.yml` | Optional Postgres and Kafka for the archive and batch pipeline |

### The three engines

**Quant** (`backend/app/engines/quant.py`) — *"What does the math say?"*
Turns a year of daily bars into RSI, MACD, Bollinger Bands, Stochastic, ADX,
ATR and moving averages, then into a 0-100 chart score plus plain-English
observations.

**Psych** (`backend/app/engines/psych.py`) — *"What does the crowd feel?"*
Scores news articles, Reddit posts and tweets for sentiment, using VADER by
default and transformer models when they are installed.

**Hybrid** (`backend/app/engines/hybrid.py`) — *"So what should I do?"*
Weighs the two (45% chart, 55% mood by default) into one verdict, a derived
confidence figure, and the sentence a beginner actually reads.

---

## Design rules

These are the constraints the code is written to hold. They are worth knowing
before changing anything.

**1. Nothing is invented.** If a stock has no news coverage, the app says so
and scores it on price action alone. It never substitutes a neutral placeholder
and presents it as a measurement. `sentiment_rating` is `null`, not `50`.

**2. Identical inputs give identical outputs.** Confidence is derived from how
much the evidence agrees. There is no randomness anywhere in the scoring path.

**2b. The verdict is scored, and it did not do well.** A walk-forward backtest
over 1,888 readings across five years found no verdict that beat simply holding
by more than statistical noise — and a monotonic inversion, where the more
bullish calls performed slightly *worse*. So the product leads with the
explanation, which describes the present and is checkable, and presents the
verdict quietly. `backend/scripts/backtest.py` reproduces this.

**3. No bare jargon on screen.** Terms like RSI and ADX appear only next to a
plain-English definition. The wording for a given reading is defined once, in
the backend, and the frontend renders it — so a card can never contradict
itself.

**4. Missing infrastructure degrades, it does not break.** No database, no API
keys, no Kafka: the API still starts and still serves signals. `/health`
reports which subsystems are live.

**5. No native dependencies.** Indicators are implemented in
`backend/app/engines/indicators.py` with NumPy and pandas rather than calling
TA-Lib, which needs a C library installed out-of-band and made the project
impossible to set up on a clean machine. They are verified against TA-Lib's
output in the test suite.

---

## Optional features

Each of these is off until you configure it.

<details>
<summary><strong>News archive and Reddit caching</strong> (needs Postgres)</summary>

```bash
docker compose up -d
cd backend
cp env.example .env          # then uncomment DATABASE_URL
PYTHONPATH=$(pwd) alembic upgrade head
```
</details>

<details>
<summary><strong>Live sentiment</strong> (needs API keys)</summary>

Add any of `MARKETAUX_API_KEY`, `REDDIT_CLIENT_ID` / `REDDIT_CLIENT_SECRET`,
`TWITTER_API_KEY`, or `GROQ_API_KEY` to `backend/.env`. Sources you do not
configure are simply skipped, and the signal says which ones it used.

Then request the deep path: `POST /api/v1/signals/analyze`.
</details>

<details>
<summary><strong>Transformer sentiment models</strong> (~800MB)</summary>

```bash
pip install -r backend/requirements-ml.txt
```

Adds FinBERT for news and Twitter RoBERTa for social posts. Without them,
sentiment falls back to VADER and the Groq-hosted LLM.
</details>

<details>
<summary><strong>Batch pipeline</strong> (needs Kafka)</summary>

```bash
docker compose --profile pipeline up -d
```
</details>

---

## API

| Method | Endpoint | What it does |
| --- | --- | --- |
| `POST` | `/api/v1/signals/analyze` | Full analysis of one stock, including sentiment. Slow. |
| `POST` | `/api/v1/signals/batch?depth=fast` | Several stocks at once. `fast` skips sentiment. |
| `GET` | `/api/v1/signals/search?q=` | Find tickers by symbol or company name. |
| `GET` | `/api/v1/news/ticker/{ticker}` | Recent news with sentiment. Needs a database. |
| `GET` | `/health` | Status, plus which subsystems are live. |

A batch of 15 tickers at `fast` depth returns in roughly a second.

---

## Tests

```bash
cd backend && PYTHONPATH=$(pwd) python -m pytest     # 114 tests
cd frontend && npm run check                         # types + lint
```

The indicator tests are the load-bearing ones: they verify the pure-Python
implementations against closed-form expectations and known mathematical
properties, since they replaced a C library.

---

## Deploying

**Backend** — Railway, Render, Fly, or any container host. `backend/railway.json`
is set up for Railway. Set `CORS_ORIGINS` to your frontend's URL.

**Frontend** — Vercel or any Next.js host. Set `NEXT_PUBLIC_API_URL` to your
deployed backend.

---

## This is not financial advice

Quantimental summarises public data. It cannot predict the future, it does not
know your circumstances, and it can be wrong. Do your own research.
