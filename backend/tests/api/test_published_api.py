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


class TestFilings:
    """8-Ks for the session: a fact about a document, not about a move."""

    ROWS = {
        "EXE": {"t": "EXE", "n": "Expand Energy", "s": "Energy", "c": 0.4,
                "f": {"i": ["1.01", "2.03"], "p": "a material agreement",
                      "a": "2026-09-17T12:00:00Z", "u": "https://sec.gov/x"}},
        "AIG": {"t": "AIG", "n": "AIG", "s": "Financials", "c": -8.0,
                "f": {"i": ["5.02"], "p": "a change among its directors",
                      "a": "2026-09-17T13:00:00Z", "u": None}},
        "AAPL": {"t": "AAPL", "n": "Apple Inc.", "s": "Information Technology", "c": 1.4},
    }

    @pytest.fixture
    def filed(self, monkeypatch):
        from app.services.data import snapshot_service

        class Fake:
            rows = self.ROWS
            as_of = "2026-09-17"
            generated_at = "2026-09-17T20:18:00+00:00"

        monkeypatch.setattr(snapshot_service, "get_snapshot", lambda *a, **k: Fake())
        return TestClient(app)

    def test_returns_only_rows_that_filed(self, filed):
        body = filed.get("/api/v1/market/filings").json()
        assert body["count"] == 2
        assert {f["ticker"] for f in body["filings"]} == {"EXE", "AIG"}

    def test_ordered_by_item_code_not_by_price_move(self, filed):
        # Sorting filings by how far the stock moved would be a causal claim
        # made with a sort key. AIG moved eight times as far as EXE.
        body = filed.get("/api/v1/market/filings").json()
        assert [f["ticker"] for f in body["filings"]] == ["EXE", "AIG"]

    def test_every_filing_carries_the_adjacency_note(self, filed):
        for f in filed.get("/api/v1/market/filings").json()["filings"]:
            assert "adjacency, not cause" in f["note"]

    def test_a_missing_filing_url_is_passed_through_not_invented(self, filed):
        aig = [f for f in filed.get("/api/v1/market/filings").json()["filings"]
               if f["ticker"] == "AIG"][0]
        assert aig["url"] is None

    def test_no_published_scan_says_so(self, monkeypatch):
        from app.services.data import snapshot_service
        monkeypatch.setattr(snapshot_service, "get_snapshot", lambda *a, **k: None)
        assert TestClient(app).get("/api/v1/market/filings").json()["available"] is False
