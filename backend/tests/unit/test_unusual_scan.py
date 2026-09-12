"""
Tests for the unusual-movement scan.

The scan's whole value rests on one claim: that "unusual" means unusual *for
that stock*. A percentage leaderboard would surface the same volatile tickers
every day and be worthless as a reason to come back, so most of these tests
exist to keep the normalisation honest.
"""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from app.services.scan import unusual_service
from app.services.scan.unusual_service import (
    MIN_ABSOLUTE_MOVE_PCT,
    UNUSUAL_MULTIPLE,
    _measure,
    load_universe,
    scan,
)


def _frame(closes: list[float], span_pct: float = 1.0) -> pd.DataFrame:
    """Daily bars with a controlled high/low span, so ATR is predictable."""
    closes_arr = np.array(closes, dtype=float)
    spans = closes_arr * span_pct / 100.0
    return pd.DataFrame({
        "Open": closes_arr,
        "High": closes_arr + spans / 2,
        "Low": closes_arr - spans / 2,
        "Close": closes_arr,
        "Volume": np.full(len(closes_arr), 1_000_000),
    })


class TestMeasure:
    def test_normalises_the_move_against_the_stocks_own_range(self):
        # Flat at 100 with a 1% daily span, then a 4% jump. That is roughly
        # four times normal for this stock.
        frame = _frame([100.0] * 30 + [104.0], span_pct=1.0)
        move = _measure("TEST", frame)

        assert move is not None
        assert move["change_percent"] == pytest.approx(4.0, abs=0.01)
        assert move["typical_percent"] == pytest.approx(1.0, abs=0.1)
        assert move["multiple"] == pytest.approx(4.0, abs=0.2)
        assert move["direction"] == "up"

    def test_the_same_percentage_move_is_unusual_for_one_stock_and_not_another(self):
        # This is the entire premise. A 4% day on a calm stock is remarkable;
        # on a stock that swings 6% routinely it is a Tuesday.
        calm = _measure("CALM", _frame([100.0] * 30 + [104.0], span_pct=1.0))
        wild = _measure("WILD", _frame([100.0] * 30 + [104.0], span_pct=6.0))

        assert calm["multiple"] > UNUSUAL_MULTIPLE
        assert wild["multiple"] < UNUSUAL_MULTIPLE

    def test_the_move_being_judged_is_excluded_from_what_counts_as_normal(self):
        # If today's huge range were folded into the average, a big day would
        # partly normalise itself away and read as less unusual than it is.
        frame = _frame([100.0] * 30, span_pct=1.0)
        frame.loc[len(frame)] = {
            "Open": 100.0, "High": 130.0, "Low": 100.0,
            "Close": 130.0, "Volume": 1_000_000,
        }
        move = _measure("TEST", frame)

        assert move["typical_percent"] == pytest.approx(1.0, abs=0.1)
        assert move["multiple"] > 25

    def test_too_little_history_returns_nothing(self):
        assert _measure("TEST", _frame([100.0] * 5)) is None

    def test_a_flat_range_returns_nothing_rather_than_dividing_by_zero(self):
        # A zero ATR would make every move infinitely unusual.
        frame = _frame([100.0] * 31, span_pct=0.0)
        assert _measure("TEST", frame) is None

    def test_penny_stocks_are_skipped(self):
        # Tiny absolute moves produce enormous percentages on cheap stocks.
        frame = _frame([0.40] * 30 + [0.55], span_pct=1.0)
        assert _measure("TEST", frame) is None

    def test_missing_closes_are_dropped_before_measuring(self):
        # Yahoo emits a row for the current session as soon as it opens, with
        # volume but a NaN close.
        frame = _frame([100.0] * 30 + [104.0], span_pct=1.0)
        frame.loc[len(frame)] = {
            "Open": 104.0, "High": 104.0, "Low": 104.0,
            "Close": np.nan, "Volume": 10,
        }
        move = _measure("TEST", frame)

        assert move is not None
        assert move["change_percent"] == pytest.approx(4.0, abs=0.01)


class TestScan:
    def _patched_download(self, monkeypatch, frames: dict[str, pd.DataFrame]):
        combined = pd.concat(frames, axis=1)
        combined.index = pd.date_range("2026-08-01", periods=len(next(iter(frames.values()))))
        monkeypatch.setattr(unusual_service.yf, "download", lambda *a, **k: combined)

    def test_reports_only_the_stocks_that_cleared_the_bar(self, monkeypatch):
        self._patched_download(monkeypatch, {
            "CALM": _frame([100.0] * 30 + [104.0], span_pct=1.0),   # ~4x
            "WILD": _frame([100.0] * 30 + [104.0], span_pct=6.0),   # <1x
        })

        result = scan([
            {"ticker": "CALM", "name": "Calm Co", "sector": "Utilities"},
            {"ticker": "WILD", "name": "Wild Inc", "sector": "Biotech"},
        ])

        assert result["available"] is True
        assert result["scanned"] == 2
        assert [m["ticker"] for m in result["movers"]] == ["CALM"]
        assert "Calm Co is up 4.0% today" in result["movers"][0]["headline"]

    def test_biggest_is_populated_even_when_nothing_is_unusual(self, monkeypatch):
        # A calm day must still leave the page with something to show, without
        # calling an ordinary move remarkable.
        self._patched_download(monkeypatch, {
            "WILD": _frame([100.0] * 30 + [104.0], span_pct=6.0),
        })

        result = scan([{"ticker": "WILD", "name": "Wild Inc", "sector": "Biotech"}])

        assert result["unusual_count"] == 0
        assert result["movers"] == []
        assert [m["ticker"] for m in result["biggest"]] == ["WILD"]
        assert result["biggest"][0]["company"] == "Wild Inc"

    def test_a_tiny_move_is_not_unusual_however_calm_the_stock(self, monkeypatch):
        # A stock that normally moves 0.05% having a 0.4% day is technically
        # 8x normal, and telling anyone about it would be absurd.
        self._patched_download(monkeypatch, {
            "SLEEPY": _frame([100.0] * 30 + [100.4], span_pct=0.05),
        })

        result = scan([{"ticker": "SLEEPY", "name": "Sleepy Co", "sector": "Utilities"}])

        assert result["movers"] == []
        assert MIN_ABSOLUTE_MOVE_PCT > 0.4

    def test_a_failed_download_is_reported_not_raised(self, monkeypatch):
        def boom(*args, **kwargs):
            raise RuntimeError("network down")

        monkeypatch.setattr(unusual_service.yf, "download", boom)
        result = scan([{"ticker": "X", "name": "X", "sector": ""}])

        assert result["available"] is False
        assert "network down" in result["reason"]

    def test_movers_are_ordered_by_how_unusual_not_by_size(self, monkeypatch):
        self._patched_download(monkeypatch, {
            "BIG": _frame([100.0] * 30 + [112.0], span_pct=5.0),   # +12%, ~2.4x
            "ODD": _frame([100.0] * 30 + [105.0], span_pct=0.6),   # +5%,  ~8x
        })

        result = scan([
            {"ticker": "BIG", "name": "Big Move", "sector": ""},
            {"ticker": "ODD", "name": "Odd Move", "sector": ""},
        ])

        # The smaller percentage move is the more remarkable one.
        assert [m["ticker"] for m in result["movers"]] == ["ODD", "BIG"]
        assert [m["ticker"] for m in result["biggest"]] == ["BIG", "ODD"]


class TestUniverse:
    def test_the_shipped_universe_is_usable(self):
        constituents = load_universe()

        assert len(constituents) > 400
        assert all(c["ticker"] and c["name"] for c in constituents)
        # Yahoo spells class shares with a hyphen; a dot returns no data at all
        # and would silently drop those names from every scan.
        assert not any("." in c["ticker"] for c in constituents)
