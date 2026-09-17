import json

import pytest

from misses import Misses, _tag


@pytest.fixture
def misses(tmp_path):
    return Misses(tmp_path / "misses.json")


class TestRecording:
    def test_counts_repeat_requests(self, misses):
        for _ in range(3):
            misses.record("KAZR", guild_id=1)
        assert misses.ranked()[0][1]["count"] == 3
        assert misses.total() == 3
        assert misses.distinct() == 1

    def test_normalises_the_symbol(self, misses):
        misses.record(" kazr ", guild_id=1)
        misses.record("KAZR", guild_id=1)
        assert misses.distinct() == 1

    def test_an_empty_ticker_is_ignored(self, misses):
        misses.record("", guild_id=1)
        misses.record("   ", guild_id=1)
        assert misses.distinct() == 0

    def test_distinct_servers_are_counted_once_each(self, misses):
        misses.record("KAZR", guild_id=1)
        misses.record("KAZR", guild_id=1)
        misses.record("KAZR", guild_id=2)
        assert len(misses.ranked()[0][1]["guilds"]) == 2


class TestPrivacy:
    def test_the_guild_id_is_not_stored(self, misses):
        misses.record("KAZR", guild_id=123456789)
        raw = misses.path.read_text()
        assert "123456789" not in raw

    def test_the_tag_is_stable_and_short(self):
        assert _tag(1) == _tag(1)
        assert _tag(1) != _tag(2)
        assert len(_tag(1)) == 8

    def test_no_guild_still_records_the_ticker(self, misses):
        # A DM or an interaction without a guild still tells us what was wanted.
        misses.record("KAZR", guild_id=None)
        assert misses.ranked()[0][0] == "KAZR"
        assert misses.ranked()[0][1]["guilds"] == []


class TestRanking:
    def test_breadth_outranks_volume(self, misses):
        # One person hammering a ticker is a person. Five servers asking once
        # each is a universe gap, and that is the thing being measured.
        for _ in range(50):
            misses.record("LOUD", guild_id=1)
        for guild in range(2, 7):
            misses.record("BROAD", guild_id=guild)
        assert misses.ranked()[0][0] == "BROAD"

    def test_the_limit_is_honoured(self, misses):
        for i in range(30):
            misses.record(f"AA{chr(65 + i % 26)}", guild_id=i)
        assert len(misses.ranked(limit=5)) == 5


class TestPersistence:
    def test_survives_a_restart(self, tmp_path):
        path = tmp_path / "misses.json"
        Misses(path).record("KAZR", guild_id=1)
        assert Misses(path).ranked()[0][1]["count"] == 1

    def test_a_corrupt_file_is_kept_not_replaced(self, tmp_path):
        path = tmp_path / "misses.json"
        path.write_text("{broken")
        assert Misses(path).distinct() == 0
        assert path.read_text() == "{broken"

    def test_the_write_is_atomic(self, tmp_path):
        path = tmp_path / "misses.json"
        Misses(path).record("KAZR", guild_id=1)
        assert not list(tmp_path.glob(".*.tmp"))
        assert "KAZR" in json.loads(path.read_text())["requests"]
