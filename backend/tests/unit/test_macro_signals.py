"""
Tests for the macro Signal Desk.

Market data is stubbed with synthetic price histories so these run offline and
deterministically — the point is to verify the reasoning, not Yahoo's uptime.
"""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from app.services.data import macro_signal_service as macro
from app.services.data.macro_signal_service import MacroSignalService
from app.services.data.narrative_service import NarrativeService


def _series(start: float, drift: float, n: int = 260, seed: int = 0) -> np.ndarray:
    """A price path with a controllable trend."""
    rng = np.random.default_rng(seed)
    return start + np.cumsum(rng.normal(drift, abs(start) * 0.004, n))


@pytest.fixture
def stub_closes() -> pd.DataFrame:
    """A calm, featureless market: every instrument drifts sideways."""
    symbols = [i.symbol for i in macro.MACRO_UNIVERSE] + list(macro.SECTOR_ETFS)
    index = pd.bdate_range(end="2026-09-11", periods=260)
    return pd.DataFrame(
        {s: _series(100.0, 0.0, len(index), seed=i) for i, s in enumerate(symbols)},
        index=index,
    )


@pytest.fixture
def service(monkeypatch, stub_closes) -> MacroSignalService:
    svc = MacroSignalService()
    monkeypatch.setattr(svc, "_fetch_closes", lambda: stub_closes)
    macro._cache.clear()
    return svc


class TestDeskShape:
    def test_returns_a_complete_payload(self, service):
        desk = service.get_desk()
        for key in ("available", "signals", "composite", "sectors", "history"):
            assert key in desk
        assert desk["available"] is True

    def test_reports_unavailable_rather_than_inventing(self, monkeypatch):
        svc = MacroSignalService()
        monkeypatch.setattr(svc, "_fetch_closes", lambda: None)
        macro._cache.clear()

        desk = svc.get_desk()
        assert desk["available"] is False
        assert desk["reason"]
        # No fabricated market picture when the feed is down.
        assert "composite" not in desk

    def test_every_signal_is_well_formed(self, service):
        for signal in service.get_desk()["signals"]:
            assert signal["direction"] in {"up", "down", "flat"}
            assert signal["risk_tone"] in {"risk_on", "risk_off", "neutral"}
            assert signal["delta"]
            assert isinstance(signal["notable"], bool)
            assert not np.isnan(signal["z_score"])


class TestComposite:
    def test_score_is_bounded(self, service):
        assert 0 <= service.get_desk()["composite"]["score"] <= 100

    def test_calm_market_reads_near_neutral(self, service):
        # Every instrument is drifting sideways, so nothing should tilt the read.
        composite = service.get_desk()["composite"]
        assert 35 <= composite["score"] <= 65
        assert composite["label"] == "Mixed"

    def test_rising_yields_push_risk_off(self, monkeypatch, stub_closes):
        closes = stub_closes.copy()
        # A sharp jump in the last week only — a genuine spike, not a trend.
        closes.loc[closes.index[-5:], "^TNX"] = closes["^TNX"].iloc[-6] * 1.15

        svc = MacroSignalService()
        monkeypatch.setattr(svc, "_fetch_closes", lambda: closes)
        macro._cache.clear()

        composite = svc.get_desk()["composite"]
        assert composite["score"] < 50, "spiking yields should read risk-off"

    def test_correlated_instruments_do_not_double_count(self, monkeypatch, stub_closes):
        """
        Regression test.

        High-yield and investment-grade credit move together, so summing both
        let a single underlying story vote twice and drove the composite to
        implausible extremes. Contributions are averaged within a category.
        """
        closes = stub_closes.copy()
        for symbol in ("HYG", "LQD"):
            closes.loc[closes.index[-5:], symbol] = closes[symbol].iloc[-6] * 0.90

        svc = MacroSignalService()
        monkeypatch.setattr(svc, "_fetch_closes", lambda: closes)
        macro._cache.clear()

        composite = svc.get_desk()["composite"]
        names = [c["name"] for c in composite["contributions"]]
        # The two credit instruments collapse into one line item.
        assert sum(1 for n in names if "redit" in n) == 1


class TestCompositeHistory:
    def test_trace_ends_near_the_headline_score(self, service):
        """
        Regression test.

        The sparkline sits under a "Risk appetite" label, so its last point has
        to agree with the number printed beside it. An earlier version plotted
        an equal-weight sector basket over 30 days against a 5-day risk score,
        so the line could trend green while the headline read risk-off.
        """
        desk = service.get_desk()
        history, score = desk["history"], desk["composite"]["score"]

        assert history, "expected a trace to plot"
        assert abs(history[-1] - score) <= 3, (
            f"chart ends at {history[-1]} but the headline says {score}"
        )

    def test_trace_is_bounded_like_the_score(self, service):
        for point in service.get_desk()["history"]:
            assert 0 <= point <= 100

    def test_trace_responds_to_a_risk_off_shock(self, monkeypatch, stub_closes):
        closes = stub_closes.copy()
        closes.loc[closes.index[-5:], "^TNX"] = closes["^TNX"].iloc[-6] * 1.2

        svc = MacroSignalService()
        monkeypatch.setattr(svc, "_fetch_closes", lambda: closes)
        macro._cache.clear()

        history = svc.get_desk()["history"]
        assert history[-1] < history[0], "a yield spike should pull the trace down"


class TestSectors:
    def test_breadth_is_a_percentage(self, service):
        sectors = service.get_desk()["sectors"]
        assert 0 <= sectors["breadth"] <= 100
        assert sectors["advancing"] <= sectors["total"]

    def test_leaders_outrank_laggards(self, service):
        sectors = service.get_desk()["sectors"]
        assert sectors["leaders"][0]["change_percent"] >= sectors["laggards"][0]["change_percent"]


@pytest.fixture
def no_groq(monkeypatch):
    """
    Force the no-API-key path.

    Deleting the environment variable is not enough: the key is read through
    Settings, which loads it from .env without going near os.environ. The
    setting itself has to be overridden.
    """
    from app.core import config

    patched = config.get_settings().model_copy(update={"GROQ_API_KEY": None})
    monkeypatch.setattr(config, "get_settings", lambda: patched)
    return patched


class TestNarrative:
    def test_template_is_used_without_an_api_key(self, service, no_groq):
        result = NarrativeService().generate(service.get_desk())

        assert result["source"] == "template"
        assert len(result["text"]) > 30

    def test_template_never_predicts_or_advises(self, service, no_groq):
        text = NarrativeService().generate(service.get_desk())["text"].lower()

        for phrase in ("will ", "expect", "should buy", "should sell", "forecast", "poised"):
            assert phrase not in text, f"narrative should not forecast: {phrase!r}"

    def test_predictive_llm_output_is_rejected(self):
        svc = NarrativeService()
        assert svc._looks_predictive("Rates could push equities lower going forward.")
        assert svc._looks_predictive("Energy is poised to outperform.")
        assert not svc._looks_predictive("Government bond yields rose and credit sold off.")

    def test_fallback_explains_itself(self, service, no_groq):
        """
        A silent downgrade leaves you reading logs you may not have access to.
        The payload says why it fell back.
        """
        result = NarrativeService().generate(service.get_desk())
        assert result["reason"] == "no_api_key"

    def test_rejected_output_names_the_reason(self, service, monkeypatch):
        svc = NarrativeService()

        class _Message:
            content = "Rates are poised to push equities lower going forward."

        class _Choice:
            message = _Message()

        class _Completion:
            choices = [_Choice()]

        class _Client:
            class chat:
                class completions:
                    @staticmethod
                    def create(**_):
                        return _Completion()

        monkeypatch.setattr(type(svc), "client", property(lambda self: _Client()))
        result = svc.generate(service.get_desk())

        assert result["source"] == "template"
        assert result["reason"] == "predictive_language_rejected"

    def test_failure_reason_never_echoes_a_credential(self):
        redacted = NarrativeService._safe_error(
            RuntimeError("401 unauthorized for key gsk_abcdef123456 on Bearer gsk_zzz")
        )
        assert "gsk_abcdef123456" not in redacted
        assert "gsk_zzz" not in redacted
        assert "gsk_***" in redacted

    def test_unavailable_desk_yields_no_narrative(self):
        result = NarrativeService().generate({"available": False})
        assert result["source"] == "none"

    def test_facts_brief_contains_only_given_numbers(self, service):
        desk = service.get_desk()
        brief = NarrativeService()._facts(desk)
        assert str(desk["composite"]["score"]) in brief
        assert "standard deviations" in brief
