"""
Sentiment model with graceful degradation.

Three analysers, in descending order of quality, each optional:

1. **FinBERT / Twitter RoBERTa** — local transformers, best results.
   Installed via `requirements-ml.txt` (~800MB with PyTorch).
2. **Llama 3 via Groq** — cloud, needs `GROQ_API_KEY`.
3. **VADER** — lexicon-based, always available, no download.

Two things matter about how they load:

- **Imports are lazy.** `transformers` is imported inside the loader, not at
  module scope, so the whole sentiment stack remains importable when the ML
  extras are not installed. A module-level import made this file — and every
  module that touched it — raise ImportError on a default install.
- **Models are loaded on first use, not in __init__.** Constructing this class
  used to download and initialise two transformer models eagerly, which blocked
  for minutes on a cold cache and ran even for requests that never needed them.

Whatever is unavailable is skipped, and `analyze()` falls back down the list.
"""

from __future__ import annotations

import logging
import os
from typing import Any, Optional

from vaderSentiment.vaderSentiment import SentimentIntensityAnalyzer

logger = logging.getLogger(__name__)

# Extra weight for financial slang that VADER's general-purpose lexicon
# either scores neutrally or gets backwards.
FINANCIAL_LEXICON: dict[str, float] = {
    "bullish": 2.0,
    "bearish": -2.0,
    "long": 1.0,
    "short": -1.0,
    "call": 0.5,
    "put": -0.5,
    "moon": 2.0,
    "dump": -2.0,
    "pump": 1.5,
    "breakout": 1.5,
    "resistance": -0.5,
    "support": 0.5,
    "rug pull": -3.0,
    "gem": 1.5,
    "fud": -1.5,
    "fomo": 1.0,
    "ath": 2.0,
    "atl": -2.0,
}

# Transformer inputs are capped around 512 tokens; ~500 characters is a safe
# proxy that avoids the tokeniser truncating mid-analysis.
MAX_TRANSFORMER_CHARS = 500
MAX_LLM_CHARS = 2000

_SOCIAL_LABELS = {"LABEL_0": "bearish", "LABEL_1": "neutral", "LABEL_2": "bullish"}


class SentimentModel:
    """Analyses text sentiment using the best available backend."""

    def __init__(self) -> None:
        self.vader = SentimentIntensityAnalyzer()
        self.vader.lexicon.update(FINANCIAL_LEXICON)

        # Populated on first use. `False` means "tried and unavailable", which
        # is distinct from `None` meaning "not yet attempted".
        self._news_pipe: Any = None
        self._social_pipe: Any = None
        self._groq: Any = None

    # ------------------------------------------------------------------
    # Lazy backends
    # ------------------------------------------------------------------

    def _load_pipeline(self, model_name: str) -> Any:
        """Build a transformers pipeline, or return False if unavailable."""
        try:
            from transformers import pipeline
        except ImportError:
            logger.info(
                "transformers is not installed; using VADER instead of %s. "
                "Install with: pip install -r requirements-ml.txt",
                model_name,
            )
            return False

        try:
            return pipeline("text-classification", model=model_name)
        except Exception as exc:
            # A download failure or missing cache must not break analysis.
            logger.warning("Could not load %s (%s); falling back to VADER", model_name, exc)
            return False

    @property
    def news_pipe(self) -> Any:
        if self._news_pipe is None:
            self._news_pipe = self._load_pipeline("ProsusAI/finbert")
        return self._news_pipe

    @property
    def social_pipe(self) -> Any:
        if self._social_pipe is None:
            self._social_pipe = self._load_pipeline("cardiffnlp/twitter-roberta-base-sentiment")
        return self._social_pipe

    @property
    def groq(self) -> Any:
        """Groq client, or False when no API key is configured."""
        if self._groq is None:
            # Settings, not os.getenv — see the note in narrative_service.
            from app.core.config import get_settings

            api_key = get_settings().GROQ_API_KEY
            if not api_key:
                logger.info("GROQ_API_KEY is not set; discussion analysis will use VADER")
                self._groq = False
            else:
                try:
                    from groq import Groq

                    self._groq = Groq(api_key=api_key)
                except Exception as exc:
                    logger.warning("Could not create Groq client (%s); using VADER", exc)
                    self._groq = False
        return self._groq

    # ------------------------------------------------------------------
    # Analysis
    # ------------------------------------------------------------------

    @staticmethod
    def _truncate(text: str, max_length: int) -> str:
        """Cut text to length on a word boundary."""
        if len(text) <= max_length:
            return text
        return text[:max_length].rsplit(" ", 1)[0]

    def predict(self, text: str) -> tuple[float, str, float]:
        """
        VADER scoring. Returns (compound, label, confidence).

        Kept for the Kafka classifier worker, which stores a numeric score.
        """
        if not text:
            return 0.0, "neutral", 0.0

        compound = self.vader.polarity_scores(text)["compound"]
        if compound >= 0.05:
            label = "positive"
        elif compound <= -0.05:
            label = "negative"
        else:
            label = "neutral"
        return compound, label, abs(compound)

    def _vader_fallback(self, text: str) -> dict[str, Any]:
        """Bullish/bearish/neutral via VADER, used whenever a backend is absent."""
        compound, _, confidence = self.predict(text)
        if compound >= 0.05:
            sentiment = "bullish"
        elif compound <= -0.05:
            sentiment = "bearish"
        else:
            sentiment = "neutral"
        # VADER is a lexicon, not a classifier: report modest confidence so it
        # never outranks a real model in the aggregate.
        return {"sentiment": sentiment, "confidence": min(0.6, confidence), "model": "vader"}

    def analyze(self, text: str, source_type: str = "news") -> dict[str, Any]:
        """
        Analyse one piece of text.

        Args:
            text: The content to score.
            source_type: "news", "social", or "discussion" — selects the
                backend best suited to that kind of writing.

        Returns:
            {"sentiment": str, "confidence": float, "model": str}. Always
            returns a result; never raises for a missing backend.
        """
        if not text or not text.strip():
            return {"sentiment": "neutral", "confidence": 0.0, "model": "none"}

        if source_type == "news":
            return self._analyze_with_pipeline(text, self.news_pipe, "finbert")

        if source_type == "social":
            return self._analyze_with_pipeline(text, self.social_pipe, "twitter-roberta")

        if source_type == "discussion":
            return self._analyze_discussion(text)

        raise ValueError(
            f"Unknown source_type {source_type!r}. Use 'news', 'social', or 'discussion'."
        )

    def _analyze_with_pipeline(self, text: str, pipe: Any, model_name: str) -> dict[str, Any]:
        """Run a transformers pipeline, falling back to VADER on any problem."""
        if not pipe:
            return self._vader_fallback(text)

        try:
            results = pipe(self._truncate(text, MAX_TRANSFORMER_CHARS))
            first = list(results)[0] if results else {}
            raw_label = str(first.get("label", ""))
            # Twitter RoBERTa emits LABEL_0/1/2; FinBERT emits words already.
            sentiment = _SOCIAL_LABELS.get(raw_label, raw_label.lower()) or "neutral"
            return {
                "sentiment": sentiment,
                "confidence": float(first.get("score", 0.0)),
                "model": model_name,
            }
        except Exception as exc:
            logger.warning("%s inference failed (%s); falling back to VADER", model_name, exc)
            return self._vader_fallback(text)

    def _analyze_discussion(self, text: str) -> dict[str, Any]:
        """Ask Groq's Llama 3 to classify a discussion post."""
        client = self.groq
        if not client:
            return self._vader_fallback(text)

        try:
            from app.core.config import get_settings

            completion = client.chat.completions.create(
                model=get_settings().GROQ_MODEL,
                messages=[
                    {
                        "role": "system",
                        "content": (
                            "Analyze the sentiment of this financial post. "
                            "Return ONLY one word: 'Bullish', 'Bearish', or 'Neutral'."
                        ),
                    },
                    {"role": "user", "content": self._truncate(text, MAX_LLM_CHARS)},
                ],
                temperature=0,
                max_tokens=10,
            )
            raw = (completion.choices[0].message.content or "").strip().lower()

            # The model occasionally adds punctuation or a stray word; only
            # accept one of the three expected answers.
            sentiment = raw if raw in {"bullish", "bearish", "neutral"} else None
            if sentiment is None:
                for candidate in ("bullish", "bearish", "neutral"):
                    if candidate in raw:
                        sentiment = candidate
                        break
            if sentiment is None:
                logger.debug("Unexpected Groq response %r; falling back to VADER", raw)
                return self._vader_fallback(text)

            return {"sentiment": sentiment, "confidence": 0.90, "model": "llama-3.1-8b"}
        except Exception as exc:
            logger.warning("Groq analysis failed (%s); falling back to VADER", exc)
            return self._vader_fallback(text)

    @property
    def available_backends(self) -> dict[str, bool]:
        """
        Which backends are usable, without triggering a load.

        Reads the private fields directly so a health check does not cause a
        multi-hundred-megabyte model download as a side effect.
        """
        from app.core.config import get_settings

        return {
            "vader": True,
            "finbert": self._news_pipe not in (None, False),
            "twitter_roberta": self._social_pipe not in (None, False),
            "groq": bool(get_settings().GROQ_API_KEY),
        }
