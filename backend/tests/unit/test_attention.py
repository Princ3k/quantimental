"""
Tests for attention measurement and its archive.

The archive is the one asset here that cannot be bought or backfilled, so the
properties worth defending are about not corrupting it: a failed measurement
must never be recorded as silence, a partial sweep must not always fail on the
same tickers, and a stock must not set its own baseline from the day being
judged.
"""

from __future__ import annotations

import json
from datetime import date

import pytest

from app.services.scan import attention_archive as archive_mod
from app.services.scan.attention_service import _rotate
from app.services.scan.attention_archive import (
    MIN_HISTORY_FOR_BASELINE,
    attention_multiple,
    baseline,
    load,
    record,
)


@pytest.fixture
def archive_path(tmp_path):
    return tmp_path / "attention-history.json"


def _reading(velocity: float) -> dict:
    return {"velocity": velocity, "articles": 10, "span_hours": 24.0, "last_24h": 10}


class TestRecording:
    def test_first_run_creates_the_archive(self, archive_path):
        result = record({"AAPL": _reading(5.0)}, on="2026-09-10", path=archive_path)

        assert result["dates"] == ["2026-09-10"]
        assert result["velocity"]["AAPL"] == [5.0]
        assert archive_path.exists()

    def test_a_same_day_rerun_replaces_rather_than_appends(self, archive_path):
        # The scan runs several times a session; the archive holds one
        # observation per trading day, and the last run saw the most of it.
        record({"AAPL": _reading(5.0)}, on="2026-09-10", path=archive_path)
        result = record({"AAPL": _reading(9.0)}, on="2026-09-10", path=archive_path)

        assert result["dates"] == ["2026-09-10"]
        assert result["velocity"]["AAPL"] == [9.0]

    def test_an_unmeasured_ticker_is_null_not_zero(self, archive_path):
        # This is the one that would quietly poison every median: a stock we
        # failed to reach is not a stock nobody wrote about.
        record({"AAPL": _reading(5.0), "MSFT": _reading(3.0)}, on="2026-09-10", path=archive_path)
        result = record({"AAPL": _reading(6.0)}, on="2026-09-11", path=archive_path)

        assert result["velocity"]["MSFT"] == [3.0, None]

    def test_a_ticker_first_seen_later_is_backfilled_with_nulls(self, archive_path):
        record({"AAPL": _reading(5.0)}, on="2026-09-10", path=archive_path)
        result = record(
            {"AAPL": _reading(6.0), "NEWCO": _reading(1.0)},
            on="2026-09-11",
            path=archive_path,
        )

        # Every series must stay aligned to `dates` by position, or a lookup
        # reads the wrong day.
        assert result["velocity"]["NEWCO"] == [None, 1.0]
        assert len(result["velocity"]["NEWCO"]) == len(result["dates"])

    def test_history_is_capped(self, archive_path, monkeypatch):
        monkeypatch.setattr(archive_mod, "MAX_DAYS", 3)

        for day in range(1, 6):
            record({"AAPL": _reading(float(day))}, on=f"2026-09-0{day}", path=archive_path)

        result = load(archive_path)
        assert result["dates"] == ["2026-09-03", "2026-09-04", "2026-09-05"]
        assert result["velocity"]["AAPL"] == [3.0, 4.0, 5.0]

    def test_a_corrupt_archive_raises_rather_than_starting_over(self, archive_path):
        # Silently overwriting would destroy the only copy of data that cannot
        # be regenerated from any public source.
        archive_path.write_text("{not json")

        with pytest.raises(RuntimeError, match="unreadable"):
            load(archive_path)

    def test_the_file_stays_compact(self, archive_path):
        record({f"T{i}": _reading(1.23) for i in range(503)}, on="2026-09-10", path=archive_path)
        payload = json.loads(archive_path.read_text())

        assert len(payload["velocity"]) == 503
        # 503 tickers x 180 days must stay a file, not a database.
        assert archive_path.stat().st_size < 20_000


class TestBaseline:
    def _with_history(self, path, values, ticker="AAPL"):
        for index, value in enumerate(values):
            record({ticker: _reading(value)}, on=f"2026-{(index // 28) + 1:02d}-{(index % 28) + 1:02d}", path=path)
        return load(path)

    def test_no_baseline_until_there_is_enough_history(self, archive_path):
        # A median of four points is an anecdote, not a baseline. Saying "we
        # don't know yet" is the honest answer for the archive's first weeks.
        arc = self._with_history(archive_path, [5.0] * 5)
        assert baseline(arc, "AAPL") is None
        assert attention_multiple(arc, "AAPL", 50.0) is None

    def test_baseline_is_the_median_of_history(self, archive_path):
        arc = self._with_history(archive_path, [1.0] * 30)
        assert baseline(arc, "AAPL") == 1.0

    def test_today_is_excluded_from_its_own_baseline(self, archive_path):
        # Otherwise a spike partly normalises itself away and reads as less
        # unusual than it is — the same trap the price scan avoids.
        arc = self._with_history(archive_path, [1.0] * 30 + [100.0])
        assert baseline(arc, "AAPL") == 1.0

    def test_median_resists_a_single_earnings_spike(self, archive_path):
        # A mean would be dragged far enough by one 40x day that the next
        # genuine spike looks ordinary.
        arc = self._with_history(archive_path, [2.0] * 29 + [80.0])
        assert baseline(arc, "AAPL", exclude_last=False) == 2.0

    def test_multiple_reports_coverage_against_normal(self, archive_path):
        arc = self._with_history(archive_path, [4.0] * 30)
        assert attention_multiple(arc, "AAPL", 16.0) == 4.0

    def test_an_unknown_ticker_has_no_baseline(self, archive_path):
        arc = self._with_history(archive_path, [4.0] * 30)
        assert baseline(arc, "NOSUCH") is None


class TestArchiveLocation:
    """
    The archive is the only asset here that cannot be rebuilt from public
    sources, so it must not be written into the public repository — where git
    history would publish it permanently, even after a later move.
    """

    def test_the_path_is_configurable(self, monkeypatch, tmp_path):
        import importlib

        target = tmp_path / "elsewhere" / "attention-history.json"
        monkeypatch.setenv("ATTENTION_ARCHIVE_PATH", str(target))

        reloaded = importlib.reload(archive_mod)
        try:
            assert reloaded.ARCHIVE_PATH == target
        finally:
            monkeypatch.delenv("ATTENTION_ARCHIVE_PATH")
            importlib.reload(archive_mod)

    def test_it_falls_back_to_a_local_path_for_development(self, monkeypatch):
        import importlib

        monkeypatch.delenv("ATTENTION_ARCHIVE_PATH", raising=False)
        reloaded = importlib.reload(archive_mod)

        assert reloaded.ARCHIVE_PATH.name == "attention-history.json"

    def test_the_local_copy_is_gitignored(self):
        # The fallback path is a development convenience. If it were ever
        # committed, the whole point of the move would be undone.
        from pathlib import Path

        ignore = (Path(__file__).resolve().parents[2] / ".gitignore").read_text()
        assert "data/attention-history.json" in ignore


class TestRotation:
    def test_the_sweep_starts_somewhere_different_each_day(self):
        universe = [f"T{i}" for i in range(10)]
        first = _rotate(universe, "2026-09-10")
        second = _rotate(universe, "2026-09-11")

        assert first != second
        assert sorted(first) == sorted(universe)

    def test_a_shortfall_does_not_always_hit_the_same_tickers(self):
        # A fixed order means the alphabetical tail is dropped every time a
        # sweep is cut short, and those tickers never accumulate any history.
        universe = [f"T{i}" for i in range(10)]
        measured_first_half = set()
        for day in range(1, 9):
            measured_first_half.update(_rotate(universe, f"2026-09-0{day}")[:5])

        assert measured_first_half == set(universe)

    def test_rotation_is_deterministic(self):
        universe = [f"T{i}" for i in range(10)]
        assert _rotate(universe, "2026-09-10") == _rotate(universe, "2026-09-10")

    def test_handles_an_empty_universe(self):
        assert _rotate([], "2026-09-10") == []
