"""Tests for the Hybrid Engine."""

from __future__ import annotations

import pytest

from app.engines.hybrid import HybridEngine, SignalType, hybrid_engine


@pytest.fixture
def engine() -> HybridEngine:
    return HybridEngine(technical_weight=0.45, sentiment_weight=0.55)


@pytest.fixture
def indicators() -> dict:
    return {
        "rsi": 55.0,
        "adx": 30.0,
        "trend": "uptrend",
        "volatility": "moderate",
        "data_quality": {"sufficient": True, "has_sma_200": True},
    }


@pytest.fixture
def sentiment() -> dict:
    return {"available": True, "mentions": 250, "mention_velocity": "rising"}


class TestWeighting:
    def test_weights_are_normalised(self):
        engine = HybridEngine(technical_weight=3.0, sentiment_weight=1.0)
        assert engine.technical_weight == pytest.approx(0.75)
        assert engine.sentiment_weight == pytest.approx(0.25)

    def test_rejects_non_positive_weights(self):
        with pytest.raises(ValueError):
            HybridEngine(technical_weight=0.0, sentiment_weight=0.0)

    def test_score_respects_the_weighting(self, engine):
        result = engine.synthesize(technical_rating=100, sentiment_rating=0)
        assert result["hybrid_score"] == 45  # 100 * 0.45 + 0 * 0.55

    def test_technical_only_engine_ignores_sentiment(self):
        engine = HybridEngine(technical_weight=1.0, sentiment_weight=0.0)
        result = engine.synthesize(technical_rating=80, sentiment_rating=10)
        assert result["hybrid_score"] == 80


class TestClassification:
    @pytest.mark.parametrize(
        "score,expected",
        [
            (95, SignalType.STRONG_BUY),
            (80, SignalType.STRONG_BUY),
            (70, SignalType.BUY),
            (65, SignalType.BUY),
            (50, SignalType.HOLD),
            (40, SignalType.HOLD),
            (30, SignalType.SELL),
            (25, SignalType.SELL),
            (10, SignalType.STRONG_SELL),
        ],
    )
    def test_score_maps_to_recommendation(self, engine, score, expected):
        assert engine._classify(score) is expected

    def test_signal_direction_matches_recommendation(self, engine):
        bullish = engine.synthesize(90, 90)
        bearish = engine.synthesize(10, 10)
        assert bullish["signal"] == "bullish"
        assert bearish["signal"] == "bearish"

    def test_score_is_clamped_to_range(self, engine):
        assert 0 <= engine.synthesize(0, 0)["hybrid_score"] <= 100
        assert 0 <= engine.synthesize(100, 100)["hybrid_score"] <= 100


class TestConfidence:
    def test_is_deterministic(self, engine, indicators, sentiment):
        """
        Regression test: confidence used to have `random.randint(-10, 10)`
        added to it, so identical inputs produced a different number on every
        page refresh. In a tool people may act on, that is indefensible.
        """
        results = {
            engine.synthesize(70, 65, indicators, sentiment)["confidence"] for _ in range(20)
        }
        assert len(results) == 1

    def test_never_claims_certainty(self, engine, indicators, sentiment):
        result = engine.synthesize(100, 100, indicators, sentiment)
        assert result["confidence"] <= 95

    def test_agreement_beats_disagreement(self, engine, indicators, sentiment):
        agree = engine.synthesize(75, 75, indicators, sentiment)["confidence"]
        disagree = engine.synthesize(85, 25, indicators, sentiment)["confidence"]
        assert agree > disagree

    def test_thin_coverage_lowers_confidence(self, engine, indicators):
        thick = engine.synthesize(70, 70, indicators, {"available": True, "mentions": 500})
        thin = engine.synthesize(70, 70, indicators, {"available": True, "mentions": 3})
        assert thick["confidence"] > thin["confidence"]

    def test_insufficient_price_history_lowers_confidence(self, engine, sentiment):
        good = {"rsi": 55.0, "adx": 30.0, "data_quality": {"sufficient": True}}
        poor = {"rsi": 55.0, "adx": 30.0, "data_quality": {"sufficient": False}}
        assert (
            engine.synthesize(70, 70, good, sentiment)["confidence"]
            > engine.synthesize(70, 70, poor, sentiment)["confidence"]
        )

    def test_missing_sentiment_is_penalised_once(self, engine, indicators):
        """
        Regression test: absent sentiment was charged three times over — once
        for the availability flag, once for zero mentions, and once more in the
        base adjustment — driving a clean technical read down to ~16%.
        """
        absent = {"available": False, "mentions": 0, "mention_velocity": "unknown"}
        confidence = engine.synthesize(70, 70, indicators, absent)["confidence"]
        assert 25 <= confidence <= 70


class TestMissingSentiment:
    """When sentiment is unavailable the engines must not appear to corroborate."""

    def test_does_not_claim_the_engines_agree(self, engine, indicators):
        absent = {"available": False, "mentions": 0}
        # The caller passes technical_rating as a stand-in for sentiment so the
        # weighted sum still works; that must not read as independent support.
        result = engine.synthesize(70, 70, indicators, absent)
        joined = " ".join(result["reasons"]).lower()
        assert "same story" not in joined
        assert "telling the same" not in joined

    def test_suppresses_pattern_detection(self, engine):
        absent = {"available": False, "mentions": 0}
        overbought = {"rsi": 85.0, "adx": 30.0}
        # "Crowded trade" needs real crowd sentiment; without it, no pattern.
        assert engine.synthesize(80, 80, overbought, absent)["pattern"] is None

    def test_explains_why_sentiment_is_missing(self, engine, indicators):
        absent = {
            "available": False,
            "mentions": 0,
            "reason": "No recent news or social posts were found for this stock.",
        }
        reasons = " ".join(engine.synthesize(70, 70, indicators, absent)["reasons"]).lower()
        assert "price action alone" in reasons


class TestPatterns:
    def test_detects_a_crowded_trade(self, engine):
        pattern = engine.detect_pattern(75, 85, {"rsi": 78.0})
        assert pattern is not None and pattern["id"] == "blow_off_top"

    def test_detects_capitulation(self, engine):
        pattern = engine.detect_pattern(25, 30, {"rsi": 22.0})
        assert pattern is not None and pattern["id"] == "capitulation"

    def test_detects_price_up_mood_down(self, engine):
        pattern = engine.detect_pattern(70, 30, {"rsi": 75.0})
        assert pattern is not None and pattern["id"] == "bearish_divergence"

    def test_no_pattern_without_indicators(self, engine):
        assert engine.detect_pattern(70, 70, None) is None

    def test_ordinary_conditions_produce_no_pattern(self, engine):
        assert engine.detect_pattern(50, 50, {"rsi": 50.0}) is None


class TestPlainLanguage:
    def test_summary_is_a_readable_sentence(self, engine, indicators, sentiment):
        summary = engine.synthesize(70, 70, indicators, sentiment)["plain_summary"]
        assert isinstance(summary, str)
        assert len(summary) > 30
        assert summary[0].isupper()

    def test_summary_avoids_jargon(self, engine, indicators, sentiment):
        summary = engine.synthesize(70, 70, indicators, sentiment)["plain_summary"]
        for jargon in ("RSI", "MACD", "ADX", "hybrid_score", "divergence"):
            assert jargon not in summary

    def test_every_recommendation_has_a_human_label(self, engine):
        for score, _ in [(90, 0), (70, 0), (50, 0), (30, 0), (10, 0)]:
            result = engine.synthesize(score, score)
            assert result["label"] and result["label"][0].isupper()
            assert "_" not in result["label"]


class TestDefaultInstance:
    def test_module_instance_uses_documented_weights(self):
        assert hybrid_engine.technical_weight == pytest.approx(0.45)
        assert hybrid_engine.sentiment_weight == pytest.approx(0.55)
