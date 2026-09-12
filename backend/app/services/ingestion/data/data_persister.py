"""
DataPersister Service

Saves validated market data to the database.

Strategy:
- Upsert logic (insert new, update existing)
- Batch operations for efficiency
- Transaction safety (all-or-nothing)
- Conflict resolution (duplicate dates)

For retail users: This is the layer that ensures your data is safely stored
and always available when the engines need it.
"""

import pandas as pd
from typing import List, Dict, Optional
from datetime import datetime
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, and_
from sqlalchemy.dialects.postgresql import insert
import logging

from app.db.models import Stock, DailyPrice

logger = logging.getLogger(__name__)


class PersistResult:
    """Result of a persistence operation."""
    def __init__(self):
        self.stocks_created = 0
        self.stocks_updated = 0
        self.prices_inserted = 0
        self.prices_updated = 0
        self.errors: List[str] = []
    
    @property
    def success(self) -> bool:
        return len(self.errors) == 0
    
    def __str__(self) -> str:
        return (
            f"PersistResult(stocks: {self.stocks_created} created, {self.stocks_updated} updated | "
            f"prices: {self.prices_inserted} inserted, {self.prices_updated} updated | "
            f"errors: {len(self.errors)})"
        )


class DataPersister:
    """
    Persists validated market data to PostgreSQL.
    
    Features:
    - Async database operations
    - Upsert logic (PostgreSQL ON CONFLICT)
    - Batch inserts for performance
    - Transaction safety
    """
    
    BATCH_SIZE = 1000  # Insert in batches of 1000 rows
    
    def __init__(self, session: AsyncSession):
        """
        Initialize the persister.
        
        Args:
            session: SQLAlchemy async session
        """
        self.session = session
    
    async def persist_stock(self, ticker: str, name: str, sector: Optional[str] = None) -> Stock:
        """
        Create or update a stock record.
        
        Args:
            ticker: Stock symbol (e.g., "AAPL")
            name: Company name (e.g., "Apple Inc.")
            sector: Industry sector (e.g., "Technology")
        
        Returns:
            Stock model instance
        """
        ticker = ticker.upper().strip()
        
        # Check if stock already exists
        result = await self.session.execute(
            select(Stock).where(Stock.ticker == ticker)
        )
        stock = result.scalar_one_or_none()
        
        if stock:
            # Update existing
            stock.name = name
            if sector:
                stock.sector = sector
            logger.info(f"Updated stock: {ticker}")
        else:
            # Create new
            stock = Stock(ticker=ticker, name=name, sector=sector)
            self.session.add(stock)
            logger.info(f"Created stock: {ticker}")
        
        await self.session.flush()
        return stock
    
    async def persist_prices(
        self,
        df: pd.DataFrame,
        ticker: str,
        batch_size: Optional[int] = None
    ) -> PersistResult:
        """
        Persist OHLCV price data for a ticker.
        
        Uses PostgreSQL's ON CONFLICT DO UPDATE for upsert logic.
        
        Args:
            df: DataFrame with columns [date, open, high, low, close, volume]
            ticker: Stock symbol
            batch_size: Number of rows per batch (default: BATCH_SIZE)
        
        Returns:
            PersistResult with operation statistics
        """
        result = PersistResult()
        
        if df.empty:
            result.errors.append("DataFrame is empty")
            return result
        
        ticker = ticker.upper().strip()
        batch_size = batch_size or self.BATCH_SIZE
        
        try:
            # Ensure stock exists
            stock_result = await self.session.execute(
                select(Stock).where(Stock.ticker == ticker)
            )
            stock = stock_result.scalar_one_or_none()
            
            if not stock:
                result.errors.append(f"Stock {ticker} not found. Create stock first.")
                return result
            
            # Prepare records for insert
            records = []
            for _, row in df.iterrows():
                records.append({
                    "ticker": ticker,
                    "date": row["date"].date() if isinstance(row["date"], pd.Timestamp) else row["date"],
                    "open": float(row["open"]),
                    "high": float(row["high"]),
                    "low": float(row["low"]),
                    "close": float(row["close"]),
                    "volume": int(row["volume"]),
                })
            
            # Process in batches
            total_inserted = 0
            total_updated = 0
            
            for i in range(0, len(records), batch_size):
                batch = records[i:i + batch_size]
                
                # Use PostgreSQL's INSERT ... ON CONFLICT DO UPDATE
                stmt = insert(DailyPrice).values(batch)
                
                # On conflict (ticker, date), update the values
                stmt = stmt.on_conflict_do_update(
                    index_elements=["ticker", "date"],
                    set_={
                        "open": stmt.excluded.open,
                        "high": stmt.excluded.high,
                        "low": stmt.excluded.low,
                        "close": stmt.excluded.close,
                        "volume": stmt.excluded.volume,
                    }
                )
                
                await self.session.execute(stmt)
                
                logger.info(f"Processed batch {i//batch_size + 1}: {len(batch)} records")
                total_inserted += len(batch)
            
            await self.session.commit()
            
            result.prices_inserted = total_inserted
            logger.info(f"Successfully persisted {total_inserted} price records for {ticker}")
        
        except Exception as e:
            await self.session.rollback()
            error_msg = f"Failed to persist prices for {ticker}: {str(e)}"
            logger.error(error_msg)
            result.errors.append(error_msg)
        
        return result
    
    async def persist_stock_with_prices(
        self,
        ticker: str,
        name: str,
        price_df: pd.DataFrame,
        sector: Optional[str] = None
    ) -> PersistResult:
        """
        Convenience method: Create stock and persist prices in one transaction.
        
        Args:
            ticker: Stock symbol
            name: Company name
            price_df: DataFrame with price data
            sector: Industry sector (optional)
        
        Returns:
            PersistResult with operation statistics
        """
        result = PersistResult()
        
        try:
            # Create/update stock
            stock = await self.persist_stock(ticker, name, sector)
            result.stocks_created = 1
            
            # Persist prices
            price_result = await self.persist_prices(price_df, ticker)
            result.prices_inserted = price_result.prices_inserted
            result.prices_updated = price_result.prices_updated
            result.errors.extend(price_result.errors)
            
            logger.info(f"Successfully persisted stock and prices for {ticker}")
        
        except Exception as e:
            error_msg = f"Failed to persist stock with prices for {ticker}: {str(e)}"
            logger.error(error_msg)
            result.errors.append(error_msg)
        
        return result
    
    async def get_latest_date(self, ticker: str) -> Optional[datetime]:
        """
        Get the latest date we have price data for a ticker.
        
        Useful for incremental updates (only fetch new data).
        
        Args:
            ticker: Stock symbol
        
        Returns:
            Latest date in database, or None if no data
        """
        ticker = ticker.upper().strip()
        
        result = await self.session.execute(
            select(DailyPrice.date)
            .where(DailyPrice.ticker == ticker)
            .order_by(DailyPrice.date.desc())
            .limit(1)
        )
        
        latest = result.scalar_one_or_none()
        return latest
    
    async def count_price_records(self, ticker: str) -> int:
        """
        Count how many price records we have for a ticker.
        
        Args:
            ticker: Stock symbol
        
        Returns:
            Number of price records
        """
        ticker = ticker.upper().strip()
        
        result = await self.session.execute(
            select(DailyPrice)
            .where(DailyPrice.ticker == ticker)
        )
        
        return len(result.all())
    
    async def delete_prices_for_ticker(self, ticker: str) -> int:
        """
        Delete all price records for a ticker.
        
        Use with caution! Mainly for testing/cleanup.
        
        Args:
            ticker: Stock symbol
        
        Returns:
            Number of records deleted
        """
        ticker = ticker.upper().strip()
        
        result = await self.session.execute(
            select(DailyPrice).where(DailyPrice.ticker == ticker)
        )
        records = result.scalars().all()
        count = len(records)
        
        for record in records:
            await self.session.delete(record)
        
        await self.session.commit()
        
        logger.info(f"Deleted {count} price records for {ticker}")
        return count


# Example usage
async def example_usage():
    """
    Example of how to use DataPersister.
    
    Note: This requires an active database connection.
    See app/db/session.py for database setup.
    """
    from app.db.session import get_async_session
    
    async for session in get_async_session():
        persister = DataPersister(session)
        
        # Create a stock
        await persister.persist_stock(
            ticker="AAPL",
            name="Apple Inc.",
            sector="Technology"
        )
        
        # Create sample price data
        sample_data = pd.DataFrame([
            {
                "date": pd.Timestamp("2024-01-15"),
                "open": 185.0,
                "high": 187.0,
                "low": 184.0,
                "close": 186.0,
                "volume": 52000000
            },
            {
                "date": pd.Timestamp("2024-01-16"),
                "open": 186.0,
                "high": 188.0,
                "low": 185.0,
                "close": 187.5,
                "volume": 48000000
            }
        ])
        
        # Persist prices
        result = await persister.persist_prices(sample_data, "AAPL")
        print(result)
        
        break  # Only use first session


if __name__ == "__main__":
    import asyncio
    print("\n=== DataPersister Example ===")
    print("Note: This requires database connection. See example_usage() for details.")

