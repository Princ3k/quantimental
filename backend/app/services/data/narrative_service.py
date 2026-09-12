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

Two lengths are produced from a single call: the full ``text``, and a ``short``
form under 100 characters for space-constrained surfaces — a home-screen
widget, a notification, an email subject. The short form is never a substring
of the long one. Cutting prose at a character count lands mid-clause and reads
as broken, so the model is asked for a self-contained headline, and both
fallbacks below it produce complete sentences too.
"""

from __future__ import annotations

import logging
from typing import Any, Optional

logger = logging.getLogger(__name__)

def _model() -> str:
    """The chat model to use, from settings."""
    from app.core.config import get_settings

    return get_settings().GROQ_MODEL

# Two labelled lines rather than JSON. A model that fumbles JSON costs us both
# outputs; a model that fumbles this format usually still produces one usable
# labelled line, and the parser takes what it can get.
SYSTEM_PROMPT = """You write market summaries for a first-time investor.

Reply with exactly these two lines and nothing else:

HEADLINE: <one sentence, MUST be under 100 characters, the single most
important thing that happened>
SUMMARY: <2 sentences maximum, under 45 words total>

RULES — follow all of them for both lines:
- Describe ONLY what the data shows has already happened.
- NEVER predict, forecast, or say what will/might happen next.
- NEVER advise buying, selling, or holding anything.
- No jargon: say "government bond yields", not "10Y"; "borrowing costs" not "rates complex".
- Plain declarative sentences. No hedging filler like "it appears that".
- Do not invent any number that is not given to you.
- The HEADLINE must stand alone. It is shown on its own, without the SUMMARY.

Good:
HEADLINE: Government bond yields jumped and corporate debt sold off with them.
SUMMARY: Government bond yields jumped this week and corporate debt sold off
alongside them. Energy was the only sector with real strength.

Bad: "Rates are spiking, which could pressure equities going forward."
(predicts) """

# Widget-safe. The large iOS widget fits roughly this much alongside the score,
# the moves list and the sector line.
SHORT_MAX_CHARS = 100


class NarrativeService:
    """Generates the Signal Desk narrative."""

    def __init__(self) -> None:
        self._client: Any = None

    @property
    def client(self) -> Any:
        """Groq client, or False when unavailable. Built on first use."""
        if self._client is None:
            # Read through Settings, not os.getenv: pydantic-settings loads
            # .env into the Settings object without ever touching os.environ,
            # so os.getenv returns None for a key that is configured correctly.
            from app.core.config import get_settings

            api_key = get_settings().GROQ_API_KEY
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

        Returns ``{"text", "short", "source", "short_source", "reason"}``.
        ``reason`` is set only when the LLM path was skipped or refused, so a
        deployed instance can explain a silent downgrade without anyone needing
        to read its logs — which is exactly the position a fallback leaves you
        in otherwise. ``short_source`` does the same for the short form, which
        can fall back independently of the long one.
        """
        if not desk.get("available"):
            unavailable = "Market data is temporarily unavailable."
            return {
                "text": unavailable,
                "short": unavailable,
                "source": "none",
                "short_source": "none",
            }

        template = self._template(desk)
        template_short = self._template_short(desk)

        client = self.client
        if not client:
            return {
                "text": template,
                "short": template_short,
                "source": "template",
                "short_source": "template",
                "reason": "no_api_key",
            }

        try:
            completion = client.chat.completions.create(
                model=_model(),
                messages=[
                    {"role": "system", "content": SYSTEM_PROMPT},
                    {"role": "user", "content": self._facts(desk)},
                ],
                temperature=0.3,
                # Raised from 90: the reply now carries a headline as well.
                max_tokens=160,
            )
            raw = (completion.choices[0].message.content or "").strip()
            headline, text = self._parse(raw)

            # A model that ignores the brief is worse than the template.
            if not text:
                reason = "empty_response"
            elif len(text) > 320:
                reason = "too_long"
            elif self._looks_predictive(text):
                reason = "predictive_language_rejected"
            else:
                short, short_source = self._choose_short(headline, text, template_short)
                result = {"text": text, "short": short, "source": "llm",
                          "short_source": short_source}
                return result

            logger.info("Rejected LLM narrative (%s), falling back to template", reason)
            return {
                "text": template,
                "short": template_short,
                "source": "template",
                "short_source": "template",
                "reason": reason,
            }
        except Exception as exc:
            logger.warning("Narrative generation failed (%s); using template", exc)
            return {
                "text": template,
                "short": template_short,
                "source": "template",
                "short_source": "template",
                "reason": self._safe_error(exc),
            }

    @staticmethod
    def _parse(raw: str) -> tuple[str, str]:
        """
        Split the reply into (headline, summary).

        Tolerant on purpose. A model that drops the labels entirely still gives
        us usable prose, so unlabelled output becomes the summary with no
        headline, and the caller falls back for the short form rather than
        discarding a perfectly good narrative over a formatting slip.
        """
        headline = ""
        summary_lines: list[str] = []
        in_summary = False

        for line in raw.splitlines():
            stripped = line.strip()
            if not stripped:
                continue
            lowered = stripped.lower()
            if lowered.startswith("headline:"):
                headline = stripped.split(":", 1)[1].strip().strip('"')
                in_summary = False
            elif lowered.startswith("summary:"):
                summary_lines.append(stripped.split(":", 1)[1].strip())
                in_summary = True
            elif in_summary or not headline:
                # Continuation of a wrapped line, or an unlabelled reply.
                summary_lines.append(stripped)
            else:
                # A wrapped headline, before any SUMMARY label appeared.
                headline = f"{headline} {stripped}".strip()

        summary = " ".join(summary_lines).strip().strip('"')
        return headline, summary

    @classmethod
    def _choose_short(
        cls, headline: str, text: str, template_short: str
    ) -> tuple[str, str]:
        """
        Pick the short form, in descending order of quality.

        1. The model's own headline, when it obeyed the length limit.
        2. The first complete sentence of the summary, if that fits — a whole
           sentence, not a substring, so it never reads as cut off.
        3. The deterministic template, which fits by construction.
        """
        if headline and len(headline) <= SHORT_MAX_CHARS and not cls._looks_predictive(headline):
            return headline, "llm"

        first = cls._first_sentence(text)
        if first and len(first) <= SHORT_MAX_CHARS and not cls._looks_predictive(first):
            return first, "first_sentence"

        return template_short, "template"

    @staticmethod
    def _first_sentence(text: str) -> str:
        """
        The first complete sentence, or "" when there is no sentence break.

        Returning "" rather than the whole string matters: the caller is
        choosing something that must fit a length cap, and a paragraph with no
        full stop is not a candidate.
        """
        import re

        match = re.search(r"^(.+?[.!?])(\s|$)", text.strip())
        return match.group(1).strip() if match else ""

    @staticmethod
    def _safe_error(exc: Exception) -> str:
        """
        Summarise a failure without echoing anything sensitive.

        Provider errors quote request context, so the message is truncated and
        scrubbed of anything shaped like a credential before it goes into a
        public API response.
        """
        import re

        detail = f"{type(exc).__name__}: {exc}"[:200]
        return re.sub(r"(gsk_|sk-|Bearer\s+)\S+", r"\1***", detail)

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

    @staticmethod
    def _template_short(desk: dict[str, Any]) -> str:
        """
        Deterministic short narrative, guaranteed to fit by construction.

        Built up in descending order of detail and stopped as soon as the next
        clause would breach the cap, so the result is always a whole sentence
        rather than a trimmed one. The bare opening is well under the limit, so
        there is always something to return.
        """
        composite = desk["composite"]
        signals = desk.get("signals", [])
        sectors = desk.get("sectors", {})

        opening = {
            "risk_on": "Investors leaned into risk this week",
            "risk_off": "Investors pulled back from risk this week",
            "neutral": "The market sent mixed messages this week",
        }[composite["tone"]]

        notable = [s for s in signals if s.get("notable")]
        if notable:
            move = notable[0]["text"]
            move = move[0].lower() + move[1:]
            candidate = f"{opening}, with {move}."
            if len(candidate) <= SHORT_MAX_CHARS:
                return candidate

        if sectors.get("available") and sectors.get("leaders"):
            leader = sectors["leaders"][0]
            if leader["change_percent"] > 0:
                candidate = (
                    f"{opening}, with {leader['name']} leading at "
                    f"{leader['change_percent']:+.1f}%."
                )
                if len(candidate) <= SHORT_MAX_CHARS:
                    return candidate

        return f"{opening}."


narrative_service = NarrativeService()
