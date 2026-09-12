"""
Tests for the rate limiter.

The API is unauthenticated and `/signals/batch` accepts 60 tickers a call, so
the thing being protected here is real: a loop could spend a month of Railway
credit and get our IP blocked by every upstream in an afternoon. Most of these
tests exist to pin down that cost tracks *work*, and that the client key cannot
be forged.
"""

from __future__ import annotations

import pytest

from app.core.rate_limit import (
    BURST_BUDGET,
    COST_DEEP_ANALYSIS,
    RateLimiter,
    _Bucket,
    client_key,
    is_exempt,
    request_cost,
)


class TestCost:
    def test_a_batch_costs_its_ticker_count(self):
        # Counting a 60-ticker batch as "one request" prices the expensive path
        # at zero, which is the whole hole this closes.
        assert request_cost("/api/v1/signals/batch", 60) == 60
        assert request_cost("/api/v1/signals/batch", 1) == 1

    def test_an_empty_batch_still_costs_something(self):
        assert request_cost("/api/v1/signals/batch", 0) == 1

    def test_deep_analysis_is_priced_above_its_request_size(self):
        # One ticker, but it fetches news and social posts and may call an LLM.
        assert request_cost("/api/v1/signals/analyze") == COST_DEEP_ANALYSIS
        assert COST_DEEP_ANALYSIS > 1


class TestExemptions:
    @pytest.mark.parametrize("path", ["/health", "/docs", "/openapi.json", "/"])
    def test_uptime_and_docs_are_free(self, path):
        assert is_exempt(path)

    @pytest.mark.parametrize(
        "path",
        ["/api/v1/signals/batch", "/api/v1/signals/analyze", "/api/v1/market/signal-desk"],
    )
    def test_everything_under_api_is_charged(self, path):
        assert not is_exempt(path)


class TestClientKey:
    def test_trusts_the_last_forwarded_entry_not_the_first(self):
        # X-Forwarded-For is client-controlled. Trusting the first entry lets
        # anyone mint a fresh budget per request by spoofing the header; the
        # proxy appends the real peer, so only the last entry is ours.
        assert client_key("1.2.3.4, 9.9.9.9", None, "10.0.0.1") == "9.9.9.9"

    def test_a_spoofed_header_cannot_change_the_key(self):
        forged = "attacker-chosen"
        real = "203.0.113.7"
        first = client_key(f"{forged}, {real}", None, None)
        second = client_key(f"something-else, {real}", None, None)
        assert first == second == real

    def test_falls_back_through_real_ip_then_peer(self):
        assert client_key(None, "203.0.113.9", "10.0.0.1") == "203.0.113.9"
        assert client_key(None, None, "10.0.0.1") == "10.0.0.1"
        assert client_key(None, None, None) == "unknown"

    def test_ignores_an_empty_forwarded_header(self):
        assert client_key("", None, "10.0.0.1") == "10.0.0.1"
        assert client_key("  ,  ", None, "10.0.0.1") == "10.0.0.1"


class TestBucket:
    def test_starts_full_so_a_first_request_is_never_throttled(self):
        allowed, _ = _Bucket().take(BURST_BUDGET, refill_per_second=1.0, capacity=BURST_BUDGET)
        assert allowed

    def test_refuses_once_drained_and_says_when_to_retry(self):
        bucket = _Bucket(tokens=0.0)
        allowed, retry_after = bucket.take(10.0, refill_per_second=1.0, capacity=100.0)

        assert not allowed
        # Computed from the real refill rate, so a client that honours the hint
        # succeeds rather than backing off blindly.
        assert retry_after == pytest.approx(10.0)

    def test_refills_over_time(self, monkeypatch):
        import app.core.rate_limit as module

        clock = {"t": 1_000.0}
        monkeypatch.setattr(module.time, "monotonic", lambda: clock["t"])

        bucket = _Bucket(tokens=0.0, updated=clock["t"])
        clock["t"] += 50.0

        allowed, _ = bucket.take(40.0, refill_per_second=1.0, capacity=100.0)
        assert allowed

    def test_never_refills_above_capacity(self, monkeypatch):
        # Otherwise a caller who waits a day banks a day's worth of burst.
        import app.core.rate_limit as module

        clock = {"t": 1_000.0}
        monkeypatch.setattr(module.time, "monotonic", lambda: clock["t"])

        bucket = _Bucket(tokens=0.0, updated=clock["t"])
        clock["t"] += 86_400.0
        bucket.take(0.0, refill_per_second=1.0, capacity=100.0)

        assert bucket.tokens == 100.0


class TestLimiter:
    def test_clients_have_separate_budgets(self):
        limiter = RateLimiter(hourly_budget=3_600.0, burst=10.0)

        assert limiter.check("a", 10.0)[0]
        assert not limiter.check("a", 10.0)[0]
        # One caller exhausting itself must not lock out everyone else.
        assert limiter.check("b", 10.0)[0]

    def test_a_large_batch_drains_faster_than_a_small_one(self):
        limiter = RateLimiter(hourly_budget=3_600.0, burst=100.0)

        for _ in range(10):
            assert limiter.check("bulk", 10.0)[0]
        assert not limiter.check("bulk", 10.0)[0]

        # The same number of calls, priced at one ticker each, is still fine.
        for _ in range(10):
            assert limiter.check("light", 1.0)[0]

    def test_idle_clients_are_evicted(self, monkeypatch):
        import app.core.rate_limit as module

        clock = {"t": 1_000.0}
        monkeypatch.setattr(module.time, "monotonic", lambda: clock["t"])

        limiter = RateLimiter(hourly_budget=3_600.0, burst=10.0)
        limiter.check("visitor", 1.0)
        assert len(limiter._buckets) == 1

        # An hour later, a different caller triggers the sweep.
        clock["t"] += module.IDLE_EVICTION_SECONDS + 600.0
        limiter.check("other", 1.0)

        assert "visitor" not in limiter._buckets

    def test_the_heaviest_legitimate_user_is_never_throttled(self, monkeypatch):
        """
        The ceiling must be unreachable by a person actually using the site.

        Sized against the worst legitimate case, not the average one: a full
        60-ticker watchlist refreshing every two minutes for an hour, plus
        deep dives. An earlier budget of 2,000 left this user one refresh from
        a 429 — a limiter that throttles real use breaks the product quietly,
        and only for the most engaged people.
        """
        import app.core.rate_limit as module

        clock = {"t": 1_000.0}
        monkeypatch.setattr(module.time, "monotonic", lambda: clock["t"])

        limiter = RateLimiter()

        for _ in range(30):
            allowed, retry = limiter.check("power-user", 60.0)
            assert allowed, f"throttled a real user, retry in {retry:.0f}s"
            for _ in range(2):
                assert limiter.check("power-user", COST_DEEP_ANALYSIS)[0]
            clock["t"] += 120.0  # two minutes between refreshes

    def test_a_loop_is_throttled_within_seconds(self, monkeypatch):
        # The other side of the same coin: a script that does not pause should
        # hit the ceiling quickly rather than running until the credit is gone.
        import app.core.rate_limit as module

        clock = {"t": 1_000.0}
        monkeypatch.setattr(module.time, "monotonic", lambda: clock["t"])

        limiter = RateLimiter()
        calls = 0
        while limiter.check("scraper", 60.0)[0]:
            calls += 1
            assert calls < 100, "a tight loop was never throttled"

        assert calls <= 10
