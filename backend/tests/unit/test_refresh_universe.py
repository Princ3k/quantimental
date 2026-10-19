"""
The universe refresh, specifically what it does to tickers it did not add.

refresh_universe.py rewrites data/universe.json wholesale from the S&P 500
list. Coverage of anything outside that index therefore depends entirely on
this script carrying those rows over — and a failure here is silent, arrives
weeks later, and shows up only as the scan quietly covering less than it did
the day before.
"""

from __future__ import annotations

import importlib.util
import json
from pathlib import Path

import pytest

SCRIPT = Path(__file__).resolve().parents[2] / "scripts" / "refresh_universe.py"


@pytest.fixture(scope="module")
def refresh():
    spec = importlib.util.spec_from_file_location("refresh_universe", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _universe(path: Path, rows: list[dict]) -> Path:
    path.write_text(json.dumps({"constituents": rows}))
    return path


class TestCarryingOverAdditions:
    def test_a_ticker_from_outside_the_index_survives_a_refresh(self, refresh, tmp_path):
        path = _universe(tmp_path / "universe.json", [
            {"ticker": "AAPL", "name": "Apple", "sector": "IT", "benchmark": True},
            {"ticker": "ASML", "name": "ASML Holding", "sector": "IT"},
        ])

        kept = refresh._non_benchmark_rows(path, {"AAPL"})

        assert [row["ticker"] for row in kept] == ["ASML"]

    def test_a_company_that_joins_the_index_is_not_listed_twice(self, refresh, tmp_path):
        # It stops being an addition and becomes a constituent. Keeping both
        # would scan it twice and count it twice in every median.
        path = _universe(tmp_path / "universe.json", [
            {"ticker": "SHOP", "name": "Shopify", "sector": "IT"},
        ])

        assert refresh._non_benchmark_rows(path, {"SHOP"}) == []

    def test_index_members_are_not_carried_over(self, refresh, tmp_path):
        # They come from the freshly parsed table. Carrying the old row too
        # would resurrect a company that has left the index.
        path = _universe(tmp_path / "universe.json", [
            {"ticker": "GONE", "name": "Removed Co", "sector": "IT", "benchmark": True},
        ])

        assert refresh._non_benchmark_rows(path, {"AAPL"}) == []

    def test_a_first_run_has_nothing_to_carry(self, refresh, tmp_path):
        assert refresh._non_benchmark_rows(tmp_path / "absent.json", {"AAPL"}) == []

    def test_an_unreadable_file_loses_additions_rather_than_blocking_the_refresh(
        self, refresh, tmp_path, caplog
    ):
        # Refusing would make a corrupt universe unfixable by the one script
        # meant to rewrite it. The lesser harm, said out loud.
        path = tmp_path / "universe.json"
        path.write_text("{not json")

        assert refresh._non_benchmark_rows(path, {"AAPL"}) == []
        assert "additions not carried over" in caplog.text
