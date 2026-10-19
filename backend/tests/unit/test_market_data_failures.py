"""
The two ways a quote can fail, and why they must not be confused.

"This symbol does not exist" and "we could not reach Yahoo just now" both end
in a fetch with no rows. They are different claims: one is about the ticker and
stays true, the other is about us and is over in seconds.

Collapsing them had a specific cost. The dashboard opened every watchlist
ticker at once, Yahoo throttled the burst, and each throttled fetch was cached
for a minute as "No market data available for MSFT. Check the symbol is
correct." — shown beside a Remove button, inviting people to delete real
holdings over a momentary blip.
"""

from __future__ import annotations

import asyncio

import pandas as pd
import pytest

from app.services.data.market_data_service import (
    MarketDataService,
    MarketDataUnavailable,
)


@pytest.fixture
def service():
    return MarketDataService()


class TestTellingTheFailuresApart:
    def test_a_fetch_error_is_reported_as_ours_not_the_symbols(self, service, monkeypatch):
        def explode(*_args, **_kwargs):
            raise MarketDataUnavailable("429 Too Many Requests")

        monkeypatch.setattr(service, "get_historical_data", explode)
        quote = service.get_quote("MSFT")

        assert quote["available"] is False
        assert quote["transient"] is True
        assert "Try again shortly" in quote["reason"]
        assert "symbol is correct" not in quote["reason"]

    def test_a_fetch_error_is_not_cached(self, service, monkeypatch):
        # The whole point. A throttle that clears in two seconds must not keep
        # a wrong sentence on screen for the full sixty-second TTL.
        calls = {"n": 0}

        def flaky(*_args, **_kwargs):
            calls["n"] += 1
            if calls["n"] == 1:
                raise MarketDataUnavailable("throttled")
            return pd.DataFrame({"Close": [1.0] * 30, "High": [1.0] * 30,
                                 "Low": [1.0] * 30, "Volume": [100.0] * 30})

        monkeypatch.setattr(service, "get_historical_data", flaky)
        monkeypatch.setattr(service, "get_company_info", lambda _s: {"name": "Microsoft"})

        first = service.get_quote("MSFT")
        second = service.get_quote("MSFT")

        assert first["available"] is False
        assert second["available"] is True, "the recovery must be visible at once"
        assert calls["n"] == 2, "the failure must not have been served from cache"

    def test_an_unknown_symbol_is_cached(self, service, monkeypatch):
        # This one is about the ticker and will still be true in a minute, so
        # it should not re-hit Yahoo on every keystroke of a search box.
        calls = {"n": 0}

        def empty(*_args, **_kwargs):
            calls["n"] += 1
            return pd.DataFrame()

        monkeypatch.setattr(service, "get_historical_data", empty)

        first = service.get_quote("NOSUCHTICKER")
        second = service.get_quote("NOSUCHTICKER")

        assert first["transient"] is False
        assert "symbol is correct" in first["reason"]
        assert calls["n"] == 1, "a known-bad symbol should be served from cache"
        assert second == first

    def test_the_underlying_fetch_raises_rather_than_returning_nothing(self, service, monkeypatch):
        # An empty frame here would be indistinguishable from a symbol Yahoo
        # has no rows for, which is where the whole confusion started.
        import app.services.data.market_data_service as module

        class Boom:
            def __init__(self, *_a, **_k): ...
            def history(self, *_a, **_k):
                raise ConnectionError("connection reset")

        monkeypatch.setattr(module.yf, "Ticker", Boom)

        with pytest.raises(MarketDataUnavailable):
            service.get_historical_data("MSFT")


class TestBoundedConcurrency:
    @pytest.mark.asyncio
    async def test_no_more_than_the_cap_are_in_flight_at_once(self, monkeypatch):
        # A default watchlist used to open six simultaneous upstream fetches
        # and a full one sixty. The cap is what keeps the burst small enough
        # not to be throttled in the first place.
        from app.services.signals import live_signal_service as module

        in_flight = 0
        peak = 0

        async def slow_generate(_self, symbol, depth=None):
            nonlocal in_flight, peak
            in_flight += 1
            peak = max(peak, in_flight)
            await asyncio.sleep(0.01)
            in_flight -= 1
            return {"ticker": symbol, "available": True}

        monkeypatch.setattr(module.LiveSignalService, "generate", slow_generate)

        service = module.LiveSignalService()
        signals, failures = await service.generate_many([f"T{i}" for i in range(30)])

        assert len(signals) == 30
        assert failures == []
        assert peak <= module.MAX_CONCURRENT_FETCHES
