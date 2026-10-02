"""
Tests for the published snapshot's coverage figures.

These exist because of a specific outage. On 2026-09-26 GitHub started the
post-close cron 2h24m late, after the external dispatcher had already swept on
time. The second sweep measured nothing, and the `--attention` branch — unlike
the hourly one — had no fallback, so it published a snapshot with no `v` on any
of 503 rows. Being the last publish before the weekend, that snapshot stayed
live for two days and /ops read `0 / 503` the whole time.

Nothing in the suite touched this script before, which is why a branch with no
fallback looked fine. Two properties are defended here, one per failure:

  * a run that fails to measure coverage must never remove coverage that an
    earlier run measured, and
  * a session the archive already holds must not be measured again, however late
    the trigger that asked for it arrives.
"""

from __future__ import annotations

import json

import pytest

from scripts import publish_unusual as pu

AS_OF = "2026-09-25"

# Nothing recorded for AS_OF yet: the ordinary state of a post-close run, and
# the one in which a sweep is genuinely needed. MSFT's trailing None is a
# ticker that was missed on the most recent day it appeared.
NOT_YET_SWEPT = {
    "dates": ["2026-09-23", "2026-09-24"],
    "velocity": {"AAPL": [7.0, 8.0], "MSFT": [2.0, None]},
}

# AS_OF already measured, for every ticker in the universe.
ALREADY_SWEPT = {
    "dates": ["2026-09-24", AS_OF],
    "velocity": {"AAPL": [7.0, 8.0], "MSFT": [1.0, 2.0], "ZZZ": [9.0, 9.5]},
}

# AS_OF recorded, but only a fraction of it — a sweep the limiter cut off, which
# is the case where measuring again is worth the budget.
SWEPT_PARTIALLY = {
    "dates": ["2026-09-24", AS_OF],
    "velocity": {"AAPL": [7.0, 8.0], "MSFT": [1.0, None], "ZZZ": [9.0, None]},
}


def _rows() -> list[dict]:
    # ZZZ has no history in NOT_YET_SWEPT: it is the case where carrying forward
    # is not possible, and zeroing would be a lie rather than a gap.
    return [
        {"t": "AAPL", "n": "Apple", "c": 1.0},
        {"t": "MSFT", "n": "Microsoft", "c": -0.5},
        {"t": "ZZZ", "n": "Newly Listed", "c": 0.2},
    ]


def _reading(velocity: float) -> dict:
    return {"velocity": velocity, "articles": 10, "span_hours": 24.0}


@pytest.fixture
def published(tmp_path, monkeypatch):
    """Run main() against stubbed inputs and hand back the snapshot it wrote."""

    def _run(
        measured: dict[str, dict],
        archive: dict = NOT_YET_SWEPT,
        flags: tuple[str, ...] = ("--attention",),
    ):
        out = tmp_path / "unusual.json"
        swept: list[list[str]] = []

        monkeypatch.setattr(pu.sys, "argv", ["publish_unusual.py", str(out), *flags])
        monkeypatch.setattr(pu, "scan", lambda: {
            "available": True,
            "scanned": 3,
            "universe": 3,
            "as_of": AS_OF,
            "generated_at": "2026-09-26T00:08:49+00:00",
            "unusual_count": 0,
            "rising": 0,
            "falling": 0,
            "movers": [],
            "snapshot": _rows(),
        })

        def fake_measure(tickers, on=None):
            swept.append(list(tickers))
            return measured

        monkeypatch.setattr(pu, "measure_attention", fake_measure)

        def fake_load(window=None, **kwargs):
            # Truncates like the real one, so a test cannot pass on a shape the
            # script will never actually be handed.
            copy = json.loads(json.dumps(archive))
            if window is not None and len(copy["dates"]) > window:
                copy["dates"] = copy["dates"][-window:]
                for ticker, series in copy["velocity"].items():
                    copy["velocity"][ticker] = series[-window:]
            return copy

        monkeypatch.setattr(pu.attention_archive, "load", fake_load)
        monkeypatch.setattr(
            pu.attention_archive,
            "record",
            lambda m, on=None: json.loads(json.dumps(archive)),
        )
        # The multiple is computed elsewhere and tested there; here it only has
        # to be present so `vx` travels with `v`.
        monkeypatch.setattr(
            pu.attention_archive, "attention_multiple", lambda archive, ticker, v: 1.5
        )

        assert pu.main() == 0

        snapshot = json.loads((tmp_path / "snapshot.json").read_text())
        return snapshot, {row["t"]: row for row in snapshot["stocks"]}, swept

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
        snapshot, _, _ = published(measured={})

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

    def test_a_complete_sweep_takes_nothing_from_the_archive(self, published):
        # A full sweep's numbers are today's, and nothing older should be able to
        # displace them.
        _, rows, _ = published(
            measured={
                "AAPL": _reading(20.0),
                "MSFT": _reading(30.0),
                "ZZZ": _reading(40.0),
            }
        )

        assert [rows[t]["v"] for t in ("AAPL", "MSFT", "ZZZ")] == [20.0, 30.0, 40.0]

    def test_the_hourly_run_still_carries_coverage_forward(self, published):
        # The branch that always had a fallback must keep it.
        _, rows, _ = published(measured={}, flags=())

        assert rows["AAPL"]["v"] == 8.0
        assert rows["MSFT"]["v"] == 2.0


class TestTheSessionIsSweptOnce:
    def test_a_session_already_in_the_archive_is_not_swept_again(self, published):
        # The second half of the outage: deduplicating on which cron fired cannot
        # catch a cron GitHub starts 2h24m late. Asking the archive can.
        _, _, swept = published(measured={}, archive=ALREADY_SWEPT)

        assert swept == []

    def test_skipping_the_sweep_still_publishes_full_coverage(self, published):
        # The skip has to be invisible in the output — the carry-forward reads
        # this session's own readings back out of the archive.
        snapshot, rows, _ = published(measured={}, archive=ALREADY_SWEPT)

        assert [rows[t]["v"] for t in ("AAPL", "MSFT", "ZZZ")] == [8.0, 2.0, 9.5]
        assert len([r for r in snapshot["stocks"] if r.get("v") is not None]) == 3

    def test_a_session_swept_only_partly_is_swept_again(self, published):
        # A sweep the limiter cut off is exactly when the budget is worth
        # spending twice, so the guard must not lock in a bad reading.
        _, rows, swept = published(
            measured={"AAPL": _reading(20.0), "MSFT": _reading(30.0), "ZZZ": _reading(40.0)},
            archive=SWEPT_PARTIALLY,
        )

        assert swept == [["AAPL", "MSFT", "ZZZ"]]
        assert [rows[t]["v"] for t in ("AAPL", "MSFT", "ZZZ")] == [20.0, 30.0, 40.0]

    def test_an_hourly_run_never_sweeps_whatever_the_archive_holds(self, published):
        _, _, swept = published(measured={}, archive=NOT_YET_SWEPT, flags=())

        assert swept == []


class TestTheMeasuredCountIsPublished:
    """
    The snapshot has to say how much of a session a sweep actually reached.

    Without it the two cases are indistinguishable from outside: a sweep that
    measured all 503 and a sweep that measured 300 both publish a snapshot with
    `v` on ~503 rows, because the carry-forward fills the rest from the archive.
    That is the whole reason a half-reaching sweep went unnoticed.
    """

    def test_a_complete_sweep_publishes_its_count_and_session(self, published):
        snapshot, _, _ = published(
            measured={
                "AAPL": _reading(20.0),
                "MSFT": _reading(30.0),
                "ZZZ": _reading(40.0),
            },
            archive=ALREADY_SWEPT,
        )

        assert snapshot["coverage_measured"] == 3
        assert snapshot["coverage_measured_on"] == AS_OF

    def test_a_partial_session_publishes_the_smaller_count(self, published):
        # SWEPT_PARTIALLY holds AS_OF with one of three tickers measured. The
        # count has to show 1, not the 3 that `v` will report once the
        # carry-forward has done its work.
        snapshot, rows, _ = published(measured={}, archive=SWEPT_PARTIALLY)

        assert snapshot["coverage_measured"] == 1
        with_v = len([r for r in snapshot["stocks"] if r.get("v") is not None])
        assert with_v == 3, "carry-forward should still fill the rows"

    def test_the_two_counts_disagree_and_that_is_the_point(self, published):
        # Stated as its own test because the gap between them is the signal.
        snapshot, _, _ = published(measured={}, archive=SWEPT_PARTIALLY)

        assert snapshot["coverage_measured"] == 1
        assert snapshot["count"] == 3

    def test_an_unmeasured_session_names_the_one_it_can_speak_for(self, published):
        # For most of a trading day the sweep has not run, so the newest measured
        # session is the previous one. Reporting the date alongside the count is
        # what stops the page reading that normal state as a fault.
        snapshot, _, _ = published(measured={}, archive=NOT_YET_SWEPT)

        assert snapshot["as_of"] == AS_OF
        assert snapshot["coverage_measured_on"] == "2026-09-24"
        assert snapshot["coverage_measured"] == 1

    def test_an_unreadable_archive_publishes_nothing_rather_than_zero(self, published):
        # Zero would read as "the sweep measured nothing", which is a different
        # and much louder claim than "we could not find out".
        snapshot, _, _ = published(measured={}, archive={"dates": [], "velocity": {}})

        assert snapshot["coverage_measured"] is None
        assert snapshot["coverage_measured_on"] is None
