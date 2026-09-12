# Batch Orchestration System

Automated 6-hourly ingestion and analysis pipeline for Quantimental.

## Overview

The orchestration system runs comprehensive market analysis every 6 hours to keep data fresh while preserving API rate limits:

- **6 AM (pre-market)**: Full refresh before market opens
- **12 PM (intraday)**: Midday update during trading hours
- **6 PM (post-market)**: Post-close comprehensive analysis
- **12 AM (midnight)**: End-of-day refresh

## Pipeline Stages

```
┌─────────────┐    ┌──────────────┐    ┌──────────────┐    ┌──────────────┐    ┌──────────────┐
│   Ingest    │ -> │    Quant     │ -> │    Psych     │ -> │    Hybrid    │ -> │   Persist    │
│   Raw Data  │    │  Technical   │    │  Sentiment   │    │   Scoring    │    │  & Refresh   │
└─────────────┘    └──────────────┘    └──────────────┘    └──────────────┘    └──────────────┘
```

### Stage 1: Ingest
Fetches raw data from:
- Yahoo Finance (prices, volume, historical data)
- Reddit (r/stocks, r/investing, r/wallstreetbets)
- News (MarketAux API)
- Twitter (financial Twitter)

### Stage 2: Quant (Quantitative Analysis)
Calculates technical indicators (see `app/engines/indicators.py`):
- RSI, MACD, Stochastic
- Bollinger Bands
- ADX (trend strength)
- Moving averages (SMA 20/50)

### Stage 3: Psych (Psychometric Analysis)
Analyzes sentiment using ML models:
- **FinBERT** for news articles
- **Twitter RoBERTa** for social media
- **Llama 3 via Groq** for Reddit discussions

### Stage 4: Hybrid Scoring
Combines signals:
- 45% Technical Rating
- 55% Sentiment Rating
- Generates buy/sell/hold recommendations

### Stage 5: Persist & Refresh
- Saves results to PostgreSQL
- Idempotent: Updates existing records for same day
- Refreshes public feed dataset

## Features

### ✅ Idempotency
- Reruns don't create duplicate records
- Updates existing signals for the same day
- Safe to run multiple times

### 📊 Structured Logging
- Start/success/failure for each stage
- Processing durations
- Success/failure counts per ticker

### 🚨 Error Handling
- Graceful degradation (individual ticker failures don't stop batch)
- Detailed error logging
- Fallback to database sentiment if live fetch fails

### ⚡ Performance
- Parallel processing of tickers
- Async/await throughout
- Typically completes in <60s for 10 tickers

## Usage

### Running the Scheduler

#### Option 1: Direct Python
```bash
cd quantimental-backend
python -m app.services.orchestration.batch_scheduler
```

#### Option 2: Docker Compose
```bash
docker-compose -f docker-compose.scheduler.yml up -d
```

#### Option 3: Systemd (Production)
```bash
# Install service
sudo cp deploy/quantimental-scheduler.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable quantimental-scheduler
sudo systemctl start quantimental-scheduler

# Check status
sudo systemctl status quantimental-scheduler

# View logs
sudo journalctl -u quantimental-scheduler -f
```

### Manual Batch Execution

Use the CLI tool for manual runs:

```bash
# Run batch now
python scripts/batch_cli.py run

# Run for specific tickers
python scripts/batch_cli.py run --tickers AAPL TSLA NVDA

# Test with single ticker
python scripts/batch_cli.py test --ticker AAPL

# Check last run status
python scripts/batch_cli.py status

# View schedule
python scripts/batch_cli.py schedule
```

## Configuration

### Default Tickers
Edit `SchedulerConfig.DEFAULT_TICKERS` in `batch_scheduler.py`:

```python
DEFAULT_TICKERS = [
    "AAPL", "MSFT", "GOOGL", "AMZN", "NVDA",
    "TSLA", "META", "NFLX", "AMD", "DIS"
]
```

### Schedule Times
Edit `SchedulerConfig.SCHEDULE_TIMES` to customize:

```python
SCHEDULE_TIMES = [
    {"hour": 6, "minute": 0, "name": "pre-market"},
    {"hour": 12, "minute": 0, "name": "intraday"},
    {"hour": 18, "minute": 0, "name": "post-market"},
    {"hour": 0, "minute": 0, "name": "midnight"},
]
```

## Monitoring

### Check Batch Status
```bash
python scripts/batch_cli.py status
```

Output:
```
Last Update: 2025-11-24 06:00:15
Total Signals: 10
Time Since Last Update: 0.2 hours

Signal Distribution:
  bullish: 6
  neutral: 3
  bearish: 1
```

### View Logs

#### Docker
```bash
docker logs -f quantimental-scheduler
```

#### Systemd
```bash
sudo journalctl -u quantimental-scheduler -f
```

#### Log Files (if configured)
```bash
tail -f /var/log/quantimental/scheduler.log
```

## Database Schema

### HybridSignal Table
```sql
CREATE TABLE hybrid_signals (
    id SERIAL PRIMARY KEY,
    ticker VARCHAR(10) NOT NULL,
    company_name VARCHAR(255),
    technical_rating INTEGER,
    sentiment_rating INTEGER,
    hybrid_score INTEGER,
    signal VARCHAR(20),
    price DECIMAL(10, 2),
    mentions INTEGER,
    mention_velocity VARCHAR(20),
    created_at TIMESTAMP DEFAULT NOW(),
    updated_at TIMESTAMP DEFAULT NOW()
);

CREATE INDEX idx_hybrid_signals_ticker ON hybrid_signals(ticker);
CREATE INDEX idx_hybrid_signals_created_at ON hybrid_signals(created_at);
```

## API Rate Limits

The 6-hour schedule is designed to stay within API limits:

| Service | Free Tier | Our Usage (per run) | Daily Total | Limit |
|---------|-----------|---------------------|-------------|-------|
| MarketAux | 100/day | 10 | 40 (4 runs) | ✅ |
| Reddit | Unlimited | 10-50 posts | 40-200 | ✅ |
| Twitter | Variable | 10-25 tweets | 40-100 | ✅ |
| Yahoo Finance | Unlimited | 10 tickers | 40 | ✅ |
| Groq (Llama 3) | 30 req/min | ~20 | ~80 | ✅ |

## Alerting (TODO)

Planned alerting mechanisms:

- [ ] Email alerts on batch failures
- [ ] Slack notifications for missing data
- [ ] PagerDuty integration for critical errors
- [ ] Prometheus metrics export

## Performance Benchmarks

Typical performance for 10 tickers:

- Stage 1 (Ingest): ~15s
- Stage 2 (Quant): ~5s
- Stage 3 (Psych): ~25s (ML model inference)
- Stage 4 (Hybrid): ~2s
- Stage 5 (Persist): ~3s
- **Total**: ~50s

## Troubleshooting

### Batch Not Running

1. Check if scheduler is running:
   ```bash
   # Docker
   docker ps | grep scheduler

   # Systemd
   systemctl status quantimental-scheduler
   ```

2. Check logs for errors:
   ```bash
   python scripts/batch_cli.py status
   ```

### Missing Sentiment Data

If sentiment scores are 50 (neutral):
- Check API keys in `.env`
- Verify Reddit/Twitter/MarketAux credentials
- Check rate limits

### Database Connection Errors

Verify database is running and credentials are correct:
```bash
# Test connection
psql -h localhost -U quantimental -d quantimental
```

## Development

### Running Tests
```bash
# Test single ticker
python scripts/batch_cli.py test --ticker AAPL

# Test with verbose logging
python scripts/batch_cli.py test --ticker AAPL -v
```

### Adding New Stages

1. Add method to `BatchOrchestrator` class
2. Call from `run_full_pipeline()`
3. Add to summary output
4. Update this README

## License

Proprietary - Quantimental
