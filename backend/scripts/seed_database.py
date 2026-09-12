"""
Database Seeder Script

Populates the database with initial stock data.
Uses Alpha Vantage to fetch historical price data for a predefined list of tickers.

Usage:
    python -m scripts.seed_database
"""

import asyncio
import logging
from pathlib import Path
from dotenv import load_dotenv

# Force load .env file from project root
# This must be done BEFORE importing app modules that use get_settings()
BASE_DIR = Path(__file__).resolve().parent.parent
ENV_PATH = BASE_DIR / ".env"

if ENV_PATH.exists():
    load_dotenv(dotenv_path=ENV_PATH, override=False)
else:
    print(f"WARNING: .env file not found at {ENV_PATH}")

# Now imports can happen
from app.db.session import async_session
from app.services.ingestion.data.data_fetcher import DataFetcher
from app.services.ingestion.data.data_validator import DataValidator
from app.services.ingestion.data.data_persister import DataPersister

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)


# Initial list of stocks to track (Mix of Tech, Finance, Retail)
SEED_TICKERS = [
    {"ticker": "AAPL", "name": "Apple Inc.", "sector": "Technology"},
    {"ticker": "MSFT", "name": "Microsoft Corporation", "sector": "Technology"},
    {"ticker": "GOOGL", "name": "Alphabet Inc.", "sector": "Technology"},
    {"ticker": "AMZN", "name": "Amazon.com Inc.", "sector": "Consumer Cyclical"},
    {"ticker": "NVDA", "name": "NVIDIA Corporation", "sector": "Technology"},
    {"ticker": "TSLA", "name": "Tesla Inc.", "sector": "Consumer Cyclical"},
    {"ticker": "META", "name": "Meta Platforms Inc.", "sector": "Technology"},
    {"ticker": "JPM", "name": "JPMorgan Chase & Co.", "sector": "Financial Services"},
    {"ticker": "V", "name": "Visa Inc.", "sector": "Financial Services"},
    {"ticker": "JNJ", "name": "Johnson & Johnson", "sector": "Healthcare"},
    {"ticker": "WMT", "name": "Walmart Inc.", "sector": "Consumer Defensive"},
    {"ticker": "PG", "name": "Procter & Gamble Co.", "sector": "Consumer Defensive"},
    {"ticker": "DIS", "name": "Walt Disney Co.", "sector": "Communication Services"},
    {"ticker": "NFLX", "name": "Netflix Inc.", "sector": "Communication Services"},
    {"ticker": "COIN", "name": "Coinbase Global Inc.", "sector": "Financial Services"},
]


async def seed_stock(
    session, 
    fetcher: DataFetcher, 
    validator: DataValidator, 
    persister: DataPersister, 
    stock_info: dict
):
    """Process a single stock: Fetch -> Validate -> Persist."""
    ticker = stock_info["ticker"]
    name = stock_info["name"]
    sector = stock_info["sector"]
    
    logger.info(f"\n" + "="*60)
    logger.info(f"Processing: {ticker} ({name})")
    logger.info(f"="*60)
    
    try:
        # 1. Fetch Data
        logger.info(f"[1/4] Fetching price data for {ticker}...")
        # Use "compact" (100 days) for quick seeding, "full" for production history
        df = await fetcher.fetch_daily_prices(ticker, outputsize="compact")
        logger.info(f"✅ Fetched {len(df)} days of data")
        
        # 2. Validate Data
        logger.info(f"[2/4] Validating data for {ticker}...")
        # The correct method name is validate_dataframe
        clean_df, report = validator.validate_dataframe(df, ticker)
        
        if not report.is_valid:
            logger.error(f"❌ Validation failed for {ticker}")
            for error in report.errors:
                logger.error(f"  - {error}")
            return
            
        logger.info(f"✅ Validation passed: {report.records_passed}/{report.records_validated} records")
        
        # 3. Persist Data
        logger.info(f"[3/4] Creating stock record for {ticker}...")
        result = await persister.persist_stock_with_prices(
            ticker=ticker,
            name=name,
            price_df=clean_df,
            sector=sector
        )
        
        if result.success:
            logger.info(f"✅ Persistence successful!")
            logger.info(f"  - Stocks created: {result.stocks_created}")
            logger.info(f"  - Prices inserted: {result.prices_inserted}")
        else:
            logger.error(f"❌ Persistence failed for {ticker}")
            for error in result.errors:
                logger.error(f"  - {error}")

    except Exception as e:
        logger.error(f"❌ Error processing {ticker}: {e}")


async def main():
    print("\n" + "="*60)
    print("🌱 QUANTIMENTAL DATABASE SEEDER")
    print("="*60)
    print(f"Stocks to seed: {len(SEED_TICKERS)}")
    print("Data range: compact")
    print("Rate limit delay: 12.0s between requests")
    print("Estimated time: 3.0 minutes")
    print("="*60)
    
    # Initialize services
    async with DataFetcher() as fetcher:
        validator = DataValidator()
        
        # Get database session
        async with async_session() as session:
            persister = DataPersister(session)
            
            for i, stock_info in enumerate(SEED_TICKERS):
                await seed_stock(session, fetcher, validator, persister, stock_info)
                
                # Rate limiting check
                if i < len(SEED_TICKERS) - 1:
                    print(f"\n⏳ Rate limiting: waiting 12.0s before next request...")
                    await asyncio.sleep(12.0)
    
    print("\n" + "="*60)
    print("✨ SEEDING COMPLETE")
    print("="*60)


if __name__ == "__main__":
    asyncio.run(main())
