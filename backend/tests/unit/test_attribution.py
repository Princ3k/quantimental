"""
Tests for move attribution.

The claim being defended is narrow on purpose: not "this much was
company-specific risk" — which would need a beta estimate — but "the sector
moved this much and the stock moved that much", which a reader can check
against two other numbers on the same page.
"""

from __future__ import annotations

import pytest

from app.engines.attribution import (
    MIN_SECTOR_MEMBERS,
    decompose,
    explain,
)


def _rows(*specs) -> list[dict]:
    """(ticker, change_percent, typical_percent) triples."""
    return [
        {"ticker": t, "change_percent": c, "typical_percent": d}
        for t, c, d in specs
    ]


def _sectors(tickers, sector="Tech") -> dict[str, str]:
    return {t: sector for t in tickers}


class TestDecompose:
    def test_market_and_sector_are_medians_not_means(self):
        # One company halving on an earnings miss must not redefine what its
        # whole sector did that day.
        rows = _rows(*[(f"T{i}", 1.0, 2.0) for i in range(10)], ("CRASH", -60.0, 2.0))
        result = decompose(rows, _sectors([r["ticker"] for r in rows]))

        assert result["T0"]["market_percent"] == 1.0
        assert result["T0"]["sector_percent"] == 1.0

    def test_a_stock_moving_with_its_sector_is_not_a_divergence(self):
        rows = _rows(*[(f"T{i}", -3.0, 2.0) for i in range(10)], ("SAME", -3.2, 2.0))
        result = decompose(rows, _sectors([r["ticker"] for r in rows]))

        assert result["SAME"]["diverged"] is False

    def test_divergence_is_judged_against_the_stocks_own_range(self):
        # The same 2-point gap is noise for a volatile stock and a real
        # divergence for a calm one, which is the whole normalisation premise.
        peers = [(f"T{i}", 0.0, 2.0) for i in range(10)]
        rows = _rows(*peers, ("CALM", 2.0, 0.5), ("WILD", 2.0, 8.0))
        result = decompose(rows, _sectors([r["ticker"] for r in rows]))

        assert result["CALM"]["diverged"] is True
        assert result["WILD"]["diverged"] is False

    def test_sectors_too_small_to_summarise_are_omitted(self):
        # A median of four companies is not a sector.
        rows = _rows(*[(f"BIG{i}", 1.0, 2.0) for i in range(MIN_SECTOR_MEMBERS)],
                     *[(f"TINY{i}", 1.0, 2.0) for i in range(3)])
        sectors = {r["ticker"]: ("Big" if r["ticker"].startswith("BIG") else "Tiny")
                   for r in rows}

        result = decompose(rows, sectors)

        assert "BIG0" in result
        assert "TINY0" not in result

    def test_a_ticker_with_no_sector_is_omitted(self):
        rows = _rows(*[(f"T{i}", 1.0, 2.0) for i in range(10)], ("ORPHAN", 5.0, 2.0))
        sectors = _sectors([f"T{i}" for i in range(10)])

        assert "ORPHAN" not in decompose(rows, sectors)

    def test_no_measurements_yields_nothing(self):
        assert decompose([], {}) == {}


class TestExplain:
    def _attribution(self, **overrides):
        base = {
            "market_percent": -1.2,
            "sector": "Information Technology",
            "sector_percent": -3.1,
            "gap": -0.9,
            "diverged": False,
        }
        base.update(overrides)
        return base

    def test_a_market_wide_move_says_so(self):
        # The most useful thing this can tell someone: stop looking for a
        # company reason, there isn't one.
        sentence = explain("Nvidia", -4.0, self._attribution())

        assert "tracked the market rather than anything specific to Nvidia" in sentence
        assert "fell 1.2%" in sentence
        assert "fell 3.1%" in sentence

    def test_a_divergent_move_says_it_was_specific(self):
        sentence = explain("Nvidia", -8.0, self._attribution(gap=-4.9, diverged=True))
        assert "most of this was specific to Nvidia" in sentence

    def test_moving_against_the_sector_is_called_out(self):
        sentence = explain(
            "Nvidia", 3.0,
            self._attribution(sector_percent=-3.1, gap=6.1, diverged=True),
        )
        assert "moved against its sector" in sentence

    def test_states_both_numbers_so_the_reader_can_subtract(self):
        # Deliberately never phrased as "2.8% more than its sector": that
        # difference is in percentage points, and calling it a percentage would
        # be wrong in a way most readers would never catch.
        sentence = explain("Nvidia", -4.0, self._attribution(gap=-0.9, diverged=True))

        assert "more than its sector" not in sentence
        assert "fell 3.1%" in sentence

    def test_small_moves_are_flat_not_given_a_direction(self):
        sentence = explain("Nvidia", 0.1, self._attribution(market_percent=0.1, sector_percent=0.2))
        assert "was flat" in sentence

    def test_missing_attribution_yields_nothing(self):
        assert explain("Nvidia", -4.0, None) is None
