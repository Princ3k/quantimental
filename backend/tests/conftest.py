"""Shared fixtures."""

from __future__ import annotations

import numpy as np
import pytest


@pytest.fixture
def rising_prices() -> np.ndarray:
    """
    250 sessions of an unambiguous uptrend.

    Drift is large relative to noise so the most recent window is trending too.
    Trend detection reads the *last* 20 sessions, so a gentler series can
    legitimately end in a flat patch and classify as sideways — correct
    behaviour, but useless for asserting that an uptrend is recognised.
    """
    rng = np.random.default_rng(1)
    return 100 + np.cumsum(rng.normal(0.5, 0.6, 250))


@pytest.fixture
def falling_prices() -> np.ndarray:
    """250 sessions of an unambiguous downtrend."""
    rng = np.random.default_rng(2)
    return 400 + np.cumsum(rng.normal(-0.5, 0.6, 250))


@pytest.fixture
def flat_prices() -> np.ndarray:
    """
    250 sessions of a range-bound stock: noise around a constant, no drift.

    Deliberately not a sine wave — at the right phase a sine is genuinely
    trending, which makes it a misleading stand-in for a flat market.
    """
    rng = np.random.default_rng(3)
    return 100 + rng.normal(0.0, 0.6, 250)


@pytest.fixture
def ohlc(rising_prices):
    """(highs, lows, closes) derived from a close series."""
    closes = rising_prices
    return closes + 1.0, closes - 1.0, closes


@pytest.fixture(autouse=True)
def _reset_rate_limiter():
    """
    Give every test a full budget.

    The limiter keys on client address, and every test shares one, so without
    this a test that sends a 60-ticker batch quietly drains the budget for
    whatever runs next — and the failure surfaces as an unrelated 429.
    """
    from app.core.rate_limit import rate_limiter

    rate_limiter.reset()
    yield
    rate_limiter.reset()
