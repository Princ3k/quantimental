"""The published-file endpoints: cheap, cached, and no upstream fan-out."""

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.services.data import published_service

FEED = {
    "available": True,
    "as_of": "2026-09-17",
    "generated_at": "2026-09-17T20:13:00+00:00",
    "scanned": 503,
    "unusual_count": 1,
    "rising": 1,
    "falling": 0,
    "threshold": {"multiple": 2.0, "min_move_percent": 1.5},
    "movers": [{"ticker": "GNRC", "multiple": 3.9, "headline": "Generac is up 17.6% today."}],
    "biggest": [{"ticker": f"T{i}", "multiple": 1.1} for i in range(20)],
}


@pytest.fixture
def client(monkeypatch):
    monkeypatch.setattr(published_service, "get", lambda name, **kw: FEED)
    return TestClient(app)


class TestUnusual:
    def test_returns_the_movers_and_the_threshold(self, client):
        body = client.get("/api/v1/market/unusual").json()
        assert body["available"] is True
        assert body["movers"][0]["ticker"] == "GNRC"
        # Without the threshold a reader cannot judge what "unusual" meant.
        assert body["threshold"] == {"multiple": 2.0, "min_move_percent": 1.5}

    def test_the_limit_is_honoured(self, client):
        assert len(client.get("/api/v1/market/unusual?limit=5").json()["biggest"]) == 5

    def test_an_absurd_limit_is_rejected(self, client):
        assert client.get("/api/v1/market/unusual?limit=500").status_code == 422

    def test_the_disclosure_travels_with_it(self, client):
        assert "not a forecast" in client.get("/api/v1/market/unusual").json()["disclosure"]

    def test_biggest_is_kept_separate_from_movers(self, client):
        # biggest is not a list of unusual moves. Collapsing them would turn a
        # quiet day into a promoted list of ordinary ones.
        body = client.get("/api/v1/market/unusual").json()
        assert body["count"] == 1
        assert len(body["movers"]) == 1
        assert len(body["biggest"]) == 10

    def test_no_published_scan_says_so_rather_than_erroring(self, monkeypatch):
        monkeypatch.setattr(published_service, "get", lambda name, **kw: None)
        body = TestClient(app).get("/api/v1/market/unusual").json()
        assert body["available"] is False

    def test_it_never_returns_a_rating(self, client):
        body = client.get("/api/v1/market/unusual").json()
        for banned in ("rating", "verdict", "score", "recommendation", "signal"):
            assert banned not in body


class TestPublishedDesk:
    def test_serves_the_published_file(self, monkeypatch):
        monkeypatch.setattr(published_service, "get", lambda name, **kw: {
            "available": True, "as_of": "2026-09-17", "composite": {"score": 37},
        })
        body = TestClient(app).get("/api/v1/market/desk").json()
        assert body["composite"]["score"] == 37
        assert "not a forecast" in body["disclosure"]

    def test_unavailable_is_reported_not_raised(self, monkeypatch):
        monkeypatch.setattr(published_service, "get", lambda name, **kw: None)
        assert TestClient(app).get("/api/v1/market/desk").json()["available"] is False
