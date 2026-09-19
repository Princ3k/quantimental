import json

import pytest

import personal
from personal import MAX_PER_PERSON, Personal, tag


@pytest.fixture
def lists(tmp_path):
    return Personal(tmp_path / "personal.json")


class TestIdentity:
    def test_the_discord_id_is_never_written_down(self):
        # The whole basis of the privacy claim for this feature.
        uid = 987654321098765432
        assert str(uid) not in tag(uid)

    def test_a_full_digest_is_used_not_a_short_one(self):
        # misses.json truncates to 8 chars because it only counts servers and a
        # collision is harmless. A collision here would hand one person another
        # person's watchlist.
        assert len(tag(1)) == 64

    def test_the_same_person_resolves_to_the_same_list(self):
        assert tag(42) == tag(42)
        assert tag(42) != tag(43)

    def test_the_file_contains_no_raw_ids(self, lists):
        lists.add(987654321098765432, "AAPL")
        raw = lists.path.read_text()
        assert "987654321098765432" not in raw
        assert "AAPL" in raw


class TestList:
    def test_add_and_read_back(self, lists):
        assert lists.add(1, "aapl") == (True, "Added AAPL to your list.")
        assert lists.get(1) == ["AAPL"]

    def test_duplicates_are_refused(self, lists):
        lists.add(1, "AAPL")
        assert lists.add(1, "aapl")[0] is False

    def test_rubbish_is_refused(self, lists):
        assert lists.add(1, "'; DROP")[0] is False
        assert lists.get(1) == []

    def test_the_cap_is_enforced(self, lists):
        for i in range(MAX_PER_PERSON):
            assert lists.add(1, f"AA{chr(65 + i)}")[0] is True
        changed, message = lists.add(1, "ZZZZ")
        assert changed is False and str(MAX_PER_PERSON) in message

    def test_two_people_do_not_see_each_other(self, lists):
        lists.add(1, "AAPL")
        lists.add(2, "NVDA")
        assert lists.get(1) == ["AAPL"]
        assert lists.get(2) == ["NVDA"]


class TestDeletion:
    def test_clear_removes_everything(self, lists):
        lists.add(1, "AAPL")
        assert lists.clear(1) is True
        assert lists.get(1) == []
        assert lists.people() == 0

    def test_clearing_nothing_is_harmless(self, lists):
        assert lists.clear(999) is False

    def test_removing_the_last_ticker_removes_the_row_entirely(self, lists):
        # Leaving an empty row behind would keep a record that this person had
        # used the bot, which is more than the privacy page says is kept.
        lists.add(1, "AAPL")
        lists.remove(1, "AAPL")
        assert lists.people() == 0
        assert tag(1) not in lists.path.read_text()

    def test_deletion_reaches_the_file(self, tmp_path):
        path = tmp_path / "personal.json"
        first = Personal(path)
        first.add(1, "AAPL")
        first.clear(1)
        assert Personal(path).get(1) == []


class TestPersistence:
    def test_survives_a_restart(self, tmp_path):
        path = tmp_path / "personal.json"
        Personal(path).add(1, "AAPL")
        assert Personal(path).get(1) == ["AAPL"]

    def test_a_corrupt_file_is_kept_not_replaced(self, tmp_path):
        path = tmp_path / "personal.json"
        path.write_text("{broken")
        assert Personal(path).people() == 0
        assert path.read_text() == "{broken"

    def test_the_write_is_atomic(self, tmp_path):
        path = tmp_path / "personal.json"
        Personal(path).add(1, "AAPL")
        assert not list(tmp_path.glob(".*.tmp"))
        assert json.loads(path.read_text())["lists"]

    def test_the_volume_mount_supplies_the_default(self, monkeypatch):
        import importlib
        monkeypatch.setenv("RAILWAY_VOLUME_MOUNT_PATH", "/mnt/state")
        importlib.reload(personal)
        assert personal.default_path().as_posix() == "/mnt/state/personal.json"
        monkeypatch.delenv("RAILWAY_VOLUME_MOUNT_PATH")
        importlib.reload(personal)
