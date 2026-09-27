"""
Tests for the published snapshot's coverage figures.

These exist because of a specific outage. On 2026-09-26 GitHub started the
post-close cron 2h24m late, after the external dispatcher had already swept on
time. The second sweep measured nothing, and the `--attention` branch — unlike
the hourly one — had no fallback, so it published a snapshot with no `v` on any
of 503 rows. Being the last publish before the weekend, that snapshot stayed
live for two days and /ops read `0 / 503` the whole time.

Nothing in the suite touched this script before, which is why a branch with no
fallback looked fine. The property being defended is narrow and worth stating
plainly: **a run that fails to measure coverage must never remove coverage that
an earlier run measured.**
"""

from __future__ import annotations

import json

import pytest

from scripts import publish_unusual as pu


def _rows() -> list[dict]:
    # ZZZ has no archive history: it is the case where carrying forward is not
    # possible, and zeroing would be a lie rather than a gap.
    return [
        {"t": "AAPL", "n": "Apple", "c": 1.0},
        {"t": "MSFT", "n": "Microsoft", "c": -0.5},
        {"t": "ZZZ", "n": "Newly Listed", "c": 0.2},
    ]


def _reading(velocity: float) -> dict:
    return {"velocity": velocity, "articles": 10, "span_hours": 24.0}


ARCHIVE = {
    "dates": ["2026-09-24", "2026-09-25"],
    "velocity": {"AAPL": [7.0, 8.0], "MSFT": [2.0, None]},
}


@pytest.fixture
def published(tmp_path, monkeypatch):
    """Run main() against stubbed inputs and hand back the snapshot it wrote."""

    def _run(measured: dict[str, dict], flags: tuple[str, ...] = ("--attention",)):
        out = tmp_path / "unusual.json"

        monkeypatch.setattr(pu.sys, "argv", ["publish_unusual.py", str(out), *flags])
        monkeypatch.setattr(pu, "scan", lambda: {
            "available": True,
            "scanned": 3,
            "universe": 3,
            "as_of": "2026-09-25",
            "generated_at": "2026-09-26T00:08:49+00:00",
            "unusual_count": 0,
            "rising": 0,
            "falling": 0,
            "movers": [],
            "snapshot": _rows(),
        })
        monkeypatch.setattr(pu, "measure_attention", lambda tickers, on=None: measured)

        loads: list[dict] = []

        def fake_load(window=None, **kwargs):
            loads.append({"window": window})
            return json.loads(json.dumps(ARCHIVE))

        monkeypatch.setattr(pu.attention_archive, "load", fake_load)
        monkeypatch.setattr(
            pu.attention_archive, "record", lambda m, on=None: json.loads(json.dumps(ARCHIVE))
        )
        # The multiple is computed elsewhere and tested there; here it only has
        # to be present so `vx` travels with `v`.
        monkeypatch.setattr(
            pu.attention_archive, "attention_multiple", lambda archive, ticker, v: 1.5
        )

        assert pu.main() == 0

        snapshot = json.loads((tmp_path / "snapshot.json").read_text())
        return snapshot, {row["t"]: row for row in snapshot["stocks"]}, loads

    return _run


class TestCoverageSurvivesAFailedSweep:
    def test_a_sweep_that_measured_nothing_keeps_the_last_reading(self, published):
        # The regression. Before the fix this published 0 of 3 rows with `v`.
        _, rows, _ = published(measured={})

        assert rows["AAPL"]["v"] == 8.0
        assert rows["MSFT"]["v"] == 2.0

    def test_the_published_count_matches_what_ops_reports(self, published):
        # /ops counts rows carrying `v`, and that count is the alarm that caught
        # the outage. It has to be able to go back to full without a good sweep.
        snapshot, rows, _ = published(measured={})

        with_coverage = [r for r in snapshot["stocks"] if r.get("v") is not None]
        assert len(with_coverage) == 2
        assert snapshot["count"] == 3

    def test_a_partial_sweep_fills_only_the_gaps(self, published):
        # measure_attention omits tickers it could not reach rather than zeroing
        # them, so a missing row means "we failed to look" — and today's reading
        # must still win wherever there is one.
        _, rows, _ = published(measured={"AAPL": _reading(20.0)})

        assert rows["AAPL"]["v"] == 20.0
        assert rows["MSFT"]["v"] == 2.0

    def test_a_ticker_with_no_history_is_left_uncovered(self, published):
        # Absent, not zero. A stock nobody has ever measured and a stock nobody
        # is writing about are different facts.
        _, rows, _ = published(measured={})

        assert "v" not in rows["ZZZ"]

    def test_a_complete_sweep_does_not_read_the_archive_for_coverage(self, published):
        # Cheapness matters less than the guarantee: a full sweep's numbers are
        # today's, and nothing from the archive should be able to displace them.
        _, rows, loads = published(
            measured={
                "AAPL": _reading(20.0),
                "MSFT": _reading(30.0),
                "ZZZ": _reading(40.0),
            }
        )

        assert [rows[t]["v"] for t in ("AAPL", "MSFT", "ZZZ")] == [20.0, 30.0, 40.0]
        # The carry-forward read is the windowed one; `_archive_days` reads
        # unwindowed. Only the first should be absent.
        assert [load for load in loads if load["window"] is not None] == []

    def test_the_hourly_run_still_carries_coverage_forward(self, published):
        # The branch that always had a fallback must keep it.
        _, rows, _ = published(measured={}, flags=())

        assert rows["AAPL"]["v"] == 8.0
        assert rows["MSFT"]["v"] == 2.0
