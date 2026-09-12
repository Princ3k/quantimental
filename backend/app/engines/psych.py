"""
Psych Engine

The psychological analysis core of Quantimental.
Responsible for converting text (social media, news) into quantifiable sentiment metrics.

Logic:
- VADER Sentiment Analysis (Valence Aware Dictionary and sEntiment Reasoner)
- Emotion Classification (Fear, Greed, Neutral)
- Weighted scoring based on source credibility (future)
"""

import logging
from typing import Dict, Any, Tuple
from vaderSentiment.vaderSentiment import SentimentIntensityAnalyzer

logger = logging.getLogger(__name__)

class PsychEngine:
    """
    Analyzes text sentiment and emotion.
    """
    
    def __init__(self):
        self.analyzer = SentimentIntensityAnalyzer()
        
        # Custom lexicon updates for financial context
        self.analyzer.lexicon.update({
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
            "ath": 2.0,  # All Time High
            "atl": -2.0, # All Time Low
        })

    def analyze_text(self, text: str) -> Dict[str, Any]:
        """
        Analyze text and return sentiment scores.
        
        Args:
            text: The text to analyze.
            
        Returns:
            Dict containing:
            - sentiment_score: float (-1.0 to 1.0)
            - sentiment_label: str (positive, negative, neutral)
            - emotion: str (FEAR, GREED, NEUTRAL, etc.)
            - raw_scores: dict (neg, neu, pos, compound)
        """
        if not text:
            return {
                "sentiment_score": 0.0,
                "sentiment_label": "neutral",
                "emotion": "NEUTRAL",
                "raw_scores": {}
            }
            
        # VADER Analysis
        scores = self.analyzer.polarity_scores(text)
        compound = scores["compound"]
        
        # Determine Label
        if compound >= 0.05:
            label = "positive"
        elif compound <= -0.05:
            label = "negative"
        else:
            label = "neutral"
            
        # Determine Emotion (Heuristic)
        # Fear: Negative sentiment + specific keywords (optional)
        # Greed: Positive sentiment + specific keywords
        emotion = "NEUTRAL"
        if compound >= 0.5:
            emotion = "GREED"
        elif compound <= -0.5:
            emotion = "FEAR"
        elif compound >= 0.2:
            emotion = "OPTIMISM"
        elif compound <= -0.2:
            emotion = "PESSIMISM"
            
        return {
            "sentiment_score": compound,
            "sentiment_label": label,
            "emotion": emotion,
            "raw_scores": scores
        }

# Global instance
psych_engine = PsychEngine()

