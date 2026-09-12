"""
API tests for the signal endpoints.

Market data is stubbed throughout: these tests assert the HTTP contract and
never touch Yahoo, so they run offline and deterministically in CI.
"""

from __future__ import annotations

import numpy as np
import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.services.data import market_data_service as mds_module
from app.services.signals import live_signal_service as live_module


def _fake_quote(ticker: str = "AAPL", price: float = 150.0) -> dict:
    """A complete, realistic quote built from a synthetic uptrend."""
    rng = np.random.default_rng(1)
    closes = np.cumsum(rng.normal(0.5, 0.6, 250)) + 100.0
    closes = closes / closes[-1] * price  # scale so the last close is `price`

    from app.engines.quant import quant_engine

    return {
        "ticker": ticker,
        "available": True,
        "price": float(closes[-1]),
        "previous_close": float(closes[-2]),
        "company": {"name": f"{ticker} Corp", "sector": "Technology"},
        "indicators": quant_engine.calculate_indicators(closes, closes + 1, closes - 1),
        "price_history": [round(float(c), 2) for c in closes[-30:]],
        "timestamp": "2026-01-01T00:00:00+00:00",
    }


def _unavailable_quote(ticker: str) -> dict:
    return {
        "ticker": ticker,
        "available": False,
        "reason": f"No market data available for {ticker}. Check the symbol is correct.",
        "price": None,
        "company": {"name": ticker},
        "indicators": {},
        "timestamp": "2026-01-01T00:00:00+00:00",
    }


@pytest.fixture
def client(monkeypatch) -> TestClient:
    """TestClient with market data stubbed; KNOWN symbols resolve, others don't."""

    def fake_get_quote(ticker: str) -> dict:
        if ticker.upper().startswith("BAD") or ticker.upper() == "NOSUCH":
            return _unavailable_quote(ticker.upper())
        return _fake_quote(ticker.upper())

    monkeypatch.setattr(mds_module.market_data_service, "get_quote", fake_get_quote)
    # The signal service holds its own reference to the singleton.
    monkeypatch.setattr(live_module.market_data_service, "get_quote", fake_get_quote)
    return TestClient(app)


class TestHealth:
    def test_health_reports_subsystems(self, client):
        response = client.get("/health")
        assert response.status_code == 200
        body = response.json()
        assert body["status"] == "healthy"
        assert "market_data" in body["subsystems"]

    def test_health_reports_each_sentiment_provider(self, client):
        """
        A single combined flag cannot answer "which credential is missing",
        which is the only question worth asking after a deploy.
        """
        sentiment = client.get("/health").json()["subsystems"]["sentiment"]

        for provider in ("groq", "marketaux", "reddit", "twitter"):
            assert provider in sentiment
            assert isinstance(sentiment[provider], bool)

    def test_health_never_leaks_a_credential(self, client):
        """Booleans and a model name only — never the key itself."""
        raw = client.get("/health").text
        for marker in ("gsk_", "sk-", "Bearer "):
            assert marker not in raw

    def test_root_points_at_docs(self, client):
        assert client.get("/").json()["docs"] == "/docs"

    def test_process_time_header_is_set(self, client):
        assert "X-Process-Time" in client.get("/health").headers


class TestAnalyze:
    def test_returns_a_complete_signal(self, client):
        response = client.post("/api/v1/signals/analyze", json={"ticker": "AAPL"})
        assert response.status_code == 200

        signal = response.json()["signal"]
        for field in (
            "ticker", "company_name", "price", "signal", "hybrid_score",
            "technical_rating", "recommendation", "technical_analysis",
            "sentiment_analysis", "metadata",
        ):
            assert field in signal, f"missing {field}"

    def test_lowercase_ticker_is_normalised(self, client):
        response = client.post("/api/v1/signals/analyze", json={"ticker": "aapl"})
        assert response.json()["signal"]["ticker"] == "AAPL"

    def test_unknown_symbol_is_404_not_500(self, client):
        response = client.post("/api/v1/signals/analyze", json={"ticker": "NOSUCH"})
        assert response.status_code == 404
        assert "NOSUCH" in response.json()["detail"]

    @pytest.mark.parametrize("bad", ["", "   ", "TOOLONGTICKER", "AA PL", "<script>", "1"])
    def test_malformed_tickers_are_rejected(self, client, bad):
        response = client.post("/api/v1/signals/analyze", json={"ticker": bad})
        assert response.status_code == 422

    def test_missing_body_is_rejected(self, client):
        assert client.post("/api/v1/signals/analyze", json={}).status_code == 422

    def test_recommendation_is_human_readable(self, client):
        recommendation = client.post(
            "/api/v1/signals/analyze", json={"ticker": "AAPL"}
        ).json()["signal"]["recommendation"]

        assert recommendation["label"][0].isupper()
        assert "_" not in recommendation["label"]
        assert len(recommendation["summary"]) > 30
        assert isinstance(recommendation["reasons"], list) and recommendation["reasons"]
        assert 0 <= recommendation["confidence"] <= 95


class TestBatch:
    def test_analyzes_several_tickers(self, client):
        response = client.post(
            "/api/v1/signals/batch", json={"tickers": ["AAPL", "MSFT", "NVDA"]}
        )
        assert response.status_code == 200
        body = response.json()
        assert body["total_processed"] == 3
        assert len(body["signals"]) == 3
        assert body["failed"] == []

    def test_unresolvable_tickers_are_reported_not_dropped(self, client):
        """
        A ticker that cannot be priced must come back with a reason. The old
        implementation silently substituted randomly generated mock data.
        """
        response = client.post("/api/v1/signals/batch", json={"tickers": ["AAPL", "BADONE"]})
        body = response.json()

        assert len(body["signals"]) == 1
        assert len(body["failed"]) == 1
        assert body["failed"][0]["ticker"] == "BADONE"
        assert body["failed"][0]["reason"]

    def test_duplicates_are_collapsed(self, client):
        response = client.post(
            "/api/v1/signals/batch", json={"tickers": ["AAPL", "aapl", "AAPL"]}
        )
        assert response.json()["total_processed"] == 1

    def test_empty_list_is_rejected(self, client):
        assert client.post("/api/v1/signals/batch", json={"tickers": []}).status_code == 422

    def test_oversized_batch_is_rejected(self, client):
        """A batch fans out to one upstream call per ticker, so it is capped."""
        tickers = [f"TCK{i}" for i in range(50)]
        assert client.post("/api/v1/signals/batch", json={"tickers": tickers}).status_code == 422

    def test_fast_depth_marks_sentiment_unavailable(self, client):
        signal = client.post(
            "/api/v1/signals/batch?depth=fast", json={"tickers": ["AAPL"]}
        ).json()["signals"][0]

        sentiment = signal["sentiment_analysis"]
        assert sentiment["available"] is False
        assert sentiment["rating"] is None  # never a fabricated 50
        assert sentiment["reason"]

    def test_invalid_depth_is_rejected(self, client):
        response = client.post(
            "/api/v1/signals/batch?depth=nonsense", json={"tickers": ["AAPL"]}
        )
        assert response.status_code == 422


class TestNoFabricatedData:
    """The product must never present invented numbers as analysis."""

    def test_response_is_stable_across_identical_requests(self, client):
        first = client.post("/api/v1/signals/batch", json={"tickers": ["AAPL"]}).json()
        second = client.post("/api/v1/signals/batch", json={"tickers": ["AAPL"]}).json()

        a, b = first["signals"][0], second["signals"][0]
        assert a["hybrid_score"] == b["hybrid_score"]
        assert a["recommendation"]["confidence"] == b["recommendation"]["confidence"]
        assert a["technical_rating"] == b["technical_rating"]

    def test_data_sources_are_declared_honestly(self, client):
        signal = client.post("/api/v1/signals/batch", json={"tickers": ["AAPL"]}).json()["signals"][0]
        sources = signal["metadata"]["data_sources"]

        assert "yahoo_finance" in sources
        assert "mock_data" not in sources
        # Fast depth does not query social sources, so it must not claim them.
        assert "reddit" not in sources

    def test_data_quality_is_exposed(self, client):
        metadata = client.post(
            "/api/v1/signals/batch", json={"tickers": ["AAPL"]}
        ).json()["signals"][0]["metadata"]
        assert metadata["data_quality"]["bars"] > 0


class TestSearch:
    def test_empty_query_returns_suggestions(self, client):
        results = client.get("/api/v1/signals/search").json()["results"]
        assert len(results) > 0
        assert all("ticker" in r and "name" in r for r in results)

    def test_respects_the_limit(self, client):
        results = client.get("/api/v1/signals/search?q=&limit=3").json()["results"]
        assert len(results) <= 3

    def test_rejects_an_out_of_range_limit(self, client):
        assert client.get("/api/v1/signals/search?q=a&limit=500").status_code == 422
