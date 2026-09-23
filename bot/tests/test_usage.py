import json
from datetime import datetime, timedelta, timezone

import pytest

import usage
from usage import Usage, _tag


@pytest.fixture
def counts(tmp_path):
    return Usage(tmp_path / "usage.json")


def day(offset=0):
    return (datetime.now(timezone.utc).date() + timedelta(days=offset)).isoformat()


class TestPrivacy:
    def test_the_digest_changes_every_day(self):
        # The property the whole design rests on: counting people today must
        # not make it possible to follow one of them to tomorrow.
        assert _tag("2026-09-22", 42) != _tag("2026-09-23", 42)

    def test_it_is_stable_within_a_day(self):
        assert _tag("2026-09-22", 42) == _tag("2026-09-22", 42)

    def test_two_people_differ(self):
        assert _tag("2026-09-22", 42) != _tag("2026-09-22", 43)

    def test_no_raw_id_reaches_the_file(self, counts):
        counts.record("stock", user_id=987654321098765432, guild_id=123456789, tickers=["AAPL"])
        raw = counts.path.read_text()
        assert "987654321098765432" not in raw
        assert "123456789" not in raw
        assert "AAPL" in raw

    def test_no_link_between_a_person_and_a_ticker(self, counts):
        counts.record("stock", user_id=1, tickers=["AAPL"])
        counts.record("stock", user_id=2, tickers=["NVDA"])
        bucket = json.loads(counts.path.read_text())["days"][day()]
        # People and tickers are separate piles. Nothing pairs them.
        assert set(bucket) <= {"commands", "people", "servers", "tickers"}
        assert bucket["tickers"] == {"AAPL": 1, "NVDA": 1}
        assert len(bucket["people"]) == 2


class TestCounting:
    def test_commands_are_counted(self, counts):
        counts.record("stock", user_id=1)
        counts.record("stock", user_id=1)
        counts.record("unusual", user_id=1)
        s = counts.summary()
        assert s["commands"] == {"stock": 2, "unusual": 1}
        assert s["total_commands"] == 3

    def test_one_person_is_counted_once_a_day(self, counts):
        for _ in range(5):
            counts.record("stock", user_id=7)
        assert counts.summary()["today"]["people"] == 1

    def test_tickers_are_ranked_by_frequency(self, counts):
        for _ in range(3):
            counts.record("stock", user_id=1, tickers=["AAPL"])
        counts.record("stock", user_id=1, tickers=["NVDA"])
        assert list(counts.summary()["tickers"]) == ["AAPL", "NVDA"]

    def test_a_command_with_no_ticker_still_counts(self, counts):
        counts.record("unusual", user_id=1)
        assert counts.summary()["tickers"] == {}
        assert counts.summary()["total_commands"] == 1

    def test_returning_visitors_are_counted_again_not_deduplicated(self, counts):
        # Person-days, not people. Calling it anything else would claim we can
        # tell the two apart, and by design we cannot.
        counts.record("stock", user_id=7, day=day(-1))
        counts.record("stock", user_id=7, day=day(0))
        assert counts.summary(days=7)["person_days"] == 2


class TestTrend:
    def test_daily_counts_come_back_in_order(self, counts):
        counts.record("stock", user_id=1, day=day(-2))
        counts.record("stock", user_id=1, day=day(0))
        rows = counts.daily_counts(days=7)
        assert [r[0] for r in rows] == sorted(r[0] for r in rows)
        assert rows[-1][0] == day(0)

    def test_the_window_excludes_older_days(self, counts):
        counts.record("stock", user_id=1, day=day(-30))
        counts.record("stock", user_id=1, day=day(0))
        assert counts.summary(days=7)["total_commands"] == 1


class TestPersistence:
    def test_survives_a_restart(self, tmp_path):
        path = tmp_path / "usage.json"
        Usage(path).record("stock", user_id=1, tickers=["AAPL"])
        assert Usage(path).summary()["total_commands"] == 1

    def test_old_days_are_pruned(self, counts, monkeypatch):
        counts.record("stock", user_id=1, day=day(-200))
        counts.record("stock", user_id=1, day=day(0))
        # The prune runs on write, so the ancient day is gone from the file.
        assert day(-200) not in json.loads(counts.path.read_text())["days"]

    def test_a_corrupt_file_is_kept_not_replaced(self, tmp_path):
        path = tmp_path / "usage.json"
        path.write_text("{broken")
        assert Usage(path).summary()["total_commands"] == 0
        assert path.read_text() == "{broken"

    def test_the_write_is_atomic(self, tmp_path):
        path = tmp_path / "usage.json"
        Usage(path).record("stock", user_id=1)
        assert not list(tmp_path.glob(".*.tmp"))
        assert json.loads(path.read_text())["days"]
