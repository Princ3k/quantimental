"""
Technical indicators — pure NumPy/pandas implementations.

Why this module exists
----------------------
Quantimental previously called TA-Lib, which is a C library that has to be
installed out-of-band (`brew install ta-lib`, apt, or a custom Nixpacks layer)
before `pip install TA-Lib` will even build. That made the backend impossible
to install on a clean machine and painful to deploy.

Every indicator below is standard, well-documented math. Implementing them
directly removes the native dependency entirely: `pip install -r requirements.txt`
is now sufficient, on any platform, and the functions are directly unit-testable.

Conventions
-----------
- Every function takes and returns 1-D float arrays aligned to the input.
- Leading values that cannot be computed yet are NaN, matching TA-Lib's
  behaviour, so callers can keep using `[-1]` to read the latest value.
- Wilder's smoothing (used by RSI, ATR, ADX) is an EMA with alpha = 1/period,
  which is what TA-Lib uses and what most charting platforms display.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

__all__ = [
    "sma",
    "ema",
    "wilder_smooth",
    "rsi",
    "macd",
    "bollinger_bands",
    "stochastic",
    "true_range",
    "atr",
    "adx",
]


def _as_series(values: np.ndarray | pd.Series) -> pd.Series:
    """Coerce input to a float Series so pandas' rolling/ewm math is available."""
    if isinstance(values, pd.Series):
        return values.astype(float).reset_index(drop=True)
    return pd.Series(np.asarray(values, dtype=float))


def sma(values: np.ndarray, period: int) -> np.ndarray:
    """Simple moving average."""
    return _as_series(values).rolling(window=period, min_periods=period).mean().to_numpy()


def ema(values: np.ndarray, period: int) -> np.ndarray:
    """
    Exponential moving average.

    Seeded with an SMA of the first `period` values (TA-Lib's convention) rather
    than pandas' default of starting from the first observation, so MACD lines
    match what traders see on standard charting tools.
    """
    series = _as_series(values)
    if len(series) < period:
        return np.full(len(series), np.nan)

    result = np.full(len(series), np.nan, dtype=float)
    seed = series.iloc[:period].mean()
    result[period - 1] = seed

    multiplier = 2.0 / (period + 1.0)
    previous = seed
    for i in range(period, len(series)):
        previous = (series.iloc[i] - previous) * multiplier + previous
        result[i] = previous
    return result


def wilder_smooth(values: np.ndarray, period: int) -> np.ndarray:
    """
    Wilder's smoothing: an EMA with alpha = 1/period.

    Used by RSI, ATR and ADX. Seeded with a simple average of the first
    `period` values, which is how Wilder originally defined it.
    """
    series = _as_series(values)
    if len(series) < period:
        return np.full(len(series), np.nan)

    result = np.full(len(series), np.nan, dtype=float)
    seed = series.iloc[:period].mean()
    result[period - 1] = seed

    previous = seed
    for i in range(period, len(series)):
        previous = (previous * (period - 1) + series.iloc[i]) / period
        result[i] = previous
    return result


def rsi(closes: np.ndarray, period: int = 14) -> np.ndarray:
    """
    Relative Strength Index (0-100).

    Above 70 is conventionally read as overbought, below 30 as oversold.
    """
    series = _as_series(closes)
    if len(series) <= period:
        return np.full(len(series), np.nan)

    delta = series.diff()
    gains = delta.clip(lower=0.0).fillna(0.0).to_numpy()
    losses = (-delta.clip(upper=0.0)).fillna(0.0).to_numpy()

    # Wilder's smoothing is applied from index 1 (the first diff is undefined),
    # so smooth the tail and shift the result back into place.
    avg_gain = np.full(len(series), np.nan)
    avg_loss = np.full(len(series), np.nan)
    avg_gain[1:] = wilder_smooth(gains[1:], period)
    avg_loss[1:] = wilder_smooth(losses[1:], period)

    with np.errstate(divide="ignore", invalid="ignore"):
        rs = np.divide(avg_gain, avg_loss)
        result = 100.0 - (100.0 / (1.0 + rs))

    # A period with zero losses is maximally strong (RSI 100), not undefined.
    result = np.where((avg_loss == 0) & ~np.isnan(avg_gain), 100.0, result)
    return result


def macd(
    closes: np.ndarray,
    fast_period: int = 12,
    slow_period: int = 26,
    signal_period: int = 9,
) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """
    Moving Average Convergence Divergence.

    Returns (macd_line, signal_line, histogram). The signal line is an EMA of
    the MACD line, so it is computed over the MACD's valid tail only.
    """
    fast = ema(closes, fast_period)
    slow = ema(closes, slow_period)
    macd_line = fast - slow

    signal_line = np.full(len(macd_line), np.nan)
    valid = ~np.isnan(macd_line)
    if valid.sum() >= signal_period:
        first_valid = int(np.argmax(valid))
        signal_line[first_valid:] = ema(macd_line[first_valid:], signal_period)

    histogram = macd_line - signal_line
    return macd_line, signal_line, histogram


def bollinger_bands(
    closes: np.ndarray,
    period: int = 20,
    num_std: float = 2.0,
) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """
    Bollinger Bands. Returns (upper, middle, lower).

    Uses the population standard deviation (ddof=0), matching TA-Lib.
    """
    series = _as_series(closes)
    middle = series.rolling(window=period, min_periods=period).mean()
    std = series.rolling(window=period, min_periods=period).std(ddof=0)
    return (
        (middle + num_std * std).to_numpy(),
        middle.to_numpy(),
        (middle - num_std * std).to_numpy(),
    )


def stochastic(
    highs: np.ndarray,
    lows: np.ndarray,
    closes: np.ndarray,
    fastk_period: int = 14,
    slowk_period: int = 3,
    slowd_period: int = 3,
) -> tuple[np.ndarray, np.ndarray]:
    """
    Slow Stochastic Oscillator. Returns (slow_k, slow_d), both 0-100.

    Below 20 is conventionally oversold, above 80 overbought.
    """
    high_s, low_s, close_s = _as_series(highs), _as_series(lows), _as_series(closes)

    highest = high_s.rolling(window=fastk_period, min_periods=fastk_period).max()
    lowest = low_s.rolling(window=fastk_period, min_periods=fastk_period).min()
    span = highest - lowest

    # A flat window (high == low) has no meaningful position; treat it as mid-range
    # rather than dividing by zero.
    fast_k = pd.Series(
        np.where(span > 0, (close_s - lowest) / span * 100.0, 50.0),
        index=close_s.index,
    ).where(~span.isna())

    slow_k = fast_k.rolling(window=slowk_period, min_periods=slowk_period).mean()
    slow_d = slow_k.rolling(window=slowd_period, min_periods=slowd_period).mean()
    return slow_k.to_numpy(), slow_d.to_numpy()


def true_range(highs: np.ndarray, lows: np.ndarray, closes: np.ndarray) -> np.ndarray:
    """
    True Range: the greatest of (high-low), |high-prev_close|, |low-prev_close|.

    The first bar has no previous close, so its true range is genuinely
    undefined and is returned as NaN. Callers that need a value for bar 0
    should use (high - low) explicitly.
    """
    high_s, low_s, close_s = _as_series(highs), _as_series(lows), _as_series(closes)
    prev_close = close_s.shift(1)

    ranges = pd.concat(
        [high_s - low_s, (high_s - prev_close).abs(), (low_s - prev_close).abs()],
        axis=1,
    )
    tr = ranges.max(axis=1)
    tr.iloc[0] = np.nan
    return tr.to_numpy()


def atr(
    highs: np.ndarray,
    lows: np.ndarray,
    closes: np.ndarray,
    period: int = 14,
) -> np.ndarray:
    """
    Average True Range — a volatility measure in price units.

    Seeded from TR[1..period]; bar 0 is excluded because it has no true range.
    The first ATR value therefore lands at index `period`.
    """
    tr = true_range(highs, lows, closes)
    result = np.full(len(tr), np.nan)
    if len(tr) > period:
        result[1:] = wilder_smooth(tr[1:], period)
    return result


def adx(
    highs: np.ndarray,
    lows: np.ndarray,
    closes: np.ndarray,
    period: int = 14,
) -> np.ndarray:
    """
    Average Directional Index (0-100) — trend *strength*, regardless of direction.

    Above 25 is conventionally a trending market, below 20 a ranging one.
    """
    high_s, low_s = _as_series(highs), _as_series(lows)

    up_move = high_s.diff()
    down_move = -low_s.diff()

    # A directional move only counts when it exceeds the opposite move.
    plus_dm = np.where((up_move > down_move) & (up_move > 0), up_move, 0.0)
    minus_dm = np.where((down_move > up_move) & (down_move > 0), down_move, 0.0)

    tr = true_range(highs, lows, closes)

    # Bar 0 has no previous close, so it contributes neither a true range nor a
    # directional move. Smooth from bar 1 onward and shift results back into place.
    atr_smoothed = np.full(len(tr), np.nan)
    plus_dm_smoothed = np.full(len(tr), np.nan)
    minus_dm_smoothed = np.full(len(tr), np.nan)
    if len(tr) > period:
        atr_smoothed[1:] = wilder_smooth(tr[1:], period)
        plus_dm_smoothed[1:] = wilder_smooth(plus_dm[1:], period)
        minus_dm_smoothed[1:] = wilder_smooth(minus_dm[1:], period)

    with np.errstate(divide="ignore", invalid="ignore"):
        # A zero average true range means the price did not move at all, so
        # there is no directional movement either. Without this guard the
        # division is 0/0 and ADX becomes NaN for a perfectly flat series.
        safe_atr = np.where(atr_smoothed == 0, np.nan, atr_smoothed)
        plus_di = np.where(atr_smoothed == 0, 0.0, 100.0 * np.divide(plus_dm_smoothed, safe_atr))
        minus_di = np.where(atr_smoothed == 0, 0.0, 100.0 * np.divide(minus_dm_smoothed, safe_atr))
        di_sum = plus_di + minus_di
        dx = 100.0 * np.divide(np.abs(plus_di - minus_di), np.where(di_sum == 0, np.nan, di_sum))

    # When both DIs are zero there is no directional information at all, which
    # is a strength of zero rather than an undefined value.
    dx = np.where(di_sum == 0, 0.0, dx)
    # Preserve NaN only where the inputs genuinely had not warmed up yet.
    dx = np.where(np.isnan(atr_smoothed), np.nan, dx)

    # ADX is a Wilder smoothing of DX, which itself only starts once the DIs exist.
    result = np.full(len(dx), np.nan)
    valid = ~np.isnan(dx)
    if valid.sum() >= period:
        first_valid = int(np.argmax(valid))
        result[first_valid:] = wilder_smooth(dx[first_valid:], period)
    return result
