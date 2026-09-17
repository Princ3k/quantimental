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
        assert lines[0].startswith("▼ **NVDA**")
        assert lines[1].startswith("▲ **CAT**")

    def test_an_empty_watchlist_says_so_rather_than_rendering_blank(self):
        embed = render.digest([], as_of="2026-09-17", generated_at=None)
        assert "Nothing to report" in embed.description

    def test_uncovered_tickers_are_named_not_dropped(self):
        embed = render.digest(
            [row()], as_of="2026-09-17", generated_at=None, missing=["ZZZZ"]
        )
        assert "ZZZZ" in [f.value for f in embed.fields][0]
