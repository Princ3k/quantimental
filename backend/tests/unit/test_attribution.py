"""
Tests for move attribution.

The claim being defended is narrow on purpose: not "this much was
company-specific risk" — which would need a beta estimate — but "the sector
moved this much and the stock moved that much", which a reader can check
against two other numbers on the same page.
"""

from __future__ import annotations

import pytest

from app.engines import attribution
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

    def test_a_name_ending_in_a_period_does_not_get_a_second_one(self):
        # Thirty of the 503 are "... Inc." or "... Corp.". Appending a period
        # to those rendered "specific to Apple Inc.." everywhere the sentence
        # was shown.
        for name in ("Apple Inc.", "Coherent Corp.", "Arthur J. Gallagher & Co."):
            market_wide = explain(name, -4.0, self._attribution())
            specific = explain(name, -8.0, self._attribution(gap=-4.9, diverged=True))
            for sentence in (market_wide, specific):
                assert sentence.endswith(".")
                assert not sentence.endswith("..")

    def test_a_name_without_one_still_gets_a_period(self):
        assert explain("Nvidia", -4.0, self._attribution()).endswith("Nvidia.")

    def test_a_divergent_move_says_it_was_specific(self):
        sentence = explain("Nvidia", -8.0, self._attribution(gap=-4.9, diverged=True))
        assert "most of this was specific to Nvidia" in sentence

    def test_a_flat_stock_in_a_moving_sector_is_described_as_not_following(self):
        # The generic wording got this wrong live: "most of this was specific
        # to Nvidia" about a 0.03% day. Not participating is the story.
        sentence = explain(
            "Nvidia", -0.03,
            self._attribution(market_percent=0.5, sector_percent=1.9, gap=-1.93, diverged=True),
        )

        assert "did not follow its sector" in sentence
        assert "most of this was specific" not in sentence

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


class TestBenchmarkBasket:
    """The market median must come from a named basket, not from whatever ran."""

    def _rows(self, moves):
        return [
            {"ticker": t, "change_percent": pct, "typical_percent": 2.0}
            for t, pct in moves
        ]

    def _benchmark_rows(self, n, pct):
        return [(f"BM{i:03d}", pct) for i in range(n)]

    def test_the_basket_defines_the_market_not_the_whole_scan(self):
        # 150 benchmark names flat, 400 small caps down 5%. "The market" is the
        # benchmark's answer, not the crowd's.
        rows = self._rows(
            self._benchmark_rows(150, 0.0) + [(f"SC{i:03d}", -5.0) for i in range(400)]
        )
        sectors = {r["ticker"]: "Information Technology" for r in rows}
        benchmark = {f"BM{i:03d}" for i in range(150)}

        result = attribution.decompose(rows, sectors, benchmark=benchmark)
        assert result["BM000"]["market_percent"] == 0.0

        # Without the basket, the same scan says the market fell 5%.
        unpinned = attribution.decompose(rows, sectors)
        assert unpinned["BM000"]["market_percent"] == -5.0

    def test_omitting_the_basket_keeps_the_old_behaviour(self):
        rows = self._rows(self._benchmark_rows(150, 1.0))
        sectors = {r["ticker"]: "Industrials" for r in rows}
        assert attribution.decompose(rows, sectors)["BM000"]["market_percent"] == 1.0

    def test_a_basket_too_thin_to_be_a_market_falls_back(self, caplog):
        # A median of eleven companies is worse than the whole scan, so the
        # fallback is deliberate — and says so rather than degrading quietly.
        rows = self._rows(
            [(f"BM{i:03d}", 0.0) for i in range(11)]
            + [(f"SC{i:03d}", -5.0) for i in range(400)]
        )
        sectors = {r["ticker"]: "Utilities" for r in rows}
        benchmark = {f"BM{i:03d}" for i in range(11)}

        with caplog.at_level("WARNING"):
            result = attribution.decompose(rows, sectors, benchmark=benchmark)
        assert result["BM000"]["market_percent"] == -5.0
        assert "falling back" in caplog.text

    def test_an_empty_basket_falls_back_without_complaint(self):
        # What an old universe.json with no flags produces. Correct today,
        # because the universe is exactly the benchmark.
        rows = self._rows(self._benchmark_rows(150, 0.5))
        sectors = {r["ticker"]: "Energy" for r in rows}
        assert attribution.decompose(rows, sectors, benchmark=set())["BM000"][
            "market_percent"
        ] == 0.5
