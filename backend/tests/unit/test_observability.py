"""
Tests for error reporting, and mostly for its scrubber.

This project published a live MarketAux key once because the key travels in a
query string and the exception message quoting the URL reached a public field.
An error tracker is another way out of the process, so the scrubber is the part
that gets the tests.
"""

from __future__ import annotations

import pytest

from app.core import observability
from app.core.redaction import redact, safe_detail


class TestRedaction:
    def test_a_query_string_credential_is_removed(self):
        # The exact shape that leaked: MarketAux takes its key as a parameter.
        url = "https://api.marketaux.com/v1/news/all?api_token=abc123SECRET&symbols=AAPL"
        scrubbed = redact(url)

        assert "abc123SECRET" not in scrubbed
        assert "api_token=***" in scrubbed
        # Everything else survives, or the message stops being useful.
        assert "symbols=AAPL" in scrubbed

    @pytest.mark.parametrize("secret", [
        "gsk_livekeyvalue123",
        "sk-livekeyvalue123",
        "ghp_livekeyvalue123",
        "github_pat_livekeyvalue123",
        "Bearer livetokenvalue123",
    ])
    def test_credentials_are_caught_by_their_prefix(self, secret):
        scrubbed = redact(f"auth failed for {secret} on retry")
        assert "livekeyvalue123" not in scrubbed
        assert "livetokenvalue123" not in scrubbed

    def test_an_exception_is_described_without_quoting_its_secret(self):
        exc = RuntimeError("401 from https://x.test/v1?api_key=SECRETVALUE")
        detail = safe_detail(exc)

        assert "SECRETVALUE" not in detail
        assert detail.startswith("RuntimeError")

    def test_ordinary_text_is_left_alone(self):
        assert redact("Nvidia is up 1.8% today") == "Nvidia is up 1.8% today"

    def test_empty_input_does_not_explode(self):
        assert redact("") == ""


class TestBeforeSend:
    def test_a_secret_anywhere_in_the_event_is_scrubbed(self):
        # Not just the message: a credential ends up wherever the string
        # holding it went — breadcrumbs, frame locals, request context.
        event = {
            "message": "failed",
            "breadcrumbs": [{"message": "GET https://x.test/v1?api_token=LEAKED"}],
            "extra": {"frames": [{"url": "https://x.test/v1?api_key=ALSOLEAKED"}]},
            "tags": {"provider": "marketaux"},
        }
        scrubbed = observability.before_send(event, {})

        rendered = repr(scrubbed)
        assert "LEAKED" not in rendered
        assert "ALSOLEAKED" not in rendered
        assert scrubbed["tags"]["provider"] == "marketaux"

    def test_nested_structures_are_walked(self):
        event = {"a": [{"b": ("token=DEEPSECRET",)}]}
        assert "DEEPSECRET" not in repr(observability.before_send(event, {}))

    def test_a_scrubber_failure_drops_the_event(self, monkeypatch):
        # The one behaviour that must not be "pass it through anyway".
        def boom(_value):
            raise RuntimeError("scrub failed")

        monkeypatch.setattr(observability, "_scrub", boom)
        assert observability.before_send({"message": "x"}, {}) is None

    def test_client_disconnects_are_not_reported(self):
        event = {"exception": {"values": [{"type": "ClientDisconnect"}]}}
        assert observability.before_send(event, {}) is None

    def test_real_errors_are_reported(self):
        event = {"exception": {"values": [{"type": "ValueError"}]}}
        assert observability.before_send(event, {}) is not None


class TestInit:
    def test_no_dsn_means_the_sdk_never_starts(self, monkeypatch):
        # Local runs and CI must not report anywhere, and the way to be certain
        # is that nothing was initialised at all.
        monkeypatch.setattr(
            observability, "get_settings", lambda: type("S", (), {"SENTRY_DSN": None})()
        )
        assert observability.init_sentry() is False

    def test_a_broken_dsn_does_not_stop_the_api_booting(self, monkeypatch):
        settings = type("S", (), {
            "SENTRY_DSN": "not-a-dsn",
            "SENTRY_ENVIRONMENT": "test",
            "SENTRY_TRACES_SAMPLE_RATE": 0.0,
            "VERSION": "1.0.0",
        })()
        monkeypatch.setattr(observability, "get_settings", lambda: settings)
        assert observability.init_sentry() is False
