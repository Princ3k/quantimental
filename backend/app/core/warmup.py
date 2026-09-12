"""
Prime the caches so the first visitor after a deploy is not the one who pays.

Every cache in this app is in-process — quotes, company profiles, the macro
desk, the sentiment source outcomes. That is the right choice for a single
instance with no database, but it means **every deploy starts cold**, and the
first request does all the work the hundredth does not: DNS and TLS to Yahoo,
the yfinance session handshake, a full macro download, and a sentiment fetch
that can run to its 20-second ceiling on cold connections.

A response measured at 32 seconds immediately after a deploy is consistent with
exactly that, and is the reason this exists. Warming afterwards costs one
batched download that was going to happen anyway, moved off the critical path
of a person waiting.

Three rules it must not break:

**Never block startup.** Railway routes traffic once `/health` answers, and a
warmup that delayed that would turn a slow first request into a failed deploy.
This runs as a background task after the app is already serving.

**Never raise.** Upstream being down is a reason to serve slightly slower, not
to fail to start.

**Never touch a rate-limited source.** Reddit allows roughly one request a
minute without credentials. Spending that budget on a warmup, before anybody
has asked for anything, would make the first real request *worse*.
"""

from __future__ import annotations

import asyncio
import logging
import time

logger = logging.getLogger(__name__)

# What a first-time visitor loads. Warming these specific names is worth more
# than warming arbitrary ones: it is the same list the dashboard requests.
from app.core.config import get_settings  # noqa: E402

WARMUP_TICKERS = ("AAPL", "MSFT", "NVDA", "GOOGL", "AMZN", "TSLA")

# Past this, something is wrong upstream and waiting longer helps nobody. The
# app is already serving by then; this only abandons the optimisation.
WARMUP_BUDGET_SECONDS = 45.0


async def warm() -> None:
    """Fetch what a first page load needs, so it is cached when one arrives."""
    started = time.perf_counter()

    try:
        await asyncio.wait_for(_warm(), timeout=WARMUP_BUDGET_SECONDS)
    except asyncio.TimeoutError:
        logger.warning("Warmup exceeded %.0fs; continuing cold", WARMUP_BUDGET_SECONDS)
    except Exception as exc:  # noqa: BLE001 - a failed warmup is never fatal
        logger.warning("Warmup failed (%s); continuing cold", exc)
    else:
        logger.info("Warmup finished in %.1fs", time.perf_counter() - started)


async def _warm() -> None:
    from app.services.data.macro_signal_service import macro_signal_service
    from app.services.data.market_data_service import market_data_service

    loop = asyncio.get_running_loop()

    # Quotes are cached for 60 seconds, but the *profile* lookup behind them is
    # cached for a day and the yfinance session they establish outlives both.
    # That session handshake is most of what a cold first request pays for.
    await asyncio.gather(
        *(
            loop.run_in_executor(None, market_data_service.get_quote, ticker)
            for ticker in WARMUP_TICKERS
        ),
        return_exceptions=True,
    )

    # The dashboard requests this on every page load, and it downloads
    # seventeen instruments plus a sector sweep.
    await loop.run_in_executor(None, macro_signal_service.get_desk)

    # Deliberately not warmed: the sentiment pipeline. It is only reached at
    # full depth, when somebody explicitly asks for one stock, and Reddit's
    # unauthenticated budget is roughly one request a minute — spending it here
    # would slow down the first person who actually wanted it.
    if get_settings().DEBUG:
        logger.debug("Warmed %d tickers and the macro desk", len(WARMUP_TICKERS))
