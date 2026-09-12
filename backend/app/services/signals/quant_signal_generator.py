"""
Quant Signal Generator Service

Generates QuantSignals from technical indicators.
Calculates technical signals and persists them to the database.
"""

import logging
from datetime import date, datetime
from typing import Optional, Dict, Any
from sqlalchemy import select, and_
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import Stock, QuantSignal, DailyPrice
from app.engines.quant import quant_engine
import numpy as np

logger = logging.getLogger(__name__)


class QuantSignalGenerator:
    """
    Generates and persists QuantSignals from technical indicators.
    
    Workflow:
    1. Fetch price data (DailyPrice records)
    2. Calculate technical indicators using QuantEngine
    3. Determine signal (OVERSOLD, OVERBOUGHT, NEUTRAL)
    4. Determine trends (short-term and long-term)
    5. Persist QuantSignal to database
    """
    
    def __init__(self, session: AsyncSession):
        """
        Initialize the generator.
        
        Args:
            session: Async database session
        """
        self.session = session
    
    async def fetch_price_data(
        self,
        ticker: str,
        days: int = 250
    ) -> Optional[Dict[str, Any]]:
        """
        Fetch price data for technical analysis.
        
        Args:
            ticker: Stock ticker symbol
            days: Number of days of historical data to fetch
        
        Returns:
            Dictionary with 'closes', 'highs', 'lows', 'volumes' arrays, or None
        """
        try:
            cutoff_date = datetime.utcnow().date()
            
            result = await self.session.execute(
                select(DailyPrice)
                .where(DailyPrice.ticker == ticker)
                .where(DailyPrice.date <= cutoff_date)
                .order_by(DailyPrice.date.desc())
                .limit(days)
            )
            prices = result.scalars().all()
            
            if not prices or len(prices) < 50:
                logger.warning(f"Insufficient price data for {ticker}: {len(prices)} records")
                return None
            
            # Reverse to chronological order (oldest first)
            prices = list(reversed(prices))
            
            # Extract arrays
            closes = np.array([float(p.close) for p in prices])
            highs = np.array([float(p.high) for p in prices])
            lows = np.array([float(p.low) for p in prices])
            volumes = np.array([float(p.volume) for p in prices if p.volume])
            
            return {
                'closes': closes,
                'highs': highs,
                'lows': lows,
                'volumes': volumes if len(volumes) > 0 else None
            }
        
        except Exception as e:
            logger.error(f"Error fetching price data for {ticker}: {e}")
            return None
    
    def determine_signal(self, rsi: float) -> str:
        """
        Determine signal based on RSI.
        
        Args:
            rsi: RSI value (0-100)
        
        Returns:
            Signal string: OVERSOLD, OVERBOUGHT, or NEUTRAL
        """
        if rsi > 70:
            return "OVERBOUGHT"
        elif rsi < 30:
            return "OVERSOLD"
        else:
            return "NEUTRAL"
    
    def determine_trends(
        self,
        closes: np.ndarray,
        sma_50: float,
        sma_200: Optional[float]
    ) -> tuple[str, str]:
        """
        Determine short-term and long-term trends.
        
        Args:
            closes: Array of closing prices
            sma_50: 50-day moving average
            sma_200: 200-day moving average (optional)
        
        Returns:
            (trend_short, trend_long) tuple
        """
        current_price = float(closes[-1])
        
        # Short-term trend (price vs MA50)
        if current_price > sma_50 * 1.02:  # 2% above
            trend_short = "BULLISH"
        elif current_price < sma_50 * 0.98:  # 2% below
            trend_short = "BEARISH"
        else:
            trend_short = "NEUTRAL"
        
        # Long-term trend (MA50 vs MA200, or price vs MA50 if no MA200)
        if sma_200 is not None:
            if sma_50 > sma_200 * 1.02:
                trend_long = "BULLISH"
            elif sma_50 < sma_200 * 0.98:
                trend_long = "BEARISH"
            else:
                trend_long = "NEUTRAL"
        else:
            # Fallback to short-term trend
            trend_long = trend_short
        
        return trend_short, trend_long
    
    async def generate_signal_for_ticker(
        self,
        ticker: str,
        analysis_date: date
    ) -> Optional[QuantSignal]:
        """
        Generate a QuantSignal for a specific ticker and date.
        
        Args:
            ticker: Stock ticker symbol
            analysis_date: Date to generate signal for
        
        Returns:
            QuantSignal object if successful, None if no data
        """
        logger.info(f"Generating QuantSignal for {ticker} on {analysis_date}")
        
        try:
            # 1. Fetch price data
            price_data = await self.fetch_price_data(ticker)
            
            if not price_data:
                logger.warning(f"No price data for {ticker}")
                return None
            
            # 2. Calculate technical indicators
            indicators = quant_engine.calculate_indicators(
                price_data['closes'],
                price_data.get('highs'),
                price_data.get('lows'),
                price_data.get('volumes')
            )
            
            rsi = indicators.get('rsi', 50.0)
            sma_50 = indicators.get('sma_50', 0.0)
            sma_200 = indicators.get('sma_200', None)
            
            # 3. Determine signal
            signal = self.determine_signal(rsi)
            
            # 4. Determine trends
            trend_short, trend_long = self.determine_trends(
                price_data['closes'],
                sma_50,
                sma_200
            )
            
            # 5. Create QuantSignal record
            quant_signal = QuantSignal(
                ticker=ticker,
                date=analysis_date,
                rsi=round(rsi, 2),
                ma_50=round(sma_50, 2),
                ma_200=round(sma_200, 2) if sma_200 else None,
                signal=signal,
                trend_short=trend_short,
                trend_long=trend_long
            )
            
            # Check if signal already exists (upsert logic)
            existing = await self.session.execute(
                select(QuantSignal)
                .where(QuantSignal.ticker == ticker)
                .where(QuantSignal.date == analysis_date)
            )
            existing_signal = existing.scalar_one_or_none()
            
            if existing_signal:
                # Update existing
                logger.info(f"Updating existing QuantSignal for {ticker} on {analysis_date}")
                existing_signal.rsi = quant_signal.rsi
                existing_signal.ma_50 = quant_signal.ma_50
                existing_signal.ma_200 = quant_signal.ma_200
                existing_signal.signal = quant_signal.signal
                existing_signal.trend_short = quant_signal.trend_short
                existing_signal.trend_long = quant_signal.trend_long
                result_signal = existing_signal
            else:
                # Insert new
                logger.info(f"Creating new QuantSignal for {ticker} on {analysis_date}")
                self.session.add(quant_signal)
                result_signal = quant_signal
            
            await self.session.commit()
            await self.session.refresh(result_signal)
            
            logger.info(
                f"✅ QuantSignal generated: {ticker} → {signal} "
                f"(RSI={rsi:.2f}, Short={trend_short}, Long={trend_long})"
            )
            
            return result_signal
        
        except Exception as e:
            logger.error(f"Error generating QuantSignal for {ticker}: {e}", exc_info=True)
            await self.session.rollback()
            return None

