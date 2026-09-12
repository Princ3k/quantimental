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
