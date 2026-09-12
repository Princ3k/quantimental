# Complete Kafka Pipeline Flow

## Overview

The sentiment analysis pipeline processes data through multiple stages using Kafka topics and workers.

## Pipeline Architecture

```
┌─────────────┐
│   Producer  │ Fetches from APIs (Reddit, Twitter, MarketAux)
└──────┬──────┘ skip_full_text=True (fast mode)
       │
       ▼
┌─────────────────────┐
│ sentiment.raw_events│ Kafka Topic (metadata only)
└──────┬──────────────┘
       │
       ├──────────────────┬──────────────────┐
       │                  │                  │
       ▼                  ▼                  ▼
┌──────────────┐  ┌──────────────┐  ┌──────────────┐
│ News Fetcher │  │  Classifier  │  │  Aggregator  │
│   Worker     │  │    Worker    │  │    Worker    │
└──────┬───────┘  └──────┬───────┘  └──────┬───────┘
       │                  │                  │
       ▼                  ▼                  ▼
┌──────────────┐  ┌─────────────────────┐  ┌──────────────┐
│ news.enriched│  │sentiment.scored_events│  │  Database    │
│  (with text) │  │   (with sentiment)   │  │  (Events +   │
└──────────────┘  └─────────────────────┘  │  Aggregates) │
                                            └──────────────┘
```

## Detailed Flow

### Step 1: Producer (`producer.py`)
- **Input**: Ticker symbols (e.g., "AAPL", "TSLA")
- **Action**: 
  - Fetches data from Reddit, Twitter, MarketAux APIs
  - Uses `skip_full_text=True` for speed (no content scraping)
  - Publishes events to `sentiment.raw_events`
- **Output**: Kafka events with metadata (title, description, url, but NO full_text)

### Step 2: News Fetcher Worker (`news_fetcher.py`)
- **Input**: `sentiment.raw_events` (news articles only)
- **Action**:
  - Fetches full article content from URLs
  - Stores content in `NewsArticle` table (database)
  - Publishes enriched events to `news.enriched` (with full_text)
- **Output**: 
  - Database: `NewsArticle.content` (full text stored)
  - Kafka: `news.enriched` topic (with full_text in payload)

### Step 3: Classifier Worker (`classifier_worker.py`)
- **Input**: `sentiment.raw_events` (all source types)
- **Action**:
  - For news articles: Checks database for `full_text` if missing from payload
  - Analyzes text with ML models:
    - News → FinBERT
    - Reddit/Twitter → Twitter RoBERTa
    - Unknown → VADER fallback
  - Publishes scored events to `sentiment.scored_events`
- **Output**: Kafka events with sentiment scores and labels

### Step 4: Aggregator Worker (`aggregator_worker.py`)
- **Input**: `sentiment.scored_events`
- **Action**:
  - Persists individual events to `SentimentEvent` table
  - Creates/updates aggregates in `SentimentAggregate` table (15-minute buckets)
- **Output**: Database records (events + aggregates)

## Data Flow Example

### News Article Flow:

1. **Producer**:
   ```json
   {
     "source_type": "news",
     "ticker": "AAPL",
     "payload": {
       "title": "Apple Reports Earnings",
       "description": "Apple Inc. announced...",
       "url": "https://example.com/article"
       // NO full_text
     }
   }
   ```

2. **News Fetcher**:
   - Fetches content from URL
   - Stores in DB: `NewsArticle.content = "Full article text..."`
   - Publishes to `news.enriched` with `full_text`

3. **Classifier**:
   - Receives event from `sentiment.raw_events` (no full_text)
   - Checks DB: Finds `NewsArticle.content`
   - Analyzes full text with FinBERT
   - Publishes scored event

4. **Aggregator**:
   - Persists to `SentimentEvent` table
   - Updates `SentimentAggregate` for 15-minute bucket

## Running the Pipeline

### Start Workers (in separate terminals):

```bash
# Terminal 1: News Fetcher Worker
export PYTHONPATH=$PYTHONPATH:$(pwd)
python3 -m app.services.enrichment.news_fetcher

# Terminal 2: Classifier Worker
export PYTHONPATH=$PYTHONPATH:$(pwd)
python3 -m app.services.enrichment.sentiment.classifier_worker

# Terminal 3: Aggregator Worker
export DATABASE_URL=postgresql://postgres:password@127.0.0.1:5433/quantimental
export PYTHONPATH=$PYTHONPATH:$(pwd)
python3 -m app.services.enrichment.sentiment.aggregator_worker
```

### Produce Data:

```bash
# Terminal 4: Producer
export PYTHONPATH=$PYTHONPATH:$(pwd)
python3 -m app.services.ingestion.sentiment.producer
```

### Test Complete Pipeline:

```bash
# Test with real data from APIs
export PYTHONPATH=$PYTHONPATH:$(pwd)
python3 scripts/test_real_data_ml_pipeline.py --ticker AAPL --limit 10
```

## Key Features

- **Fast Producer**: Skips content fetching for speed
- **Async Processing**: Workers process independently
- **Full Text Storage**: Content stored in database for ML analysis
- **ML Model Selection**: Automatic model selection based on source type
- **Database Persistence**: Events and aggregates stored for analysis

## Topics

- `sentiment.raw_events`: Raw events from producer (metadata only)
- `news.enriched`: News events with full text (from News Fetcher)
- `sentiment.scored_events`: Events with sentiment scores (from Classifier)

## Database Tables

- `news_articles`: Full article content storage
- `sentiment_events`: Individual sentiment events
- `sentiment_aggregates`: Time-bucketed sentiment aggregates (15-minute intervals)
