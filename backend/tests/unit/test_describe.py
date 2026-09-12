"""
Tests for the descriptive engine.

The product's claim changed here: from "you should buy this" to "this is what
happened". These tests exist mostly to keep the second claim honest — that
every sentence is checkable, that nothing is forecast, and that absent data is
reported as absent rather than as a zero.
"""

from __future__ import annotations

import pytest

from app.engines.describe import describe


def _indicators(**overrides):
    base = {
        "price": 100.0,
        "price_change_10d": 0.0,
        "atr_percent": 2.0,
        "trend": "sideways",
        "volatility": "moderate",
        "golden_cross": False,
        "death_cross": False,
        "bollinger_upper": 110.0,
        "bollinger_lower": 90.0,
    }
    base.update(overrides)
    return base


class TestHeadline:
    def test_agreement_between_today_and_the_period_reads_as_and(self):
        result = describe("Apple", 1.5, _indicators(price_change_10d=6.0))
        assert result["headline"] == (
            "Apple is up 1.5% today, and up 6.0% over the past two weeks."
        )

    def test_disagreement_reads_as_but(self):
        # "down today but up over two weeks" is a different situation from
        # "down today and down over two weeks", and the conjunction is what
        # carries that distinction at a glance.
        result = describe("Apple", -1.5, _indicators(price_change_10d=6.0))
        assert "down 1.5% today, but up 6.0%" in result["headline"]

    def test_a_quiet_stock_is_described_as_quiet(self):
        result = describe("Coca-Cola", 0.1, _indicators(price_change_10d=0.2))
        assert result["headline"] == (
            "Coca-Cola is little changed today, and has moved sideways "
            "over the past two weeks."
        )

    def test_a_flat_period_does_not_claim_a_direction(self):
        result = describe("Apple", 3.0, _indicators(price_change_10d=0.1))
        assert "little changed over the past two weeks" in result["headline"]

    def test_makes_no_forecast(self):
        # The whole point of the reframe. If any of these words appear, the
        # engine has started making claims it cannot support.
        forecast_words = (
            "expect", "likely", "should", "will ", "poised", "set to",
            "predict", "forecast", "target", "upside", "downside",
        )
        for change, period in [(5.0, 10.0), (-5.0, -10.0), (0.0, 0.0), (-3.0, 4.0)]:
            result = describe("Apple", change, _indicators(price_change_10d=period))
            text = " ".join([result["headline"], *result["notable"]]).lower()
            for word in forecast_words:
                assert word not in text, f"forecast language {word!r} in: {text}"


class TestNoForecastAnywhere:
    """
    The no-forecast rule has to cover every engine that writes copy, not just
    this one. It did not: `quant.explain()` shipped "so expect a bumpier ride"
    on every stock page, in a product whose central claim is that it does not
    forecast — while describe.py's own test passed.
    """

    FORECAST_WORDS = (
        "expect", "likely", "should ", "will ", "poised", "set to",
        "predict", "forecast", "upside", "downside", "tend to", "tended to",
    )

    def test_technical_notes_never_forecast(self):
        import numpy as np

        from app.engines.quant import quant_engine

        rng = np.random.default_rng(7)
        for drift, vol in [(0.6, 0.5), (-0.6, 0.5), (0.0, 3.0), (0.0, 0.1)]:
            closes = 100 + np.cumsum(rng.normal(drift, vol, 260))
            indicators = quant_engine.calculate_indicators(closes, closes + 1, closes - 1)

            text = " ".join(quant_engine.explain(indicators)).lower()
            for word in self.FORECAST_WORDS:
                assert word not in text, f"forecast language {word!r} in: {text}"

    def test_momentum_descriptions_never_forecast(self):
        from app.engines.quant import quant_engine

        for rsi in (5.0, 25.0, 50.0, 75.0, 95.0):
            reading = quant_engine.describe_momentum(rsi)
            text = f"{reading['label']} {reading['meaning']}".lower()
            for word in self.FORECAST_WORDS:
                assert word not in text, f"forecast language {word!r} in: {text}"


class TestUnusualMoves:
    def test_a_move_is_unusual_relative_to_this_stock_not_in_absolute_percent(self):
        # 3% is a big day for a utility and an ordinary one for a volatile
        # small cap. A fixed threshold would get both wrong.
        calm = describe("Utility", 3.0, _indicators(atr_percent=0.8))
        wild = describe("Biotech", 3.0, _indicators(atr_percent=6.0))

        assert calm["today"]["unusual"] is True
        assert wild["today"]["unusual"] is False

    def test_an_unusual_move_is_called_out_with_its_comparison(self):
        result = describe("Utility", 3.0, _indicators(atr_percent=0.8))
        assert "a bigger move than usual" in result["headline"]
        assert any("typical 0.8% daily range" in n for n in result["notable"])

    def test_no_atr_means_nothing_is_called_unusual(self):
        # Dividing by a zero range would make every move infinitely unusual.
        result = describe("Apple", 9.0, _indicators(atr_percent=0.0))
        assert result["today"]["unusual"] is False


class TestNotable:
    def test_crosses_are_reported_as_what_traders_watch_not_as_predictions(self):
        result = describe("Apple", 0.0, _indicators(golden_cross=True))
        note = next(n for n in result["notable"] if "50-day" in n)
        assert "many traders watch" in note
        # It must not claim the cross means the stock goes up.
        assert "bullish" not in note.lower()

    def test_range_position_is_reported_at_the_extremes(self):
        top = describe("Apple", 0.0, _indicators(price=109.0))
        bottom = describe("Apple", 0.0, _indicators(price=91.0))
        middle = describe("Apple", 0.0, _indicators(price=100.0))

        assert any("top of its recent range" in n for n in top["notable"])
        assert any("bottom of its recent range" in n for n in bottom["notable"])
        assert not any("recent range" in n for n in middle["notable"])

    def test_a_degenerate_range_is_skipped_rather_than_dividing_by_zero(self):
        result = describe("Apple", 0.0, _indicators(bollinger_upper=100.0, bollinger_lower=100.0))
        assert not any("recent range" in n for n in result["notable"])

    def test_quiet_stocks_get_no_manufactured_drama(self):
        result = describe("Coca-Cola", 0.1, _indicators(price_change_10d=0.2))
        assert result["notable"] == []


class TestState:
    @pytest.mark.parametrize(
        "period_pct,expected",
        [(6.0, "rising"), (-6.0, "falling"), (0.1, "steady"), (-0.1, "steady")],
    )
    def test_state_follows_the_two_week_move(self, period_pct, expected):
        result = describe("Apple", 0.0, _indicators(price_change_10d=period_pct))
        assert result["state"] == expected


class TestAttention:
    def test_unavailable_sentiment_is_none_not_zero(self):
        # "nobody is talking about it" and "we could not find out" are
        # different statements, and only one of them is true.
        result = describe("Apple", 0.0, _indicators(), sentiment={"available": False})
        assert result["attention"] is None

        result = describe("Apple", 0.0, _indicators(), sentiment=None)
        assert result["attention"] is None

    def test_coverage_is_summarised_with_its_direction(self):
        result = describe("Apple", 0.0, _indicators(), sentiment={
            "available": True, "mentions": 17, "mention_velocity": "rising",
        })
        assert result["attention"]["mentions"] == 17
        assert result["attention"]["summary"] == (
            "17 recent articles and posts, and coverage is picking up."
        )

    def test_a_single_article_is_not_pluralised(self):
        result = describe("Apple", 0.0, _indicators(), sentiment={
            "available": True, "mentions": 1, "mention_velocity": "steady",
        })
        assert result["attention"]["summary"] == "1 recent article."
