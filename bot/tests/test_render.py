from datetime import datetime, timedelta, timezone

import render
from client import Explanation


def row(ticker="AAPL", change=1.5, **over):
    payload = {
        "ticker": ticker,
        "company": "Apple Inc.",
        "as_of": "2026-09-17",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "explanation": f"{ticker} is up {change}% today.",
        "movement": {"price": 332.41, "change_percent": change, "change_percent_2w": 2.2},
        "attribution": {"text": "The market was flat today."},
        "coverage": {"articles_per_day": 58.6, "multiple_of_normal": None},
        "disclosure": "Descriptive only. Not investment advice, and not a forecast.",
    }
    payload.update(over)
    return Explanation.from_payload(payload)


class TestStaleNotice:
    def test_a_fresh_scan_gets_no_notice(self):
        assert render.stale_notice(datetime.now(timezone.utc).isoformat()) is None

    def test_an_old_scan_is_flagged(self):
        then = (datetime.now(timezone.utc) - timedelta(hours=9)).isoformat()
        assert "9 hours old" in render.stale_notice(then)

    def test_a_very_old_scan_is_reported_in_days(self):
        then = (datetime.now(timezone.utc) - timedelta(days=3)).isoformat()
        assert "3 days old" in render.stale_notice(then)


class TestOne:
    def test_carries_the_api_sentence_verbatim(self):
        e = row()
        assert render.one(e).description == e.explanation

    def test_renders_the_disclosure_from_the_response(self):
        assert "Not investment advice" in render.one(row()).footer.text

    def test_a_filing_is_shown_with_its_caveat_not_as_a_cause(self):
        e = row(filing={
            "items": ["2.02"],
            "reported": "results for the quarter",
            "url": "https://sec.gov/x",
            "note": "Filed on the same session. Same-day is adjacency, not cause.",
        })
        field = [f for f in render.one(e).fields if f.name == "SEC filing"][0]
        assert "adjacency, not cause" in field.value

    def test_coverage_omits_the_multiple_until_there_is_one(self):
        field = [f for f in render.one(row()).fields if f.name == "Coverage"][0]
        assert "59 articles/day" in field.value  # 58.6 rounds
        assert "its normal" not in field.value


class TestDigest:
    def test_orders_by_the_size_of_the_move(self):
        embed = render.digest(
            [row("AAPL", 0.3), row("NVDA", -4.1), row("CAT", 1.2)],
            as_of="2026-09-17",
            generated_at=datetime.now(timezone.utc).isoformat(),
        )
        lines = embed.description.splitlines()
        # Assert the order and the direction, not the markup — the tickers are
        # links now, and this test should not break again when they change.
        assert lines[0].startswith("▼") and "NVDA" in lines[0]
        assert lines[1].startswith("▲") and "CAT" in lines[1]
        assert "AAPL" in lines[2]

    def test_an_empty_watchlist_says_so_rather_than_rendering_blank(self):
        embed = render.digest([], as_of="2026-09-17", generated_at=None)
        assert "Nothing to report" in embed.description

    def test_uncovered_tickers_are_named_not_dropped(self):
        embed = render.digest(
            [row()], as_of="2026-09-17", generated_at=None, missing=["ZZZZ"]
        )
        assert "ZZZZ" in [f.value for f in embed.fields][0]


class TestUnusual:
    def _feed(self, movers=None, biggest=None):
        from client import Unusual
        return Unusual(
            as_of="2026-09-17",
            generated_at=datetime.now(timezone.utc).isoformat(),
            scanned=503,
            count=len(movers or []),
            movers=movers or [],
            biggest=biggest or [],
            threshold={"multiple": 2.0, "min_move_percent": 1.5},
            disclosure="Descriptive only. Not investment advice, and not a forecast.",
        )

    def test_uses_the_api_headline_verbatim(self):
        head = "Generac is up 17.6% today, 3.9x its typical 4.5% daily move."
        embed = render.unusual(self._feed([
            {"ticker": "GNRC", "direction": "up", "headline": head},
        ]))
        assert head in embed.description

    def test_states_the_threshold(self):
        # "Unusual" is a measured claim; the list cannot be judged without it.
        embed = render.unusual(self._feed([{"ticker": "GNRC", "direction": "up"}]))
        bar = [f for f in embed.fields if f.name == "What counts as unusual"][0]
        assert "2.0x" in bar.value and "1.5%" in bar.value and "503" in bar.value

    def test_a_quiet_day_says_nothing_qualified(self):
        embed = render.unusual(self._feed(movers=[], biggest=[
            {"ticker": "SMCI", "change_percent": 9.9, "multiple": 1.7, "typical_percent": 5.96},
        ]))
        assert "Nothing moved unusually" in embed.description

    def test_a_quiet_day_does_not_promote_the_largest_ordinary_move(self):
        # The failure to avoid: dressing the biggest ordinary move up as news
        # because the unusual list was empty.
        embed = render.unusual(self._feed(movers=[], biggest=[
            {"ticker": "SMCI", "change_percent": 9.9, "multiple": 1.7, "typical_percent": 5.96},
        ]))
        largest = [f for f in embed.fields if f.name == "Largest ordinary move"][0]
        assert "within its normal range" in largest.value


class TestDesk:
    def test_renders_the_published_narrative_and_score(self):
        embed = render.desk({
            "as_of": "2026-09-17T18:08:08+00:00",
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "composite": {"score": 37, "label": "Mixed"},
            "narrative": {"text": "The US dollar strengthened."},
            "signals": [
                {"text": "Dollar strengthening", "direction": "up", "delta": "+1.2%", "notable": True},
                {"text": "Quiet thing", "direction": "up", "delta": "+0.1%", "notable": False},
            ],
            "disclosure": "Descriptive only. Not investment advice, and not a forecast.",
        })
        assert embed.description == "The US dollar strengthened."
        assert "37" in [f for f in embed.fields if f.name == "Risk appetite"][0].value
        moved = [f for f in embed.fields if f.name == "What moved"][0]
        assert "Dollar strengthening" in moved.value
        assert "Quiet thing" not in moved.value   # only notable signals


class TestLinksBack:
    """Every embed is a way back to the site, not a dead end."""

    def test_the_stock_title_links_to_its_page(self):
        assert render.one(row()).url == "https://www.thequantimental.com/stock/aapl"

    def test_the_url_is_lower_cased_like_the_route(self):
        # generateStaticParams emits lower-cased tickers, so the lower-cased
        # path is the prerendered one. Upper case still resolves — the page
        # upper-cases the param itself — but it misses the static route and
        # renders on demand, and it is not the canonical URL the sitemap and
        # the og:image use.
        assert render.stock_url("AAPL").endswith("/stock/aapl")
        assert render.stock_url(" brk-b ").endswith("/stock/brk-b")

    def test_digest_tickers_are_links(self):
        embed = render.digest(
            [row("AAPL")], as_of="2026-09-17", generated_at=None
        )
        assert "[AAPL](https://www.thequantimental.com/stock/aapl)" in embed.description
        assert embed.url.endswith("/stocks")

    def test_unusual_tickers_are_links(self):
        from client import Unusual
        feed = Unusual(
            as_of="2026-09-17", generated_at=None, scanned=503, count=1,
            movers=[{"ticker": "GNRC", "direction": "up", "headline": "Generac is up."}],
            biggest=[], threshold={"multiple": 2.0, "min_move_percent": 1.5},
            disclosure="",
        )
        embed = render.unusual(feed)
        assert "[GNRC](https://www.thequantimental.com/stock/gnrc)" in embed.description

    def test_the_threshold_links_to_the_method_page(self):
        # The claim "unusual is measured, not asserted" is made good on /method.
        from client import Unusual
        feed = Unusual(
            as_of="2026-09-17", generated_at=None, scanned=503, count=0,
            movers=[], biggest=[], threshold={"multiple": 2.0, "min_move_percent": 1.5},
            disclosure="",
        )
        bar = [f for f in render.unusual(feed).fields if f.name == "What counts as unusual"][0]
        assert "https://www.thequantimental.com/method" in bar.value

    def test_the_site_is_overridable(self, monkeypatch):
        # So a staging deploy does not send people to production.
        monkeypatch.setenv("QUANTIMENTAL_SITE", "https://staging.example.com/")
        import importlib
        import render as render_module
        importlib.reload(render_module)
        assert render_module.stock_url("AAPL") == "https://staging.example.com/stock/aapl"
        monkeypatch.delenv("QUANTIMENTAL_SITE")
        importlib.reload(render_module)


class TestClosePost:
    def _unusual(self, movers):
        from client import Unusual
        return Unusual(
            as_of="2026-09-17", generated_at=datetime.now(timezone.utc).isoformat(),
            scanned=503, count=len(movers), movers=movers, biggest=[],
            threshold={"multiple": 2.0, "min_move_percent": 1.5}, disclosure="",
        )

    MOVER = {"ticker": "GNRC", "direction": "up",
             "headline": "Generac is up 17.9% today, 4.0x its typical 4.5% daily move."}
    FILING = {"ticker": "AIG", "items": ["5.02"],
              "reported": "a change among its directors", "url": "https://sec.gov/x"}

    def _names(self, embed):
        return [f.name for f in embed.fields]

    def test_nothing_at_all_posts_nothing(self):
        # A daily post saying nothing happened is how a channel learns to
        # ignore the bot.
        assert render.close_post(
            [], as_of="2026-09-17", generated_at=None,
            unusual_feed=self._unusual([]), filings=[],
        ) is None

    def test_a_server_with_no_watchlist_still_gets_the_market(self):
        # The zero-configuration path: only /watch here was ever run.
        embed = render.close_post(
            [], as_of="2026-09-17", generated_at=None,
            unusual_feed=self._unusual([self.MOVER]), filings=[self.FILING],
        )
        assert embed is not None
        assert self._names(embed) == ["Moved unusually", "Filed an 8-K (1)"]

    def test_sections_appear_only_when_they_have_something(self):
        embed = render.close_post(
            [], as_of="2026-09-17", generated_at=None,
            unusual_feed=self._unusual([self.MOVER]), filings=[],
        )
        assert self._names(embed) == ["Moved unusually"]

    def test_all_three_sections_in_order(self):
        embed = render.close_post(
            [row("AAPL")], as_of="2026-09-17", generated_at=None,
            unusual_feed=self._unusual([self.MOVER]), filings=[self.FILING],
        )
        assert self._names(embed) == ["Moved unusually", "Filed an 8-K (1)", "Your watchlist"]

    def test_the_watchlist_is_still_ordered_by_size_of_move(self):
        embed = render.close_post(
            [row("AAPL", 0.3), row("NVDA", -4.1)], as_of="2026-09-17",
            generated_at=None, unusual_feed=self._unusual([]), filings=[],
        )
        lines = [f for f in embed.fields if f.name == "Your watchlist"][0].value.splitlines()
        assert "NVDA" in lines[0] and "AAPL" in lines[1]

    def test_the_adjacency_caveat_rides_with_the_filings(self):
        embed = render.close_post(
            [], as_of="2026-09-17", generated_at=None,
            unusual_feed=self._unusual([]), filings=[self.FILING],
        )
        block = [f for f in embed.fields if f.name.startswith("Filed")][0].value
        assert "adjacency, not cause" in block
        # Once for the block, not once per line.
        assert block.count("adjacency, not cause") == 1

    def test_filings_link_to_edgar_and_to_the_stock_page(self):
        embed = render.close_post(
            [], as_of="2026-09-17", generated_at=None,
            unusual_feed=self._unusual([]), filings=[self.FILING],
        )
        block = [f for f in embed.fields if f.name.startswith("Filed")][0].value
        assert "https://sec.gov/x" in block
        assert "https://www.thequantimental.com/stock/aig" in block

    def test_a_filing_without_a_url_is_still_shown(self):
        embed = render.close_post(
            [], as_of="2026-09-17", generated_at=None,
            unusual_feed=self._unusual([]),
            filings=[{"ticker": "AWK", "items": ["8.01"], "reported": "another event"}],
        )
        assert "AWK" in [f for f in embed.fields if f.name.startswith("Filed")][0].value

    def test_the_disclosure_is_present_even_with_no_watchlist(self):
        # It normally comes off an Explanation; there is not one here.
        embed = render.close_post(
            [], as_of="2026-09-17", generated_at=None,
            unusual_feed=self._unusual([self.MOVER]), filings=[],
        )
        assert "not a forecast" in embed.footer.text


class TestDiscordLimits:
    """Over a field limit Discord rejects the whole embed, not just the field."""

    def _long_filings(self, n):
        return [{
            "ticker": f"AA{chr(65 + i % 26)}",
            "items": ["1.01", "2.03", "8.01"],
            "reported": "reporting a material definitive agreement",
            "url": f"https://www.sec.gov/Archives/edgar/data/{i}23554/00016282802606{i}267/x-2026091{i}.htm",
        } for i in range(n)]

    def _unusual(self, movers):
        from client import Unusual
        return Unusual(as_of="2026-09-17", generated_at=None, scanned=503,
                       count=len(movers), movers=movers, biggest=[],
                       threshold={}, disclosure="")

    def test_fit_keeps_whole_lines_only(self):
        # A truncated markdown link renders as raw text; a truncated URL is a
        # broken one. Lines are dropped whole or not at all.
        out = render._fit([f"[AAA](https://example.com/{'x' * 80})" for _ in range(40)])
        assert len(out) <= render.FIELD_LIMIT
        for line in out.splitlines():
            assert line.startswith("[AAA](https://") or line.startswith("_+")

    def test_a_long_filing_block_stays_under_the_limit(self):
        # Six real filings with EDGAR URLs came to 1221 characters live.
        embed = render.close_post(
            [], as_of="2026-09-17", generated_at=None,
            unusual_feed=self._unusual([]), filings=self._long_filings(12),
        )
        block = [f for f in embed.fields if f.name.startswith("Filed")][0]
        assert len(block.value) <= render.FIELD_LIMIT
        assert "more_" in block.value            # says what it left out

    def test_the_caveat_survives_truncation(self):
        # It must travel with the facts even when some facts are dropped.
        embed = render.close_post(
            [], as_of="2026-09-17", generated_at=None,
            unusual_feed=self._unusual([]), filings=self._long_filings(12),
        )
        block = [f for f in embed.fields if f.name.startswith("Filed")][0].value
        assert "adjacency, not cause" in block

    def test_the_header_count_reports_all_of_them_not_the_shown_ones(self):
        embed = render.close_post(
            [], as_of="2026-09-17", generated_at=None,
            unusual_feed=self._unusual([]), filings=self._long_filings(12),
        )
        assert [f for f in embed.fields if f.name.startswith("Filed")][0].name == "Filed an 8-K (12)"

    def test_a_full_watchlist_stays_under_the_limit(self):
        # MAX_PER_GUILD is 25, and 25 sentences with links exceed 1024.
        embed = render.close_post(
            [row(f"AA{chr(65 + i)}", 1.5) for i in range(25)],
            as_of="2026-09-17", generated_at=None,
            unusual_feed=self._unusual([]), filings=[],
        )
        block = [f for f in embed.fields if f.name == "Your watchlist"][0]
        assert len(block.value) <= render.FIELD_LIMIT

    def test_everything_fits_the_whole_embed_budget(self):
        embed = render.close_post(
            [row(f"AA{chr(65 + i)}", 1.5) for i in range(25)],
            as_of="2026-09-17", generated_at=None,
            unusual_feed=self._unusual([
                {"ticker": f"BB{chr(65 + i)}", "direction": "up",
                 "headline": "x" * 90} for i in range(8)
            ]),
            filings=self._long_filings(12),
        )
        total = (len(embed.title or "") + len(embed.footer.text or "")
                 + sum(len(f.name) + len(f.value) for f in embed.fields))
        assert total <= 6000
