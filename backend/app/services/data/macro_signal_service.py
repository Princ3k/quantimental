"""
Macro Signal Service — the data behind the Signal Desk.

Reads a small basket of market-wide instruments (rates, credit, the dollar,
commodities, volatility, sector ETFs) and turns each into a categorised signal
with a direction, a magnitude, and a z-score saying how unusual that move is
against its own trailing year.

Why z-scores matter here: "crude +9.6%" means nothing on its own to a reader
who does not know whether that is a normal week for oil. "+2.4 sigma" says it
is a genuinely large move for *this* instrument. It is also what makes the
composite comparable across instruments that have wildly different volatility.

Everything comes from the same free Yahoo Finance feed the rest of the app
already uses — one batched request for the whole universe.
"""

from __future__ import annotations

import logging
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from typing import Any, Literal, Optional

import numpy as np
import pandas as pd
import yfinance as yf

from app.services.data.market_data_service import _TTLCache

logger = logging.getLogger(__name__)

Direction = Literal["up", "down", "flat"]
RiskTone = Literal["risk_on", "risk_off", "neutral"]

# Macro moves on a slower clock than a single stock quote, and this basket is
# identical for every viewer, so one fetch serves everyone for a few minutes.
CACHE_TTL_SECONDS = 300

# Trading days used for the headline change. Five is "this week" — long enough
# to be a move rather than a single session's noise.
LOOKBACK_DAYS = 5

# A move needs to clear this many standard deviations before it is worth
# putting in front of someone as a signal.
NOTABLE_SIGMA = 0.75


@dataclass(frozen=True)
class Instrument:
    """One tradable series and how to read it."""

    symbol: str
    category: str
    name: str
    # What a *rising* value implies for risk appetite. Yields rising and the
    # dollar strengthening are both conventionally risk-off for equities.
    rising_means: RiskTone
    # How to phrase a rise and a fall, in plain English.
    up_text: str
    down_text: str
    unit: Literal["percent", "level", "bp"] = "percent"


MACRO_UNIVERSE: tuple[Instrument, ...] = (
    Instrument("^VIX", "VOL", "Volatility index", "risk_off",
               "Volatility rising — more uncertainty priced in",
               "Volatility easing — a calmer tape", unit="level"),
    Instrument("^TNX", "RATES", "10-year Treasury yield", "risk_off",
               "Long-term rates climbing", "Long-term rates easing", unit="bp"),
    Instrument("HYG", "CREDIT", "High-yield credit", "risk_on",
               "High-yield credit bid — appetite for risk improving",
               "High-yield credit under pressure"),
    Instrument("LQD", "CREDIT", "Investment-grade credit", "risk_on",
               "Investment-grade credit firm", "Investment-grade credit softening"),
    Instrument("DX-Y.NYB", "FX", "US dollar index", "risk_off",
               "Dollar strengthening", "Dollar fading"),
    Instrument("CL=F", "COMMODITIES", "Crude oil", "neutral",
               "Crude pushing higher", "Crude sliding"),
    Instrument("GC=F", "COMMODITIES", "Gold", "risk_off",
               "Gold bid — a defensive tilt", "Gold easing back"),
)

# Sector ETFs, used for leadership and breadth rather than individual signals.
SECTOR_ETFS: dict[str, str] = {
    "XLK": "Technology",
    "XLF": "Financials",
    "XLE": "Energy",
    "XLV": "Health Care",
    "XLI": "Industrials",
    "XLY": "Consumer Discretionary",
    "XLP": "Consumer Staples",
    "XLU": "Utilities",
    "XLB": "Materials",
    "XLC": "Communications",
}


@dataclass
class MacroSignal:
    """One reading, ready to render."""

    category: str
    name: str
    text: str
    direction: Direction
    delta: str
    change_percent: float
    z_score: float
    risk_tone: RiskTone
    notable: bool


_cache = _TTLCache(CACHE_TTL_SECONDS)


class MacroSignalService:
    """Builds the Signal Desk payload from live market data."""

    def get_desk(self) -> dict[str, Any]:
        """
        Full Signal Desk payload: signals, composite, sector leadership.

        Returns ``available: False`` with a reason if market data cannot be
        reached, rather than inventing a market picture.
        """
        cached = _cache.get("desk")
        if cached is not None:
            return cached

        closes = self._fetch_closes()
        if closes is None or closes.empty:
            return {
                "available": False,
                "reason": "Market data is temporarily unavailable.",
                "as_of": datetime.now(timezone.utc).isoformat(),
            }

        signals = self._build_signals(closes)
        sectors = self._build_sectors(closes)
        composite = self._build_composite(signals, sectors)

        payload = {
            "available": True,
            "as_of": datetime.now(timezone.utc).isoformat(),
            "lookback_days": LOOKBACK_DAYS,
            "signals": [asdict(s) for s in signals],
            "sectors": sectors,
            "composite": composite,
            "history": self._composite_history(closes),
        }
        _cache.set("desk", payload)
        return payload

    # ------------------------------------------------------------------
    # Data
    # ------------------------------------------------------------------

    def _fetch_closes(self) -> Optional[pd.DataFrame]:
        """One batched request for the whole universe; a year of daily closes."""
        symbols = [i.symbol for i in MACRO_UNIVERSE] + list(SECTOR_ETFS)
        try:
            raw = yf.download(
                symbols, period="1y", progress=False, auto_adjust=True, threads=True
            )
        except Exception as exc:
            logger.error("Macro universe fetch failed: %s", exc)
            return None

        if raw is None or raw.empty or "Close" not in raw:
            return None

        closes = raw["Close"]
        # Instruments keep different holiday calendars (futures, FX and equity
        # ETFs disagree), so a gap is a closed market, not missing data.
        return closes.ffill().dropna(how="all")

    # ------------------------------------------------------------------
    # Signals
    # ------------------------------------------------------------------

    @staticmethod
    def _change_and_z(series: pd.Series) -> Optional[tuple[float, float, float]]:
        """
        Return (latest value, percent change over the lookback, z-score).

        The z-score standardises this week's move against the distribution of
        every overlapping 5-day move in the trailing year, so it answers "is
        this a big move *for this instrument*".
        """
        clean = series.dropna()
        if len(clean) < LOOKBACK_DAYS + 30:
            return None

        latest = float(clean.iloc[-1])
        prior = float(clean.iloc[-(LOOKBACK_DAYS + 1)])
        if prior == 0:
            return None

        change = (latest - prior) / abs(prior) * 100.0

        rolling = clean.pct_change(LOOKBACK_DAYS).dropna() * 100.0
        std = float(rolling.std())
        # A flat series has no scale to measure against; call it unremarkable
        # rather than dividing by zero.
        z = (change - float(rolling.mean())) / std if std > 1e-9 else 0.0

        return latest, change, float(z)

    def _build_signals(self, closes: pd.DataFrame) -> list[MacroSignal]:
        """One signal per macro instrument, most unusual first."""
        signals: list[MacroSignal] = []

        for inst in MACRO_UNIVERSE:
            if inst.symbol not in closes:
                continue
            measured = self._change_and_z(closes[inst.symbol])
            if measured is None:
                continue
            latest, change, z = measured

            if abs(change) < 0.05:
                direction: Direction = "flat"
            else:
                direction = "up" if change > 0 else "down"

            # Risk tone flips when the instrument falls.
            if inst.rising_means == "neutral":
                tone: RiskTone = "neutral"
            elif direction == "flat":
                tone = "neutral"
            elif direction == "up":
                tone = inst.rising_means
            else:
                tone = "risk_on" if inst.rising_means == "risk_off" else "risk_off"

            if direction == "flat":
                # "Dollar fading" next to a 0.0% move reads as a contradiction.
                text = f"{inst.name} little changed"
            else:
                text = inst.up_text if change > 0 else inst.down_text

            signals.append(
                MacroSignal(
                    category=inst.category,
                    name=inst.name,
                    text=text,
                    direction=direction,
                    delta=self._format_delta(inst, latest, change, z),
                    change_percent=round(change, 2),
                    z_score=round(z, 2),
                    risk_tone=tone,
                    notable=abs(z) >= NOTABLE_SIGMA,
                )
            )

        # Lead with the most statistically unusual moves — those are the ones
        # that actually carry information today.
        signals.sort(key=lambda s: abs(s.z_score), reverse=True)
        return signals

    @staticmethod
    def _format_delta(inst: Instrument, latest: float, change: float, z: float) -> str:
        """
        Format the magnitude the way a desk would read it.

        Big moves are quoted in sigma because that is the honest comparison;
        ordinary moves are quoted in their natural unit.
        """
        if abs(z) >= 1.5:
            return f"{z:+.1f}σ"
        if inst.unit == "bp":
            # ^TNX is quoted in percent, so a 0.05 move is 5 basis points.
            return f"{(latest - latest / (1 + change / 100)) * 100:+.0f}bp"
        if inst.unit == "level":
            return f"{latest:.1f}"
        return f"{change:+.1f}%"

    # ------------------------------------------------------------------
    # Sectors
    # ------------------------------------------------------------------

    def _build_sectors(self, closes: pd.DataFrame) -> dict[str, Any]:
        """Sector leadership and breadth over the lookback window."""
        performance: list[dict[str, Any]] = []

        for symbol, label in SECTOR_ETFS.items():
            if symbol not in closes:
                continue
            measured = self._change_and_z(closes[symbol])
            if measured is None:
                continue
            _, change, z = measured
            performance.append(
                {
                    "symbol": symbol,
                    "name": label,
                    "change_percent": round(change, 2),
                    "z_score": round(z, 2),
                }
            )

        if not performance:
            return {"available": False, "leaders": [], "laggards": [], "breadth": None}

        performance.sort(key=lambda s: s["change_percent"], reverse=True)
        advancing = sum(1 for s in performance if s["change_percent"] > 0)

        return {
            "available": True,
            "leaders": performance[:3],
            "laggards": performance[-3:][::-1],
            "breadth": round(advancing / len(performance) * 100),
            "advancing": advancing,
            "total": len(performance),
        }

    # ------------------------------------------------------------------
    # Composite
    # ------------------------------------------------------------------

    def _build_composite(
        self, signals: list[MacroSignal], sectors: dict[str, Any]
    ) -> dict[str, Any]:
        """
        A single 0-100 risk-appetite reading.

        50 is neutral. Each signal pushes the score by its own z-score, in the
        direction its risk tone implies, so an unusually large risk-off move
        moves the needle further than a routine one. Sector breadth is folded
        in because a market where most sectors advance is behaving differently
        from one carried by two names.
        """
        score = 50.0
        contributions: list[dict[str, Any]] = []

        # Instruments inside a category are near-duplicates of each other —
        # high-yield and investment-grade credit sell off together, and
        # counting both would let one underlying story vote twice. Average
        # within a category, then sum across categories.
        by_category: dict[str, list[tuple[float, str]]] = {}
        for signal in signals:
            if signal.risk_tone == "neutral":
                continue
            # Clamp: one extreme print should tilt the read, not dominate it.
            magnitude = min(abs(signal.z_score), 3.0) * 6.0
            delta = magnitude if signal.risk_tone == "risk_on" else -magnitude
            by_category.setdefault(signal.category, []).append((delta, signal.name))

        for category, entries in by_category.items():
            effect = sum(d for d, _ in entries) / len(entries)
            score += effect
            label = entries[0][1] if len(entries) == 1 else f"{category.title()} complex"
            contributions.append(
                {
                    "name": label,
                    "effect": round(effect, 1),
                    "tone": "risk_on" if effect >= 0 else "risk_off",
                }
            )

        if sectors.get("available") and sectors.get("breadth") is not None:
            # Breadth of 50% is neutral; 100% adds 10, 0% subtracts 10.
            breadth_delta = (sectors["breadth"] - 50) / 5.0
            score += breadth_delta
            contributions.append(
                {
                    "name": "Sector breadth",
                    "effect": round(breadth_delta, 1),
                    "tone": "risk_on" if breadth_delta >= 0 else "risk_off",
                }
            )

        score = max(0.0, min(100.0, score))

        if score >= 65:
            label, tone = "Risk-on", "risk_on"
        elif score <= 35:
            label, tone = "Risk-off", "risk_off"
        else:
            label, tone = "Mixed", "neutral"

        contributions.sort(key=lambda c: abs(c["effect"]), reverse=True)

        return {
            "score": round(score),
            "label": label,
            "tone": tone,
            "contributions": contributions[:5],
        }

    def _composite_history(self, closes: pd.DataFrame) -> list[float]:
        """
        A 30-session trace of the composite itself.

        Recomputed with the same rules applied at each past date, rather than
        plotting a loosely-related proxy. That matters: an earlier version
        charted an equal-weight sector basket under a "Risk appetite" label,
        so the line could trend green while the score read risk-off — two
        different measures over two different horizons, presented as one.

        The z-scores here are standardised against the whole trailing year,
        the same statistics the live reading uses. That means a past point is
        scored with data from after it, which would be unacceptable for a
        backtest but is the right choice here: it keeps every point on the
        line directly comparable to today's headline number.
        """
        # Percentage change over the same lookback, for every instrument at once.
        changes = closes.pct_change(LOOKBACK_DAYS) * 100.0
        if changes.empty:
            return []

        stats = {c: (changes[c].mean(), changes[c].std()) for c in changes.columns}

        # Each category's z-scores, signed by what a rise means for risk appetite.
        category_scores: dict[str, list[pd.Series]] = {}

        for inst in MACRO_UNIVERSE:
            if inst.symbol not in changes or inst.rising_means == "neutral":
                continue
            mean, std = stats[inst.symbol]
            if not std or std < 1e-9:
                continue

            z = ((changes[inst.symbol] - mean) / std).clip(-3.0, 3.0)
            # A risk-off instrument rising pushes the score down.
            signed = z * (1.0 if inst.rising_means == "risk_on" else -1.0)
            category_scores.setdefault(inst.category, []).append(signed * 6.0)

        if not category_scores:
            return []

        # Average within each category, then sum across them — the same
        # double-counting guard the live composite applies.
        total = sum(
            (sum(series) / len(series) for series in category_scores.values()),
            start=pd.Series(0.0, index=changes.index),
        )

        # Sector breadth: share of sectors advancing over the lookback, on the
        # same scale as the live calculation.
        sectors = [s for s in SECTOR_ETFS if s in changes]
        if sectors:
            breadth = (changes[sectors] > 0).sum(axis=1) / len(sectors) * 100.0
            total = total + (breadth - 50.0) / 5.0

        trace = (50.0 + total).clip(0.0, 100.0).dropna()
        if len(trace) < 2:
            return []

        return [round(float(v), 1) for v in trace.tail(30)]


macro_signal_service = MacroSignalService()
