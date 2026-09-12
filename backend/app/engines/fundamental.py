"""
Fundamental Engine (Lightweight)

Lightweight fundamental analysis for Quantimental.
Provides basic valuation and earnings metrics without heavy API dependencies.

Data Sources:
- Yahoo Finance (free, no API key required)
- Basic P/E, P/B, market cap calculations
- Earnings trend detection (if available)

Note: This is a lightweight implementation. Full fundamental analysis
would require SEC filings, earnings transcripts, etc.
"""

import logging
from typing import Dict, Any, Optional
import yfinance as yf

logger = logging.getLogger(__name__)


class FundamentalEngine:
    """
    Lightweight fundamental analysis engine.
    """
    
    def __init__(self):
        pass
    
    def analyze(self, ticker: str) -> Dict[str, Any]:
        """
        Analyze fundamental metrics for a ticker.
        
        Args:
            ticker: Stock symbol
        
        Returns:
            Dictionary with:
            - valuation_score: 0-100 rating
            - pe_ratio: Price-to-Earnings ratio
            - pb_ratio: Price-to-Book ratio
            - market_cap: Market capitalization
            - earnings_trend: positive/negative/neutral
            - risk_score: 0-100 (higher = riskier)
            - success: bool
            - error: Optional error message
        """
        try:
            stock = yf.Ticker(ticker)
            info = stock.info
            
            # Extract key metrics
            pe_ratio = info.get('trailingPE') or info.get('forwardPE') or None
            pb_ratio = info.get('priceToBook') or None
            market_cap = info.get('marketCap') or None
            
            # Earnings data
            earnings_data = self._get_earnings_trend(stock)
            
            # Calculate valuation score
            valuation_score = self._calculate_valuation_score(
                pe_ratio, pb_ratio, market_cap, earnings_data
            )
            
            # Calculate risk score
            risk_score = self._calculate_risk_score(
                pe_ratio, pb_ratio, market_cap, earnings_data
            )
            
            return {
                "success": True,
                "valuation_score": valuation_score,
                "pe_ratio": pe_ratio,
                "pb_ratio": pb_ratio,
                "market_cap": market_cap,
                "earnings_trend": earnings_data.get('trend', 'neutral'),
                "earnings_growth": earnings_data.get('growth_rate', 0.0),
                "risk_score": risk_score,
                "error": None
            }
        
        except Exception as e:
            logger.error(f"Fundamental analysis failed for {ticker}: {e}")
            return {
                "success": False,
                "valuation_score": 50,  # Neutral default
                "pe_ratio": None,
                "pb_ratio": None,
                "market_cap": None,
                "earnings_trend": "neutral",
                "earnings_growth": 0.0,
                "risk_score": 50,
                "error": str(e)
            }
    
    def _get_earnings_trend(self, stock: yf.Ticker) -> Dict[str, Any]:
        """Extract earnings trend from stock data."""
        try:
            # Try to get earnings history
            earnings = stock.earnings_history
            if earnings is not None and len(earnings) > 0:
                # Simple trend: compare recent earnings
                # This is a simplified approach - full analysis would use quarterly reports
                return {
                    "trend": "positive",  # Placeholder
                    "growth_rate": 0.0
                }
            
            # Try financials
            financials = stock.financials
            if financials is not None and len(financials) > 0:
                # Extract net income trend
                if 'Net Income' in financials.index:
                    net_income = financials.loc['Net Income']
                    if len(net_income) >= 2:
                        recent = net_income.iloc[0]
                        previous = net_income.iloc[1]
                        if previous != 0:
                            growth_rate = ((recent - previous) / abs(previous)) * 100
                            trend = "positive" if growth_rate > 0 else "negative" if growth_rate < 0 else "neutral"
                            return {
                                "trend": trend,
                                "growth_rate": growth_rate
                            }
            
            return {
                "trend": "neutral",
                "growth_rate": 0.0
            }
        
        except Exception as e:
            logger.debug(f"Could not extract earnings trend: {e}")
            return {
                "trend": "neutral",
                "growth_rate": 0.0
            }
    
    def _calculate_valuation_score(
        self,
        pe_ratio: Optional[float],
        pb_ratio: Optional[float],
        market_cap: Optional[float],
        earnings_data: Dict[str, Any]
    ) -> int:
        """
        Calculate valuation score (0-100).
        Lower P/E and P/B = better value = higher score.
        """
        score = 50  # Neutral baseline
        
        # P/E ratio analysis
        if pe_ratio is not None:
            if pe_ratio < 15:
                score += 20  # Undervalued
            elif pe_ratio < 25:
                score += 10  # Fairly valued
            elif pe_ratio > 40:
                score -= 20  # Overvalued
            elif pe_ratio > 30:
                score -= 10  # Slightly overvalued
        
        # P/B ratio analysis
        if pb_ratio is not None:
            if pb_ratio < 1.0:
                score += 15  # Trading below book value
            elif pb_ratio < 3.0:
                score += 5  # Reasonable
            elif pb_ratio > 5.0:
                score -= 15  # Expensive relative to book
        
        # Earnings trend
        if earnings_data.get('trend') == 'positive':
            score += 10
        elif earnings_data.get('trend') == 'negative':
            score -= 10
        
        return max(0, min(100, score))
    
    def _calculate_risk_score(
        self,
        pe_ratio: Optional[float],
        pb_ratio: Optional[float],
        market_cap: Optional[float],
        earnings_data: Dict[str, Any]
    ) -> int:
        """
        Calculate risk score (0-100, higher = riskier).
        """
        risk = 50  # Neutral baseline
        
        # High P/E = higher risk (overvalued)
        if pe_ratio is not None:
            if pe_ratio > 50:
                risk += 20  # Very risky
            elif pe_ratio > 30:
                risk += 10  # Moderately risky
        
        # Negative earnings growth = higher risk
        if earnings_data.get('trend') == 'negative':
            risk += 15
        
        # Small cap = higher risk (volatility)
        if market_cap is not None:
            if market_cap < 1_000_000_000:  # < $1B
                risk += 15
            elif market_cap < 10_000_000_000:  # < $10B
                risk += 5
        
        return max(0, min(100, risk))


# Global instance
fundamental_engine = FundamentalEngine()

