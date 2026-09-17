import json
import pathlib

import pytest

import store

from store import MAX_PER_GUILD, Watchlists, clean


@pytest.fixture
def lists(tmp_path):
    return Watchlists(tmp_path / "state.json")


class TestClean:
    def test_accepts_ordinary_symbols(self):
        assert clean("aapl") == "AAPL"
        assert clean("  nvda ") == "NVDA"
        assert clean("$TSLA") == "TSLA"
        assert clean("BRK.B") == "BRK.B"

    def test_rejects_digits(self):
        # US equity tickers are letters, optionally with a dot or dash. Nothing
        # in the covered universe has a digit, so a symbol carrying one is a
        # typo or an injection attempt, not a ticker.
        assert clean("AA1") == ""
        assert clean("2024") == ""

    def test_rejects_anything_that_is_not_one(self):
        # A ticker argument comes from a stranger in someone else's server.
        for bad in ("", "   ", "TOOLONGSYM", "AA PL", "'; DROP", "<script>", "12345"):
            assert clean(bad) == ""


class TestWatchlist:
    def test_add_remove_and_list(self, lists):
        assert lists.add(1, "aapl") == (True, "Watching AAPL.")
        assert lists.get(1) == ["AAPL"]
        assert lists.add(1, "AAPL")[0] is False
        assert lists.remove(1, "aapl")[0] is True
        assert lists.get(1) == []

    def test_the_cap_is_enforced(self, lists):
        # Letters only — clean() rejects digits, and no S&P 500 ticker has one.
        symbols = [f"AA{chr(ord('A') + i)}" for i in range(MAX_PER_GUILD)]
        for symbol in symbols:
            assert lists.add(1, symbol)[0] is True
        changed, message = lists.add(1, "ZZZZ")
        assert changed is False
        assert str(MAX_PER_GUILD) in message

    def test_guilds_are_separate(self, lists):
        lists.add(1, "AAPL")
        lists.add(2, "NVDA")
        assert lists.get(1) == ["AAPL"]
        assert lists.get(2) == ["NVDA"]


class TestScheduledPostState:
    def test_guilds_needs_both_a_list_and_a_channel(self, lists):
        lists.add(1, "AAPL")
        assert lists.guilds() == []          # nowhere to post yet
        lists.set_channel(1, 999)
        assert lists.guilds() == [1]

    def test_channel_and_posted_are_not_mistaken_for_guilds_or_tickers(self, lists):
        # The first version of this store kept "channel:1" and "posted:1" as
        # top-level keys beside the guild ids, so iterating it yielded channel
        # ids as guilds and stored dates as tickers.
        lists.add(1, "AAPL")
        lists.set_channel(1, 999)
        lists.mark_posted(1, "2026-09-17")
        assert lists.guilds() == [1]
        assert lists.every_ticker() == ["AAPL"]

    def test_every_ticker_deduplicates_across_guilds(self, lists):
        for gid in (1, 2, 3):
            lists.add(gid, "AAPL")
            lists.set_channel(gid, 100 + gid)
        lists.add(2, "NVDA")
        assert sorted(lists.every_ticker()) == ["AAPL", "NVDA"]


class TestPersistence:
    def test_state_survives_a_restart(self, tmp_path):
        path = tmp_path / "state.json"
        first = Watchlists(path)
        first.add(1, "AAPL")
        first.set_channel(1, 999)
        first.mark_posted(1, "2026-09-17")

        second = Watchlists(path)
        assert second.get(1) == ["AAPL"]
        assert second.channel(1) == 999
        assert second.get_posted(1) == "2026-09-17"

    def test_a_corrupt_file_is_kept_not_replaced(self, tmp_path):
        path = tmp_path / "state.json"
        path.write_text("{not json")
        lists = Watchlists(path)
        assert lists.guilds() == []
        # The unreadable file is still there to be recovered by hand.
        assert path.read_text() == "{not json"

    def test_the_write_is_atomic(self, tmp_path):
        path = tmp_path / "state.json"
        lists = Watchlists(path)
        lists.add(1, "AAPL")
        # No staging file left behind, and what landed is valid JSON.
        assert not list(tmp_path.glob(".*.tmp"))
        assert json.loads(path.read_text())["guilds"]["1"]["tickers"] == ["AAPL"]


class TestDurability:
    def test_the_volume_mount_supplies_the_default(self, monkeypatch):
        # Railway sets this itself when a volume is attached, so deriving the
        # default from it removes the chance of two settings disagreeing.
        monkeypatch.setenv("RAILWAY_VOLUME_MOUNT_PATH", "/mnt/state")
        import importlib
        import store as store_module
        importlib.reload(store_module)
        assert store_module.default_path() == pathlib.Path("/mnt/state/watchlists.json")

    def test_no_volume_is_reported_as_not_durable(self, monkeypatch, tmp_path, caplog):
        monkeypatch.delenv("RAILWAY_VOLUME_MOUNT_PATH", raising=False)
        with caplog.at_level("ERROR"):
            assert store.check_durability(tmp_path / "state.json") is False
        assert "lost on the next deploy" in caplog.text

    def test_a_path_outside_the_volume_is_reported(self, monkeypatch, tmp_path, caplog):
        # The failure that actually happened: a volume exists, but the state
        # file is written somewhere else on container storage.
        monkeypatch.setenv("RAILWAY_VOLUME_MOUNT_PATH", str(tmp_path / "volume"))
        (tmp_path / "volume").mkdir()
        with caplog.at_level("ERROR"):
            assert store.check_durability(tmp_path / "elsewhere.json") is False
        assert "not inside the mounted volume" in caplog.text

    def test_a_path_on_the_volume_is_durable(self, monkeypatch, tmp_path):
        monkeypatch.setenv("RAILWAY_VOLUME_MOUNT_PATH", str(tmp_path))
        assert store.check_durability(tmp_path / "watchlists.json") is True
