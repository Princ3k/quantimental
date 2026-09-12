"""
DataFetcher Service

Fetches OHLCV (Open, High, Low, Close, Volume) data from market data APIs.

Current provider: Alpha Vantage (free tier: 25 calls/day)
Future providers: Polygon.io, Yahoo Finance, IEX Cloud

Design philosophy:
- Async everything (non-blocking I/O)
- Retry logic with exponential backoff
- Rate limiting awareness
- Clean error messages for retail users
"""

import httpx
import pandas as pd
from typing import Dict, Optional, List
from datetime import datetime, timedelta
import asyncio
import logging
from pydantic import BaseModel, Field

from app.schemas.ingestion import PriceData

logger = logging.getLogger(__name__)


class DataFetcher:
    """
    Fetches historical and real-time market data from external APIs.
    
    Features:
    - Async HTTP requests
    - Automatic retries with exponential backoff
    - Multiple data source support
    - Rate limit handling
    """
    
    # Alpha Vantage constants
    ALPHA_VANTAGE_BASE_URL = "https://www.alphavantage.co/query"
    DEFAULT_TIMEOUT = 30.0
    MAX_RETRIES = 3
    RETRY_DELAY = 1.0  # seconds
    
    def __init__(self, api_key: Optional[str] = None):
        """
        Initialize the data fetcher.
        
        Args:
            api_key: Alpha Vantage API key (get from .env)
        """
        self.api_key = api_key or self._get_api_key_from_env()
        self._client: Optional[httpx.AsyncClient] = None
    
    def _get_api_key_from_env(self) -> str:
        """Load API key from environment."""
        import os
        from dotenv import load_dotenv
        
        load_dotenv()
        api_key = os.getenv("ALPHA_VANTAGE_API_KEY")
        
        if not api_key:
            logger.warning(
                "No ALPHA_VANTAGE_API_KEY found. "
                "Get one free at: https://www.alphavantage.co/support/#api-key"
            )
            # Return demo key for testing
            return "demo"
        
        return api_key
    
    async def __aenter__(self):
        """Async context manager entry."""
        self._client = httpx.AsyncClient(timeout=self.DEFAULT_TIMEOUT)
        return self
    
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Async context manager exit."""
        if self._client:
            await self._client.aclose()
    
    async def fetch_daily_prices(
        self,
        ticker: str,
        outputsize: str = "full"  # "compact" = 100 days, "full" = 20+ years
    ) -> pd.DataFrame:
        """
        Fetch daily OHLCV data for a ticker.
        
        Args:
            ticker: Stock symbol (e.g., "AAPL", "TSLA")
            outputsize: "compact" (100 days) or "full" (20+ years)
        
        Returns:
            DataFrame with columns: [date, open, high, low, close, volume]
        
        Raises:
            ValueError: If ticker is invalid or API returns error
            httpx.HTTPError: If network error occurs
        """
        if not self._client:
            raise RuntimeError("DataFetcher must be used as async context manager")
        
        ticker = ticker.upper().strip()
        logger.info(f"Fetching daily prices for {ticker} (outputsize={outputsize})")
        
        params = {
            "function": "TIME_SERIES_DAILY",
            "symbol": ticker,
            "outputsize": outputsize,
            "apikey": self.api_key,
        }
        
        # Retry logic
        for attempt in range(self.MAX_RETRIES):
            try:
                response = await self._client.get(
                    self.ALPHA_VANTAGE_BASE_URL,
                    params=params
                )
                response.raise_for_status()
                data = response.json()
                
                # Check for API errors
                if "Error Message" in data:
                    raise ValueError(f"Invalid ticker '{ticker}': {data['Error Message']}")
                
                if "Note" in data:
                    # Rate limit hit
                    logger.warning(f"Alpha Vantage rate limit hit: {data['Note']}")
                    raise ValueError(
                        "API rate limit exceeded. Alpha Vantage free tier: 25 calls/day. "
                        "Try again in 1 minute or upgrade to premium."
                    )
                
                if "Time Series (Daily)" not in data:
                    raise ValueError(f"Unexpected API response for {ticker}")
                
                # Parse time series data
                time_series = data["Time Series (Daily)"]
                df = self._parse_alpha_vantage_response(time_series, ticker)
                
                logger.info(f"Successfully fetched {len(df)} days of data for {ticker}")
                return df
            
            except httpx.HTTPError as e:
                if attempt < self.MAX_RETRIES - 1:
                    delay = self.RETRY_DELAY * (2 ** attempt)  # Exponential backoff
                    logger.warning(f"HTTP error on attempt {attempt + 1}/{self.MAX_RETRIES}. Retrying in {delay}s...")
                    await asyncio.sleep(delay)
                else:
                    logger.error(f"Failed to fetch data for {ticker} after {self.MAX_RETRIES} attempts")
                    raise
    
    def _parse_alpha_vantage_response(self, time_series: Dict, ticker: str) -> pd.DataFrame:
        """
        Parse Alpha Vantage time series into clean DataFrame.
        
        Alpha Vantage format:
        {
            "2024-01-15": {
                "1. open": "185.50",
                "2. high": "187.20",
                "3. low": "184.90",
                "4. close": "186.40",
                "5. volume": "52341600"
            },
            ...
        }
        """
        records = []
        
        for date_str, values in time_series.items():
            try:
                record = {
                    "ticker": ticker,
                    "date": pd.to_datetime(date_str),
                    "open": float(values["1. open"]),
                    "high": float(values["2. high"]),
                    "low": float(values["3. low"]),
                    "close": float(values["4. close"]),
                    "volume": int(values["5. volume"]),
                }
                records.append(record)
            except (KeyError, ValueError) as e:
                logger.warning(f"Skipping invalid record for {ticker} on {date_str}: {e}")
                continue
        
        df = pd.DataFrame(records)
        
        # Sort by date ascending (oldest first)
        df = df.sort_values("date").reset_index(drop=True)
        
        return df
    
    async def fetch_multiple_tickers(
        self,
        tickers: List[str],
        delay_between_requests: float = 12.0  # Alpha Vantage: 5 calls/min = 12s delay
    ) -> Dict[str, pd.DataFrame]:
        """
        Fetch data for multiple tickers with rate limiting.
        
        Args:
            tickers: List of stock symbols
            delay_between_requests: Seconds to wait between API calls (free tier: 12s = 5 calls/min)
        
        Returns:
            Dict mapping ticker -> DataFrame
        """
        results = {}
        
        for i, ticker in enumerate(tickers):
            try:
                df = await self.fetch_daily_prices(ticker)
                results[ticker] = df
                
                # Rate limiting (except for last request)
                if i < len(tickers) - 1:
                    logger.info(f"Waiting {delay_between_requests}s before next request (rate limiting)...")
                    await asyncio.sleep(delay_between_requests)
            
            except Exception as e:
                logger.error(f"Failed to fetch {ticker}: {e}")
                # Continue with other tickers
                continue
        
        return results
    
    async def fetch_latest_price(self, ticker: str) -> Optional[float]:
        """
        Fetch just the latest close price for a ticker.
        
        Useful for real-time updates without fetching full history.
        
        Args:
            ticker: Stock symbol
        
        Returns:
            Latest close price, or None if error
        """
        try:
            df = await self.fetch_daily_prices(ticker, outputsize="compact")
            if not df.empty:
                return float(df.iloc[-1]["close"])
        except Exception as e:
            logger.error(f"Failed to fetch latest price for {ticker}: {e}")
        
        return None


# Example usage and testing
async def main():
    """Test the DataFetcher with sample tickers."""
    print("\n=== DataFetcher Test ===\n")
    
    async with DataFetcher() as fetcher:
        # Test 1: Single ticker
        print("Test 1: Fetching AAPL...")
        try:
            df = await fetcher.fetch_daily_prices("AAPL", outputsize="compact")
            print(f"✅ Success! Fetched {len(df)} days")
            print(f"Latest: {df.iloc[-1]['date'].strftime('%Y-%m-%d')} | Close: ${df.iloc[-1]['close']:.2f}")
            print(df.tail(3))
        except Exception as e:
            print(f"❌ Error: {e}")
        
        print("\n" + "-"*50 + "\n")
        
        # Test 2: Latest price only
        print("Test 2: Fetching latest TSLA price...")
        try:
            price = await fetcher.fetch_latest_price("TSLA")
            print(f"✅ TSLA latest: ${price:.2f}")
        except Exception as e:
            print(f"❌ Error: {e}")
        
        print("\n" + "-"*50 + "\n")
        
        # Test 3: Multiple tickers (with rate limiting)
        print("Test 3: Fetching multiple tickers (MSFT, GOOGL)...")
        print("⏳ This will take ~12 seconds due to API rate limits...")
        try:
            results = await fetcher.fetch_multiple_tickers(
                ["MSFT", "GOOGL"],
                delay_between_requests=12.0
            )
            for ticker, df in results.items():
                print(f"✅ {ticker}: {len(df)} days")
        except Exception as e:
            print(f"❌ Error: {e}")


if __name__ == "__main__":
    asyncio.run(main())

