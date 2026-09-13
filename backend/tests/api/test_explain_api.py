"""
API tests for the explanation endpoint.

This is the one endpoint meant to be depended on by somebody else's code, so
these tests assert the published contract — field names, what is null and when,
what happens to a symbol nobody has heard of — rather than just the status code.

The snapshot is stubbed throughout: nothing here touches the network.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.services.data import snapshot_service


def _row(ticker="NVDA", **overrides):
    row = {
        "t": ticker,
        "n": "NVIDIA Corporation",
        "s": "Information Technology",
        "p": 178.19,
        "c": 1.8,
        "x": 0.9,
        "d": 2.0,
        "w": 5.6,
        "h": "NVIDIA Corporation is up 1.8% today, and up 5.6% over the past two weeks.",
        "st": "rising",
        "ctx": "The market rose 0.3% today and Information Technology rose 0.4%, "
               "so this move tracked the market rather than anything specific to "
               "NVIDIA Corporation.",
        "mkt": 0.3,
        "sec": 0.4,
        "v": 133.31,
    }
    row.update(overrides)
    return row


@pytest.fixture
def snapshot(monkeypatch):
    """Install a published scan, and hand back the rows so tests can vary it."""
    rows = {"NVDA": _row(), "AOS": _row("AOS", n="A. O. Smith", v=0.24, vx=None)}

    def _install(**overrides):
        rows.update(overrides)
        snap = snapshot_service.Snapshot(
            rows=rows,
            as_of="2026-09-12",
            generated_at="2026-09-13T00:08:12Z",
            fetched_at=0.0,
        )
        monkeypatch.setattr(snapshot_service, "get_snapshot", lambda force=False: snap)
        return snap

    _install()
    return _install


@pytest.fixture
def client():
    return TestClient(app)


class TestSingle:
    def test_returns_the_sentence_and_the_numbers_behind_it(self, client, snapshot):
        body = client.get("/api/v1/explain/NVDA").json()

        assert body["ticker"] == "NVDA"
        assert body["company"] == "NVIDIA Corporation"
        assert body["explanation"].startswith("NVIDIA Corporation is up 1.8% today")
        assert body["movement"]["change_percent"] == 1.8
        assert body["movement"]["change_percent_2w"] == 5.6
        assert body["attribution"]["sector"] == "Information Technology"
        assert body["attribution"]["market_percent"] == 0.3
        assert body["coverage"]["articles_per_day"] == 133.31

    def test_every_response_carries_the_disclosure(self, client, snapshot):
        # It has to travel with the text, because the text is what gets
        # rendered somewhere we will never see.
        body = client.get("/api/v1/explain/NVDA").json()
        assert "Not investment advice" in body["disclosure"]

    def test_it_says_which_session_it_describes(self, client, snapshot):
        body = client.get("/api/v1/explain/NVDA").json()
        assert body["as_of"] == "2026-09-12"
        assert body["generated_at"] == "2026-09-13T00:08:12Z"

    def test_a_missing_coverage_multiple_is_null_not_absent(self, client, snapshot):
        # Null means "not enough history yet", which is a real answer. Dropping
        # the key would make a consumer guess.
        body = client.get("/api/v1/explain/AOS").json()
        assert body["coverage"]["multiple_of_normal"] is None
        assert body["coverage"]["articles_per_day"] == 0.24

    def test_lowercase_and_whitespace_are_accepted(self, client, snapshot):
        assert client.get("/api/v1/explain/  nvda  ").json()["ticker"] == "NVDA"

    def test_an_unknown_ticker_is_a_404(self, client, snapshot):
        response = client.get("/api/v1/explain/ZZZZ")
        assert response.status_code == 404
        assert "ZZZZ" in response.json()["detail"]

    def test_no_scan_available_is_a_503_not_a_500(self, client, monkeypatch):
        monkeypatch.setattr(snapshot_service, "get_snapshot", lambda force=False: None)
        assert client.get("/api/v1/explain/NVDA").status_code == 503

    def test_it_never_rates_or_recommends(self, client, snapshot):
        # The whole reason this endpoint is embeddable. A rating leaking into
        # the contract is the one regression that matters here.
        body = client.get("/api/v1/explain/NVDA").json()
        assert not {"rating", "verdict", "action", "score", "recommendation"} & set(body)


class TestBatch:
    def test_returns_one_entry_per_known_ticker(self, client, snapshot):
        body = client.get("/api/v1/explain", params={"tickers": "NVDA,AOS"}).json()

        assert body["count"] == 2
        assert [e["ticker"] for e in body["explanations"]] == ["NVDA", "AOS"]
        assert body["not_found"] == []

    def test_unknown_tickers_do_not_fail_the_call(self, client, snapshot):
        # Somebody rendering forty positions should get the thirty-eight that
        # worked, not an error for the two that were delisted.
        body = client.get("/api/v1/explain", params={"tickers": "NVDA,ZZZZ"}).json()

        assert body["count"] == 1
        assert body["not_found"] == ["ZZZZ"]

    def test_duplicates_are_collapsed(self, client, snapshot):
        body = client.get("/api/v1/explain", params={"tickers": "NVDA,nvda, NVDA "}).json()
        assert body["count"] == 1

    def test_an_empty_list_is_a_422(self, client, snapshot):
        assert client.get("/api/v1/explain", params={"tickers": " , "}).status_code == 422

    def test_the_batch_is_capped(self, client, snapshot):
        too_many = ",".join(f"T{i}" for i in range(101))
        response = client.get("/api/v1/explain", params={"tickers": too_many})

        assert response.status_code == 422
        assert "101" in response.json()["detail"]


class TestSnapshotCache:
    def test_a_failed_refresh_serves_the_last_good_scan(self, monkeypatch):
        # A blip at GitHub must not take somebody's page down. A stale sentence
        # with an honest as_of on it beats a 502.
        snapshot_service.reset_cache()
        good = {"as_of": "2026-09-12", "generated_at": "x", "stocks": [_row()]}

        monkeypatch.setattr(
            snapshot_service.httpx, "get",
            lambda *a, **k: type("R", (), {
                "raise_for_status": lambda self: None, "json": lambda self: good,
            })(),
        )
        first = snapshot_service.get_snapshot(force=True)
        assert first is not None and "NVDA" in first.rows

        def boom(*a, **k):
            raise RuntimeError("network down")

        monkeypatch.setattr(snapshot_service.httpx, "get", boom)
        assert snapshot_service.get_snapshot(force=True) is first

    def test_an_empty_publish_does_not_replace_a_good_scan(self, monkeypatch):
        # A valid document with no stocks is a bad publish, not an empty market.
        snapshot_service.reset_cache()
        payloads = [
            {"as_of": "2026-09-12", "generated_at": "x", "stocks": [_row()]},
            {"as_of": "2026-09-13", "generated_at": "y", "stocks": []},
        ]

        def fake_get(*a, **k):
            payload = payloads.pop(0) if payloads else {"stocks": []}
            return type("R", (), {
                "raise_for_status": lambda self: None, "json": lambda self: payload,
            })()

        monkeypatch.setattr(snapshot_service.httpx, "get", fake_get)
        good = snapshot_service.get_snapshot(force=True)
        assert snapshot_service.get_snapshot(force=True) is good
