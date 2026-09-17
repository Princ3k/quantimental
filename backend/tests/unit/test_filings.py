"""
Tests for 8-K ingestion.

The item mapping is the part with judgement in it, so most of these are about
what a filing is allowed to say. Nothing here reaches EDGAR.
"""

from __future__ import annotations

import json
import os
from datetime import date, timedelta

import pytest

from app.services.ingestion.filings import cik_map, filing_fetcher, items


class TestItems:
    def test_a_filing_is_described_by_its_leading_item(self):
        assert items.describe(["2.02"]) == "reporting quarterly results"

    def test_exhibit_housekeeping_is_not_an_explanation(self):
        # 9.01 is the exhibit index. It rides along with other items and was the
        # most frequent item in two years of measurement, so including it would
        # have made it the most common thing the site said.
        assert items.describe(["9.01"]) is None
        assert items.meaningful(["2.02", "9.01"]) == ["2.02"]

    def test_the_more_notable_item_leads(self):
        # Earnings arrive four times a year on a known schedule; an officer
        # leaving does not.
        assert items.describe(["2.02", "5.02"]) == (
            "reporting a change among its directors or senior officers"
        )
        assert items.describe(["7.01", "2.02"]) == "reporting quarterly results"

    def test_a_restatement_outranks_everything_it_travels_with(self):
        assert items.describe(["4.02", "2.02", "7.01"]) == (
            "reporting that earlier financial statements cannot be relied on"
        )

    def test_unknown_items_are_ignored_rather_than_guessed(self):
        assert items.describe(["6.04"]) is None
        assert items.describe(["6.04", "2.02"]) == "reporting quarterly results"

    def test_no_phrase_claims_the_filing_moved_the_price(self):
        # The product does not assert causation anywhere, and this is the
        # feature most likely to smuggle it in.
        banned = ("caused", "because", "drove", "sent", "pushed", "on the news",
                  "led to", "triggered", "sparked", "due to")
        for code, phrase in items.ITEM_PHRASES.items():
            lowered = phrase.lower()
            for word in banned:
                assert word not in lowered, f"{code}: {phrase!r}"

    def test_no_phrase_forecasts(self):
        banned = ("will ", "expect", "should ", "likely", "poised", "set to")
        for code, phrase in items.ITEM_PHRASES.items():
            for word in banned:
                assert word not in phrase.lower(), f"{code}: {phrase!r}"

    def test_every_prioritised_item_has_a_phrase(self):
        assert set(items.ITEM_PRIORITY) == set(items.ITEM_PHRASES)


class TestSessionAssignment:
    def test_a_filing_before_the_close_belongs_to_that_day(self):
        # 13:14 UTC is 09:14 ET, before the open.
        assert filing_fetcher._session_of("2026-09-11T13:14:40.000Z") == date(2026, 9, 11)

    def test_a_filing_after_the_close_belongs_to_the_next_session(self):
        # 20:16 UTC is 16:16 ET. Oracle's results landed here, and counting
        # them against the 10th would put earnings on a session that closed
        # before they existed.
        assert filing_fetcher._session_of("2026-09-10T20:16:50.000Z") == date(2026, 9, 11)

    def test_the_boundary_is_the_close_itself(self):
        assert filing_fetcher._session_of("2026-09-10T19:59:00.000Z") == date(2026, 9, 10)
        assert filing_fetcher._session_of("2026-09-10T20:00:00.000Z") == date(2026, 9, 11)

    def test_a_weekend_filing_belongs_to_monday(self):
        # Saturday the 12th of September 2026.
        assert filing_fetcher._session_of("2026-09-12T14:00:00.000Z") == date(2026, 9, 14)

    def test_a_friday_evening_filing_belongs_to_monday(self):
        assert filing_fetcher._session_of("2026-09-11T21:00:00.000Z") == date(2026, 9, 14)

    def test_an_unparseable_timestamp_is_none_not_today(self):
        assert filing_fetcher._session_of("not a date") is None


class TestIndexParsing:
    ROW = (
        "8-K              ACADIA PHARMACEUTICALS INC                       "
        "             1070494     20260911    edgar/data/1070494/0001193125-26-389400.txt"
    )

    def test_a_company_name_with_spaces_still_parses(self):
        match = filing_fetcher._INDEX_ROW.match(self.ROW)
        assert match and match.group(1) == "8-K"
        assert match.group(2) == "ACADIA PHARMACEUTICALS INC"
        assert int(match.group(3)) == 1070494

    def test_other_forms_are_not_8ks(self, monkeypatch):
        body = self.ROW + "\n" + self.ROW.replace("8-K  ", "10-Q ", 1)
        monkeypatch.setattr(filing_fetcher, "get_text", lambda *a, **k: body)
        assert filing_fetcher.filers_on(date(2026, 9, 11)) == {1070494}

    def test_a_closed_market_has_no_index_and_that_is_not_an_error(self, monkeypatch):
        def missing(*a, **k):
            raise RuntimeError("404")

        monkeypatch.setattr(filing_fetcher, "get_text", missing)
        assert filing_fetcher.filers_on(date(2026, 9, 12)) == set()


class TestDegradation:
    def test_a_bad_session_date_yields_nothing(self):
        assert filing_fetcher.filings_for_session(["AAPL"], "not-a-date") == {}

    def test_no_cik_map_means_no_filings_not_a_crash(self, monkeypatch):
        # The scan is the product; filings decorate it. EDGAR being unreachable
        # must never be a reason the price data fails to publish.
        def boom(*a, **k):
            raise RuntimeError("edgar down")

        monkeypatch.setattr(filing_fetcher.cik_map, "ciks_for", boom)
        assert filing_fetcher.filings_for_session(["AAPL"], "2026-09-11") == {}


class TestFilingRow:
    def test_the_snapshot_form_is_compact(self):
        filing = filing_fetcher.Filing(
            ticker="ORCL", items=["2.02"], phrase="reporting quarterly results",
            accepted_at="2026-09-10T20:16:50.000Z", session="2026-09-11",
            url="https://www.sec.gov/Archives/edgar/data/1341439/x/orcl.htm",
        )
        assert filing.as_row() == {
            "i": ["2.02"], "p": "reporting quarterly results",
            "a": "2026-09-10T20:16:50.000Z",
            "u": "https://www.sec.gov/Archives/edgar/data/1341439/x/orcl.htm",
        }

    def test_the_document_url_drops_the_dashes_edgar_omits(self):
        recent = {
            "accessionNumber": ["0001193125-26-389400"],
            "primaryDocument": ["dell-20260910.htm"],
        }
        assert filing_fetcher._document_url(1571996, recent, 0) == (
            "https://www.sec.gov/Archives/edgar/data/1571996/"
            "000119312526389400/dell-20260910.htm"
        )

    def test_a_filing_with_no_primary_document_has_no_url(self):
        recent = {"accessionNumber": ["0001193125-26-389400"], "primaryDocument": [""]}
        assert filing_fetcher._document_url(1571996, recent, 0) is None


class TestMissingIndex:
    def test_an_unpublished_index_is_not_a_block(self, monkeypatch):
        # EDGAR answers 403, not 404, for a dated index file that does not
        # exist — and the current day's is never published while that day is
        # still accepting filings. Treating that as "we are blocked" aborted
        # the whole sweep, including the previous day where the after-close
        # filings actually are. That is why the first real run attached zero.
        def refuse(*a, **k):
            raise filing_fetcher.EdgarBlocked("EDGAR refused ...")

        monkeypatch.setattr(filing_fetcher, "get_text", refuse)
        assert filing_fetcher.filers_on(date(2026, 9, 14)) == set()

    def test_a_flagged_ticker_is_checked_with_no_index_at_all(self, monkeypatch):
        # The gap the index cannot cover: a company filing for the first time
        # today, on a day whose index does not exist yet.
        monkeypatch.setattr(filing_fetcher, "get_text",
                            lambda *a, **k: (_ for _ in ()).throw(RuntimeError("no index")))
        monkeypatch.setattr(filing_fetcher.cik_map, "ciks_for", lambda t: {"DELL": 1571996})

        looked_up = []

        def fake_company(ticker, cik, session, client):
            looked_up.append(ticker)
            return filing_fetcher.Filing(
                ticker=ticker, items=["8.01"], phrase="reporting another event",
                accepted_at="2026-09-14T12:00:00.000Z", session=session.isoformat(),
            )

        monkeypatch.setattr(filing_fetcher, "_filings_for_company", fake_company)
        found = filing_fetcher.filings_for_session(
            ["DELL"], "2026-09-14", always_check=["DELL"]
        )

        assert looked_up == ["DELL"]
        assert "DELL" in found

    def test_nothing_indexed_and_nothing_flagged_is_simply_empty(self, monkeypatch):
        monkeypatch.setattr(filing_fetcher, "get_text",
                            lambda *a, **k: (_ for _ in ()).throw(RuntimeError("no index")))
        monkeypatch.setattr(filing_fetcher.cik_map, "ciks_for", lambda t: {"DELL": 1571996})
        assert filing_fetcher.filings_for_session(["DELL"], "2026-09-14") == {}


class TestCikMap:
    """
    The map is an input, not a cache.

    It used to decide its own freshness from the file's mtime, which is always
    "just written" under CI because actions/checkout sets mtime to checkout
    time. The monthly refresh it promised therefore never happened once.
    """

    @pytest.fixture
    def map_path(self, tmp_path, monkeypatch):
        path = tmp_path / "cik-map.json"
        monkeypatch.setattr(cik_map, "CACHE_PATH", path)
        cik_map.reset_cache()
        return path

    def _write(self, path, captured, ciks=None):
        path.write_text(json.dumps({
            "source": "x", "captured": captured,
            "count": 1, "ciks": ciks or {"AAPL": 320193},
        }))

    def test_age_comes_from_the_file_not_its_mtime(self, map_path, monkeypatch):
        # The bug, encoded. A checkout makes every file look newly written;
        # only a date inside it survives that.
        self._write(map_path, (date.today() - timedelta(days=400)).isoformat())
        os.utime(map_path, None)  # exactly what checkout does

        warned = []
        monkeypatch.setattr(cik_map.logger, "warning", lambda m, *a: warned.append(m % a if a else m))
        cik_map.load()

        assert any("days old" in w for w in warned)

    def test_a_recent_map_loads_without_complaint(self, map_path, monkeypatch):
        self._write(map_path, date.today().isoformat())

        warned = []
        monkeypatch.setattr(cik_map.logger, "warning", lambda m, *a: warned.append(m))
        assert cik_map.load() == {"AAPL": 320193}
        assert warned == []

    def test_the_older_flat_shape_still_loads(self, map_path, monkeypatch):
        # The first version of the file was a bare {ticker: cik} object.
        map_path.write_text(json.dumps({"AAPL": 320193}))

        warned = []
        monkeypatch.setattr(cik_map.logger, "warning", lambda m, *a: warned.append(m))
        assert cik_map.load() == {"AAPL": 320193}
        assert any("no capture date" in w for w in warned)

    def test_it_does_not_refetch_on_a_stale_map(self, map_path, monkeypatch):
        # Stale is a reason to warn, not to pull 800KB from the SEC on every
        # scan of the day to arrive at the same answer.
        self._write(map_path, (date.today() - timedelta(days=400)).isoformat())
        monkeypatch.setattr(cik_map, "write", lambda *a, **k: pytest.fail("refetched"))
        monkeypatch.setattr(cik_map.logger, "warning", lambda *a: None)

        assert cik_map.load() == {"AAPL": 320193}

    def test_class_share_tickers_resolve_through_the_dash_spelling(self, map_path):
        # EDGAR writes BRK-B where the price feed says BRK.B. Missing those
        # would be a silent hole rather than an error.
        self._write(map_path, date.today().isoformat(), {"BRK-B": 1067983})
        assert cik_map.cik_for("BRK.B") == 1067983
