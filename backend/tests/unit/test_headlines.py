"""
What the coverage says, not just how much of it there is.

These exist because the attention multiple is structurally blind to the
stories that matter most. Velocity is ten articles over the span they cover,
so it saturates at 240/day; NVDA's own baseline *is* 240, which makes its
maximum possible multiple 1.00x. On 2026-11-12, the day its CEO resigned, it
read 216 — an ordinary Thursday — and on the 13th it read 169, which the
snapshot published as `vx 0.7`, below normal. Thirteen other names, GOOG,
MSFT, META and AMZN among them, cannot reach 3.0x either.

A headline is not a better counter. It is the part of the answer the counter
was never going to give.
"""

from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone

import pytest

from app.services.scan import headline_store
from app.services.scan import attention_service as service_mod
from app.services.scan.attention_service import _article_entries, measure_one


def _epoch_article(hours_ago: float, title: str, publisher: str = "Reuters") -> dict:
    when = datetime.now(timezone.utc) - timedelta(hours=hours_ago)
    return {
        "providerPublishTime": str(int(when.timestamp())),
        "title": title,
        "publisher": publisher,
    }


def _nested_article(hours_ago: float, title: str, publisher: str = "WIRED") -> dict:
    when = datetime.now(timezone.utc) - timedelta(hours=hours_ago)
    return {
        "content": {
            "pubDate": when.isoformat(),
            "title": title,
            "provider": {"displayName": publisher},
        }
    }


class TestReadingWhatTheArticlesSay:
    def test_titles_and_sources_are_read_from_both_yahoo_shapes(self):
        entries = _article_entries(
            [_epoch_article(1, "Flat shape"), _nested_article(2, "Nested shape")]
        )

        assert [e["title"] for e in entries] == ["Flat shape", "Nested shape"]
        assert [e["publisher"] for e in entries] == ["Reuters", "WIRED"]

    def test_an_undated_article_is_still_dropped(self):
        # The timestamp rule does not relax because a title is now wanted:
        # velocity is computed from these and a guessed time would corrupt it.
        entries = _article_entries(
            [_epoch_article(1, "Dated"), {"title": "Undated"}]
        )

        assert [e["title"] for e in entries] == ["Dated"]

    def test_an_untitled_article_is_counted_but_not_quotable(self):
        # Missing title is not fatal the way a missing time is — the article
        # still happened, it just cannot be shown to anyone.
        entries = _article_entries([_epoch_article(1, ""), _epoch_article(2, "Real")])

        assert len(entries) == 2
        assert [e["title"] for e in entries if e["title"]] == ["Real"]


class TestTheHeadlineMeasureOneReturns:
    def test_it_is_the_newest_one(self, monkeypatch):
        monkeypatch.setattr(
            service_mod, "_fetch_news",
            lambda t: [
                _epoch_article(9, "Older story"),
                _epoch_article(1, "Breaking story"),
                _epoch_article(5, "Middle story"),
            ],
        )
        result = measure_one("NVDA")

        assert result["headline"]["title"] == "Breaking story"
        assert result["headline"]["publisher"] == "Reuters"

    def test_a_saturated_stock_still_gets_one(self, monkeypatch):
        # The case this whole feature exists for. Ten articles inside an hour
        # is NVDA's every single day: the span clamps to MIN_SPAN_HOURS, the
        # velocity pins to the 240/day ceiling, and the multiple cannot move.
        # The headline is unaffected by any of that.
        monkeypatch.setattr(
            service_mod, "_fetch_news",
            lambda t: [_epoch_article(h / 60.0, f"Story {h}") for h in range(1, 11)],
        )
        result = measure_one("NVDA")

        assert result["velocity"] == 240.0, "expected the saturated ceiling"
        assert result["headline"]["title"] == "Story 1"

    def test_no_titles_anywhere_is_none_not_an_empty_string(self, monkeypatch):
        monkeypatch.setattr(
            service_mod, "_fetch_news",
            lambda t: [_epoch_article(1, ""), _epoch_article(5, "")],
        )
        result = measure_one("AAPL")

        assert result is not None, "untitled articles are still a measurement"
        assert result["headline"] is None


class TestTheStore:
    def test_a_sweep_replaces_rather_than_merges(self, tmp_path):
        path = tmp_path / "headlines.json"
        headline_store.save({"AAPL": {"title": "Monday", "publisher": "A", "at": "x"}},
                            on="2026-11-12", path=path)
        headline_store.save({"MSFT": {"title": "Tuesday", "publisher": "B", "at": "y"}},
                            on="2026-11-13", path=path)

        stored = json.loads(path.read_text())
        # Last week's headline presented as today's is worse than none.
        assert stored["headlines"] == {
            "MSFT": {"title": "Tuesday", "publisher": "B", "at": "y"}
        }
        assert stored["as_of"] == "2026-11-13"

    def test_an_empty_sweep_does_not_wipe_the_store(self, tmp_path):
        # Same rule the attention archive follows: a sweep that found nothing
        # is a broken sweep, not a silent news day — and seven scans read this.
        path = tmp_path / "headlines.json"
        headline_store.save({"AAPL": {"title": "Real", "publisher": "A", "at": "x"}},
                            on="2026-11-13", path=path)
        headline_store.save({}, on="2026-11-14", path=path)

        assert headline_store.load(path)["headlines"]["AAPL"]["title"] == "Real"

    def test_a_missing_store_is_empty_not_an_error(self, tmp_path):
        assert headline_store.load(tmp_path / "nope.json") == {
            "as_of": None, "headlines": {}
        }

    def test_a_corrupt_store_costs_the_headlines_and_nothing_else(self, tmp_path):
        path = tmp_path / "headlines.json"
        path.write_text("{not json")

        assert headline_store.load(path)["headlines"] == {}

    def test_an_overlong_title_is_trimmed_and_marked(self, tmp_path):
        path = tmp_path / "headlines.json"
        headline_store.save(
            {"X": {"title": "word " * 100, "publisher": "A", "at": "x"}},
            on="2026-11-13", path=path,
        )

        title = headline_store.load(path)["headlines"]["X"]["title"]
        assert len(title) <= headline_store.MAX_TITLE_CHARS
        assert title.endswith("…")
