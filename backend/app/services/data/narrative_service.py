"""
Narrative Service — turns Signal Desk readings into a sentence a person can use.

Two implementations, same contract:

- **Groq (Llama 3)** when ``GROQ_API_KEY`` is set. Better prose, handles the
  interactions between signals that a template cannot.
- **A deterministic template** otherwise. Always available, never wrong, just
  plainer.

The prompt is deliberately constrained to *describing what happened*. It is
explicitly forbidden from forecasting or advising, for two reasons: the engine
has no demonstrated predictive edge to justify a forecast, and telling people
what to do with securities is a different regulatory posture from telling them
what the market did.
"""

from __future__ import annotations

import logging
import os
from typing import Any, Optional

logger = logging.getLogger(__name__)

def _model() -> str:
    """The chat model to use, from settings."""
    from app.core.config import get_settings

    return get_settings().GROQ_MODEL

SYSTEM_PROMPT = """You write one short market summary for a first-time investor.

RULES — follow all of them:
- 2 sentences maximum. Under 45 words total.
- Describe ONLY what the data shows has already happened.
- NEVER predict, forecast, or say what will/might happen next.
- NEVER advise buying, selling, or holding anything.
- No jargon: say "government bond yields", not "10Y"; "borrowing costs" not "rates complex".
- Plain declarative sentences. No hedging filler like "it appears that".
- Do not invent any number that is not given to you.

Good: "Government bond yields jumped this week and corporate debt sold off
alongside them. Energy was the only sector with real strength."

Bad: "Rates are spiking, which could pressure equities going forward."
(predicts) """


class NarrativeService:
    """Generates the Signal Desk narrative."""

    def __init__(self) -> None:
        self._client: Any = None

    @property
    def client(self) -> Any:
        """Groq client, or False when unavailable. Built on first use."""
        if self._client is None:
            api_key = os.getenv("GROQ_API_KEY")
            if not api_key:
                self._client = False
            else:
                try:
                    from groq import Groq

                    self._client = Groq(api_key=api_key)
                except Exception as exc:
                    logger.warning("Groq unavailable (%s); using template narrative", exc)
                    self._client = False
        return self._client

    def generate(self, desk: dict[str, Any]) -> dict[str, str]:
        """
        Build the narrative for a Signal Desk payload.

        Returns ``{"text": ..., "source": "llm"|"template"}`` so the UI can be
        honest about where the sentence came from.
        """
        if not desk.get("available"):
            return {"text": "Market data is temporarily unavailable.", "source": "none"}

        template = self._template(desk)

        client = self.client
        if not client:
            return {"text": template, "source": "template"}

        try:
            completion = client.chat.completions.create(
                model=_model(),
                messages=[
                    {"role": "system", "content": SYSTEM_PROMPT},
                    {"role": "user", "content": self._facts(desk)},
                ],
                temperature=0.3,
                max_tokens=90,
            )
            text = (completion.choices[0].message.content or "").strip().strip('"')

            # A model that ignores the brief is worse than the template.
            if not text or len(text) > 320 or self._looks_predictive(text):
                logger.info("Rejected LLM narrative, falling back to template")
                return {"text": template, "source": "template"}

            return {"text": text, "source": "llm"}
        except Exception as exc:
            logger.warning("Narrative generation failed (%s); using template", exc)
            return {"text": template, "source": "template"}

    @staticmethod
    def _looks_predictive(text: str) -> bool:
        """Reject output that forecasts or advises despite the instructions."""
        lowered = text.lower()
        banned = (
            "will likely", "expect", "should buy", "should sell", "we recommend",
            "going forward", "poised to", "set to ", "outlook", "forecast",
            "could push", "may push", "likely to",
        )
        return any(phrase in lowered for phrase in banned)

    @staticmethod
    def _facts(desk: dict[str, Any]) -> str:
        """The numeric brief handed to the model. Only real, measured values."""
        lines: list[str] = []

        composite = desk["composite"]
        lines.append(
            f"Overall risk appetite: {composite['label']} ({composite['score']}/100, "
            f"where 50 is neutral)."
        )

        lines.append(f"Notable moves over the last {desk['lookback_days']} trading days:")
        for signal in desk["signals"][:5]:
            lines.append(
                f"- {signal['name']}: {signal['text']} ({signal['change_percent']:+.1f}%, "
                f"{signal['z_score']:+.1f} standard deviations from normal)"
            )

        sectors = desk.get("sectors", {})
        if sectors.get("available"):
            leaders = ", ".join(
                f"{s['name']} {s['change_percent']:+.1f}%" for s in sectors["leaders"][:2]
            )
            laggards = ", ".join(
                f"{s['name']} {s['change_percent']:+.1f}%" for s in sectors["laggards"][:2]
            )
            lines.append(f"Strongest sectors: {leaders}.")
            lines.append(f"Weakest sectors: {laggards}.")
            lines.append(
                f"{sectors['advancing']} of {sectors['total']} sectors advanced."
            )

        return "\n".join(lines)

    @staticmethod
    def _template(desk: dict[str, Any]) -> str:
        """
        Deterministic fallback narrative.

        Built from the two most unusual signals plus sector leadership — the
        same facts the model is given, assembled by rule.
        """
        composite = desk["composite"]
        signals = desk.get("signals", [])
        sectors = desk.get("sectors", {})

        opening = {
            "risk_on": "Investors leaned into risk this week.",
            "risk_off": "Investors pulled back from risk this week.",
            "neutral": "The market sent mixed messages this week.",
        }[composite["tone"]]

        parts = [opening]

        notable = [s for s in signals if s["notable"]][:2]
        if notable:
            moves = " and ".join(s["text"][0].lower() + s["text"][1:] for s in notable)
            parts.append(f"The clearest moves: {moves}.")

        if sectors.get("available") and sectors.get("leaders"):
            leader = sectors["leaders"][0]
            laggard = sectors["laggards"][0]
            if leader["change_percent"] > 0 > laggard["change_percent"]:
                parts.append(
                    f"{leader['name']} led at {leader['change_percent']:+.1f}%, "
                    f"while {laggard['name']} lagged at {laggard['change_percent']:+.1f}%."
                )

        return " ".join(parts)


narrative_service = NarrativeService()
