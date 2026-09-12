"""
Tests for the startup warmup.

Every cache in this app is in-process, so a deploy starts cold and the first
visitor pays for the DNS, TLS and session handshakes that the hundredth does
not. The warmup moves that off the critical path — but it runs during startup,
where the two ways to make things worse are blocking the healthcheck and
raising.
"""

from __future__ import annotations

import asyncio

import pytest

from app.core import warmup


class TestWarmupSafety:
    @pytest.mark.asyncio
    async def test_an_upstream_failure_never_raises(self, monkeypatch):
        # Upstream being down is a reason to serve slightly slower, not a
        # reason to fail to start.
        async def boom():
            raise RuntimeError("yahoo is down")

        monkeypatch.setattr(warmup, "_warm", boom)
        await warmup.warm()  # must not raise

    @pytest.mark.asyncio
    async def test_a_hung_upstream_is_abandoned_not_waited_on(self, monkeypatch):
        async def forever():
            await asyncio.sleep(3600)

        monkeypatch.setattr(warmup, "_warm", forever)
        monkeypatch.setattr(warmup, "WARMUP_BUDGET_SECONDS", 0.05)

        await asyncio.wait_for(warmup.warm(), timeout=2.0)

    @pytest.mark.asyncio
    async def test_it_warms_what_a_first_page_load_actually_requests(self, monkeypatch):
        # Warming arbitrary tickers would be busywork. These are the ones the
        # dashboard asks for on a first visit.
        asked: list[str] = []
        desk_called = []

        class _Market:
            @staticmethod
            def get_quote(ticker):
                asked.append(ticker)
                return {}

        class _Macro:
            @staticmethod
            def get_desk():
                desk_called.append(True)
                return {}

        import app.services.data.market_data_service as mds
        import app.services.data.macro_signal_service as macro

        monkeypatch.setattr(mds, "market_data_service", _Market())
        monkeypatch.setattr(macro, "macro_signal_service", _Macro())

        await warmup._warm()

        assert set(asked) == set(warmup.WARMUP_TICKERS)
        assert desk_called == [True]

    @pytest.mark.asyncio
    async def test_one_failing_ticker_does_not_abort_the_rest(self, monkeypatch):
        asked: list[str] = []

        class _Market:
            @staticmethod
            def get_quote(ticker):
                asked.append(ticker)
                if ticker == "NVDA":
                    raise RuntimeError("no data")
                return {}

        class _Macro:
            @staticmethod
            def get_desk():
                return {}

        import app.services.data.market_data_service as mds
        import app.services.data.macro_signal_service as macro

        monkeypatch.setattr(mds, "market_data_service", _Market())
        monkeypatch.setattr(macro, "macro_signal_service", _Macro())

        await warmup._warm()

        assert set(asked) == set(warmup.WARMUP_TICKERS)

    def test_it_does_not_spend_reddits_budget(self):
        """
        Reddit allows roughly one request a minute unauthenticated. Spending
        that before anyone has asked for anything would make the first real
        request slower, not faster.
        """
        import inspect

        source = inspect.getsource(warmup)
        for forbidden in ("reddit", "fetch_all_sentiment", "sentiment_service"):
            assert forbidden not in source.lower().replace("# ", "").split('"""')[0]
