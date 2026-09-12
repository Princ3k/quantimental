"""
Hybrid Signal Generator Service

Generates HybridSignals from QuantSignal and PsychSignal.
Combines technical and sentiment analysis into unified recommendations.
"""

import logging
from datetime import date, datetime
from typing import Optional, Dict, Any
from sqlalchemy import select, and_
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import Stock, QuantSignal, PsychSignal, HybridSignal
from app.engines.hybrid import hybrid_engine, SignalType

logger = logging.getLogger(__name__)


class HybridSignalGenerator:
    """
    Generates and persists HybridSignals from Quant and Psych signals.
    
    Workflow:
    1. Fetch QuantSignal and PsychSignal for a specific date
    2. Use HybridEngine to synthesize signals
    3. Detect "Sacred Cases" (confirmation, divergence, etc.)
    4. Generate confidence and reasons
    5. Persist HybridSignal to database
    """
    
    def __init__(self, session: AsyncSession):
        """
        Initialize the generator.
        
        Args:
            session: Async database session
        """
        self.session = session
    
    async def fetch_prerequisite_signals(
        self,
        ticker: str,
        analysis_date: date
    ) -> tuple[Optional[QuantSignal], Optional[PsychSignal]]:
        """
        Fetch QuantSignal and PsychSignal for synthesis.
        
        Args:
            ticker: Stock ticker symbol
            analysis_date: Date to fetch signals for
        
        Returns:
            (QuantSignal, PsychSignal) tuple
        """
        # Fetch QuantSignal
        quant_result = await self.session.execute(
            select(QuantSignal)
            .where(QuantSignal.ticker == ticker)
            .where(QuantSignal.date == analysis_date)
        )
        quant_signal = quant_result.scalar_one_or_none()
        
        # Fetch PsychSignal
        psych_result = await self.session.execute(
            select(PsychSignal)
            .where(PsychSignal.ticker == ticker)
            .where(PsychSignal.date == analysis_date)
        )
        psych_signal = psych_result.scalar_one_or_none()
        
        return quant_signal, psych_signal
    
    def _quant_to_rating(self, quant_signal: QuantSignal) -> int:
        """
        Convert QuantSignal to technical rating (0-100).
        
        Args:
            quant_signal: QuantSignal object
        
        Returns:
            Technical rating (0-100)
        """
        rsi = float(quant_signal.rsi or 50.0)
        
        # RSI component
        rsi_score = 100 - abs(rsi - 50) * 2
        
        # Trend component
        trend_scores = {
            'BULLISH': 75,
            'BEARISH': 35,
            'NEUTRAL': 50
        }
        trend_score = trend_scores.get(quant_signal.trend_short or 'NEUTRAL', 50)
        
        # Signal component
        signal_scores = {
            'OVERSOLD': 80,  # Potential bounce
            'OVERBOUGHT': 20,  # Potential pullback
            'NEUTRAL': 50
        }
        signal_score = signal_scores.get(quant_signal.signal or 'NEUTRAL', 50)
        
        # Weighted combination
        technical_rating = int(
            (rsi_score * 0.4) +
            (trend_score * 0.4) +
            (signal_score * 0.2)
        )
        
        return max(0, min(100, technical_rating))
    
    def _psych_to_rating(self, psych_signal: PsychSignal) -> int:
        """
        Convert PsychSignal to sentiment rating (0-100).
        
        Args:
            psych_signal: PsychSignal object
        
        Returns:
            Sentiment rating (0-100)
        """
        sentiment_score = float(psych_signal.sentiment_score or 0.0)
        
        # Convert -1.0 to +1.0 range to 0-100
        sentiment_rating = int((sentiment_score + 1.0) * 50)
        
        # Adjust based on hype velocity
        hype_velocity = float(psych_signal.hype_velocity or 1.0)
        if hype_velocity > 2.0:
            sentiment_rating = min(100, sentiment_rating + 10)  # Boost for high hype
        elif hype_velocity < 0.5:
            sentiment_rating = max(0, sentiment_rating - 10)  # Reduce for low hype
        
        return max(0, min(100, sentiment_rating))
    
    async def generate_signal_for_ticker(
        self,
        ticker: str,
        analysis_date: date
    ) -> Optional[HybridSignal]:
        """
        Generate a HybridSignal for a specific ticker and date.
        
        Args:
            ticker: Stock ticker symbol
            analysis_date: Date to generate signal for
        
        Returns:
            HybridSignal object if successful, None if prerequisites missing
        """
        logger.info(f"Generating HybridSignal for {ticker} on {analysis_date}")
        
        try:
            # 1. Fetch prerequisite signals
            quant_signal, psych_signal = await self.fetch_prerequisite_signals(
                ticker, analysis_date
            )
            
            if not quant_signal:
                logger.warning(f"No QuantSignal for {ticker} on {analysis_date}")
                return None
            
            if not psych_signal:
                logger.warning(f"No PsychSignal for {ticker} on {analysis_date}")
                return None
            
            # 2. Convert to ratings
            technical_rating = self._quant_to_rating(quant_signal)
            sentiment_rating = self._psych_to_rating(psych_signal)
            
            # 3. Prepare technical indicators for HybridEngine
            technical_indicators = {
                'rsi': float(quant_signal.rsi or 50.0),
                'trend': quant_signal.trend_short or 'NEUTRAL',
                'signal': quant_signal.signal or 'NEUTRAL'
            }
            
            # 4. Prepare sentiment data for HybridEngine
            sentiment_data = {
                'score': float(psych_signal.sentiment_score or 0.0),
                'mentions': int(psych_signal.mention_count or 0),
                'velocity': 'rising' if float(psych_signal.hype_velocity or 1.0) > 1.5 else 'falling' if float(psych_signal.hype_velocity or 1.0) < 0.7 else 'steady',
                'emotion': psych_signal.emotion or 'NEUTRAL'
            }
            
            # 5. Synthesize using HybridEngine
            synthesis = hybrid_engine.synthesize(
                technical_rating=technical_rating,
                sentiment_rating=sentiment_rating,
                technical_indicators=technical_indicators,
                sentiment_data=sentiment_data
            )
            
            # 6. Detect Sacred Cases
            case_type = hybrid_engine.detect_sacred_cases(
                technical_rating,
                sentiment_rating,
                technical_indicators
            )
            
            # 7. Create HybridSignal record
            hybrid_signal = HybridSignal(
                ticker=ticker,
                date=analysis_date,
                signal=synthesis['recommendation'].upper(),
                case_type=case_type,
                confidence=round(synthesis['confidence'] / 100.0, 3),  # Convert to 0-1 range
                reason=' | '.join(synthesis['reasons']),
                reason_short=synthesis['reasons'][0] if synthesis['reasons'] else f"Hybrid Score: {synthesis['hybrid_score']}",
                quant_signal_id=quant_signal.id,
                psych_signal_id=psych_signal.id
            )
            
            # Check if signal already exists (upsert logic)
            existing = await self.session.execute(
                select(HybridSignal)
                .where(HybridSignal.ticker == ticker)
                .where(HybridSignal.date == analysis_date)
            )
            existing_signal = existing.scalar_one_or_none()
            
            if existing_signal:
                # Update existing
                logger.info(f"Updating existing HybridSignal for {ticker} on {analysis_date}")
                existing_signal.signal = hybrid_signal.signal
                existing_signal.case_type = hybrid_signal.case_type
                existing_signal.confidence = hybrid_signal.confidence
                existing_signal.reason = hybrid_signal.reason
                existing_signal.reason_short = hybrid_signal.reason_short
                existing_signal.quant_signal_id = hybrid_signal.quant_signal_id
                existing_signal.psych_signal_id = hybrid_signal.psych_signal_id
                result_signal = existing_signal
            else:
                # Insert new
                logger.info(f"Creating new HybridSignal for {ticker} on {analysis_date}")
                self.session.add(hybrid_signal)
                result_signal = hybrid_signal
            
            await self.session.commit()
            await self.session.refresh(result_signal)
            
            logger.info(
                f"✅ HybridSignal generated: {ticker} → {synthesis['recommendation']} "
                f"(Score: {synthesis['hybrid_score']}, Confidence: {synthesis['confidence']}%)"
            )
            
            return result_signal
        
        except Exception as e:
            logger.error(f"Error generating HybridSignal for {ticker}: {e}", exc_info=True)
            await self.session.rollback()
            return None

