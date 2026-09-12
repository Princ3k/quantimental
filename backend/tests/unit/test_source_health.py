"""
Tests for source health reporting.

The bug being prevented: `/health` inferred whether a source worked from
whether its key was set, and was wrong in both directions at once — reporting
Twitter healthy while every request returned 401, and Reddit broken while it
was serving posts over a keyless path. A monitor that points at the wrong
source is worse than no monitor.
"""

from __future__ import annotations

import pytest

from app.core.source_health import SourceHealth
from app.services.ingestion.sentiment.sentiment_data_fetcher import _safe_detail


@pytest.fixture
def health():
    return SourceHealth()


class TestConfiguredVersusWorking:
    def test_a_configured_but_rejected_source_is_not_reported_as_working(self, health):
        # Twitter: key present, provider says 401. The old check called this
        # healthy purely because a key existed.
        health.record("twitter", "error", "HTTP 401 — key rejected by ScrapeBadger")
        described = health.describe("twitter", configured=True)

        assert described["configured"] is True
        assert described["working"] is False
        assert "401" in described["detail"]

    def test_an_unconfigured_but_working_source_is_not_reported_as_broken(self, health):
        # Reddit: no OAuth credentials, but the RSS path needs none and works.
        # The old check read fields that path never touches.
        health.record("reddit", "ok")
        described = health.describe("reddit", configured=False)

        assert described["configured"] is False
        assert described["working"] is True

    def test_an_unobserved_source_is_unknown_rather_than_guessed(self, health):
        # Immediately after a deploy nothing has been asked yet. Guessing from
        # configuration is exactly how this went wrong.
        described = health.describe("marketaux", configured=True)

        assert described["configured"] is True
        assert described["working"] is None
        assert described["last_result"] is None
        assert described["observed_at"] is None

    def test_a_source_that_answered_with_nothing_is_still_working(self, health):
        # "This company had a quiet week" is a functioning source.
        assert health.describe("marketaux", True)["working"] is None
        health.record("marketaux", "empty", "no articles for this symbol")
        assert health.describe("marketaux", True)["working"] is True

    def test_a_deliberately_disabled_source_is_not_working(self, health):
        # Not a fault, but not something to report as operational either.
        health.record("twitter", "disabled", "TWITTER_API_KEY is not set")
        assert health.describe("twitter", False)["working"] is False

    def test_the_latest_observation_wins(self, health):
        health.record("reddit", "error", "HTTP 429")
        health.record("reddit", "ok")

        described = health.describe("reddit", configured=False)
        assert described["working"] is True
        assert described["detail"] is None


class TestRecordAll:
    def test_records_a_whole_sentiment_fetch(self, health):
        health.record_all({
            "reddit": {"status": "ok", "count": 7, "detail": None},
            "twitter": {"status": "error", "count": 0, "detail": "HTTP 401"},
        })

        assert health.describe("reddit", False)["working"] is True
        assert health.describe("twitter", True)["working"] is False

    def test_ignores_malformed_entries(self, health):
        health.record_all({"reddit": "not a dict", "twitter": {"count": 0}})

        assert health.describe("reddit", False)["working"] is None
        assert health.describe("twitter", True)["working"] is None

    def test_tolerates_an_empty_block(self, health):
        health.record_all({})
        health.record_all(None)  # type: ignore[arg-type]


class TestDetailRedaction:
    """
    Source details are published on every analyse response, and MarketAux takes
    its key as `api_token` in the query string. An exception carrying the
    request URL would put a live credential into a public payload.
    """

    def test_a_key_in_a_query_string_is_redacted(self):
        detail = _safe_detail(Exception(
            "Request URL is https://api.marketaux.com/v1/news/all"
            "?api_token=liveSecret123&symbols=AAPL"
        ))

        assert "liveSecret123" not in detail
        assert "api_token=***" in detail
        # Still says enough to debug with.
        assert "marketaux.com" in detail

    @pytest.mark.parametrize(
        "param", ["api_token", "api_key", "apikey", "access_token", "token", "key"]
    )
    def test_every_credential_parameter_name_is_covered(self, param):
        assert "SECRET" not in _safe_detail(Exception(f"https://x.test/a?{param}=SECRET&b=1"))

    def test_key_shaped_prefixes_are_redacted(self):
        detail = _safe_detail(Exception("auth failed for gsk_liveKey123 via Bearer sk-abc999"))

        assert "gsk_liveKey123" not in detail
        assert "sk-abc999" not in detail

    def test_ordinary_errors_survive_intact(self):
        assert _safe_detail(Exception("plain network failure")) == (
            "Exception: plain network failure"
        )

    def test_long_provider_errors_are_truncated(self):
        assert len(_safe_detail(Exception("x" * 5_000))) <= 200
