# ML Sentiment Models - Kafka Pipeline Integration

## Overview

The ML sentiment models (FinBERT, Twitter RoBERTa, Groq Llama 3) have been integrated into the Kafka pipeline. The `classifier_worker.py` now uses these models based on the `source_type` of incoming events.

## Changes Made

### 1. Updated `classifier_worker.py`

The classifier worker now:
- Detects `source_type` from Kafka events
- Maps source types to ML models:
  - `"news"` → FinBERT (`analyze(text, source_type="news")`)
  - `"reddit"` → Twitter RoBERTa (`analyze(text, source_type="social")`)
  - `"twitter"` → Twitter RoBERTa (`analyze(text, source_type="social")`)
  - Unknown sources → VADER fallback (`predict(text)`)

### 2. Source Type Mapping

| Event Source Type | ML Model Used | Model Type |
|------------------|---------------|------------|
| `news` | FinBERT | Local Transformer |
| `reddit` | Twitter RoBERTa | Local Transformer |
| `twitter` | Twitter RoBERTa | Local Transformer |
| Unknown | VADER | Lexicon-based |

### 3. Output Format

The enriched events now include:
```json
{
  "sentiment": {
    "score": 0.85,
    "label": "positive",
    "confidence": 0.85,
    "model_used": "news"  // or "social", "vader"
  }
}
```

## Testing

### Unit Tests
✅ All unit tests pass (16/16)
```bash
pytest tests/unit/services/enrichment/test_sentiment_model.py -v
```

### Manual Model Tests
✅ ML models work correctly
```bash
python3 scripts/test_ml_sentiment.py
```

### Kafka Pipeline Integration Test
To test the full pipeline:

1. **Start Kafka** (if not running):
```bash
docker-compose up -d kafka zookeeper
```

2. **Test with real data** (recommended):
```bash
export PYTHONPATH=$PYTHONPATH:$(pwd)
python3 scripts/test_real_data_ml_pipeline.py --ticker AAPL --limit 10
```

3. **Or test with real pipeline** (manual):
   - Terminal 1: Start classifier worker
   ```bash
   export PYTHONPATH=$PYTHONPATH:$(pwd)
   python3 -m app.services.enrichment.sentiment.classifier_worker
   ```
   
   - Terminal 2: Produce test events
   ```bash
   export PYTHONPATH=$PYTHONPATH:$(pwd)
   python3 -m app.services.ingestion.sentiment.producer
   ```

## Verification

Check logs for model usage:
```
Processed event for AAPL (news): positive (0.850) [model: news]
Processed event for TSLA (reddit): positive (0.820) [model: social]
Processed event for NVDA (twitter): negative (-0.810) [model: social]
```

## Backwards Compatibility

- VADER `predict()` method still available for backwards compatibility
- Unknown source types automatically fall back to VADER
- Output format remains compatible with existing aggregator worker

## Next Steps

1. ✅ ML models integrated into pipeline
2. ⏳ Monitor performance and accuracy
3. ⏳ Consider using "discussion" model for longer Reddit posts
4. ⏳ Add metrics/telemetry for model usage
