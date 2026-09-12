"""
DataValidator Service

Validates market data quality before persistence.

Why validation matters:
- Bad data = bad signals = lost trust
- APIs can return corrupted, stale, or anomalous data
- Catch issues early, before they poison the engines

Validation rules:
1. No missing required fields
2. Prices are positive
3. High >= Low >= 0
4. Volume >= 0
5. No duplicate dates for same ticker
6. No prices with >50% single-day moves (likely data errors)
7. Dates are reasonable (not future, not pre-1900)
"""

import pandas as pd
from typing import Dict, List, Tuple
from datetime import datetime, timedelta
import logging
from pydantic import BaseModel, validator

from app.schemas.ingestion import ValidationResult

logger = logging.getLogger(__name__)


class DataValidator:
    """
    Validates OHLCV data quality.
    
    Philosophy: Be strict but informative.
    - Reject clearly bad data (missing prices, negative values)
    - Warn about suspicious data (extreme moves, gaps)
    - Always explain what went wrong
    """
    
    # Validation thresholds
    MAX_SINGLE_DAY_MOVE = 0.50  # 50% move in one day (likely error)
    MAX_FUTURE_DAYS = 1  # Allow 1 day in future (timezone issues)
    MIN_YEAR = 1900
    
    def validate_dataframe(self, df: pd.DataFrame, ticker: str) -> Tuple[pd.DataFrame, ValidationResult]:
        """
        Validate a DataFrame of OHLCV data.
        
        Args:
            df: DataFrame with columns [ticker, date, open, high, low, close, volume]
            ticker: Stock symbol (for logging)
        
        Returns:
            Tuple of (cleaned_df, validation_result)
            - cleaned_df: DataFrame with invalid rows removed
            - validation_result: Detailed validation report
        """
        if df.empty:
            return df, ValidationResult(
                is_valid=False,
                errors=["DataFrame is empty"],
                records_validated=0
            )
        
        errors = []
        warnings = []
        initial_count = len(df)
        
        # Required columns
        required_cols = {"ticker", "date", "open", "high", "low", "close", "volume"}
        missing_cols = required_cols - set(df.columns)
        if missing_cols:
            return df, ValidationResult(
                is_valid=False,
                errors=[f"Missing required columns: {missing_cols}"],
                records_validated=initial_count
            )
        
        # Create a copy for cleaning
        clean_df = df.copy()
        
        # Rule 1: Remove rows with missing values
        null_counts = clean_df[["open", "high", "low", "close", "volume"]].isnull().sum()
        if null_counts.sum() > 0:
            clean_df = clean_df.dropna(subset=["open", "high", "low", "close", "volume"])
            warnings.append(f"Removed {initial_count - len(clean_df)} rows with missing values")
        
        if clean_df.empty:
            return clean_df, ValidationResult(
                is_valid=False,
                errors=["All rows contained missing values"],
                records_validated=initial_count,
                records_failed=initial_count
            )
        
        # Rule 2: Prices must be positive
        negative_prices = (
            (clean_df["open"] <= 0) |
            (clean_df["high"] <= 0) |
            (clean_df["low"] <= 0) |
            (clean_df["close"] <= 0)
        )
        if negative_prices.any():
            bad_count = negative_prices.sum()
            clean_df = clean_df[~negative_prices]
            errors.append(f"Removed {bad_count} rows with non-positive prices")
        
        # Rule 3: High >= Low
        invalid_ranges = clean_df["high"] < clean_df["low"]
        if invalid_ranges.any():
            bad_count = invalid_ranges.sum()
            clean_df = clean_df[~invalid_ranges]
            errors.append(f"Removed {bad_count} rows where high < low")
        
        # Rule 4: Volume must be non-negative
        negative_volume = clean_df["volume"] < 0
        if negative_volume.any():
            bad_count = negative_volume.sum()
            clean_df = clean_df[~negative_volume]
            errors.append(f"Removed {bad_count} rows with negative volume")
        
        # Rule 5: Check for duplicate dates
        duplicates = clean_df.duplicated(subset=["ticker", "date"], keep="first")
        if duplicates.any():
            dup_count = duplicates.sum()
            clean_df = clean_df[~duplicates]
            warnings.append(f"Removed {dup_count} duplicate date entries")
        
        # Rule 6: Check for extreme single-day moves (likely data errors)
        clean_df = clean_df.sort_values("date").reset_index(drop=True)
        if len(clean_df) > 1:
            clean_df["pct_change"] = clean_df["close"].pct_change().abs()
            extreme_moves = clean_df["pct_change"] > self.MAX_SINGLE_DAY_MOVE
            
            if extreme_moves.any():
                extreme_count = extreme_moves.sum()
                extreme_dates = clean_df[extreme_moves]["date"].tolist()
                warnings.append(
                    f"Found {extreme_count} extreme moves (>{self.MAX_SINGLE_DAY_MOVE*100}% in one day). "
                    f"First occurrence: {extreme_dates[0] if extreme_dates else 'N/A'}. "
                    "This might indicate data quality issues."
                )
            
            # Remove the temporary column
            clean_df = clean_df.drop(columns=["pct_change"])
        
        # Rule 7: Check date ranges
        max_future_date = datetime.now() + timedelta(days=self.MAX_FUTURE_DAYS)
        min_valid_date = datetime(self.MIN_YEAR, 1, 1)
        
        future_dates = clean_df["date"] > max_future_date
        if future_dates.any():
            bad_count = future_dates.sum()
            clean_df = clean_df[~future_dates]
            errors.append(f"Removed {bad_count} rows with future dates")
        
        old_dates = clean_df["date"] < min_valid_date
        if old_dates.any():
            bad_count = old_dates.sum()
            clean_df = clean_df[~old_dates]
            errors.append(f"Removed {bad_count} rows with dates before {self.MIN_YEAR}")
        
        # Final check: Do we have enough data left?
        if clean_df.empty:
            return clean_df, ValidationResult(
                is_valid=False,
                errors=["All rows failed validation"] + errors,
                warnings=warnings,
                records_validated=initial_count,
                records_failed=initial_count
            )
        
        # Additional checks for data quality
        self._check_data_gaps(clean_df, ticker, warnings)
        self._check_price_consistency(clean_df, ticker, warnings)
        
        # Build result
        final_count = len(clean_df)
        result = ValidationResult(
            is_valid=True,
            errors=errors,
            warnings=warnings,
            records_validated=initial_count,
            records_passed=final_count,
            records_failed=initial_count - final_count
        )
        
        logger.info(
            f"Validation complete for {ticker}: "
            f"{result.records_passed}/{result.records_validated} passed"
        )
        
        if errors:
            logger.warning(f"Errors: {'; '.join(errors)}")
        if warnings:
            logger.info(f"Warnings: {'; '.join(warnings)}")
        
        return clean_df, result
    
    def _check_data_gaps(self, df: pd.DataFrame, ticker: str, warnings: List[str]):
        """Check for suspicious gaps in the date series."""
        if len(df) < 2:
            return
        
        df_sorted = df.sort_values("date")
        date_diffs = df_sorted["date"].diff()
        
        # Find gaps > 10 days (weekends/holidays are normal, but 10+ days is suspicious)
        large_gaps = date_diffs > timedelta(days=10)
        
        if large_gaps.any():
            gap_count = large_gaps.sum()
            warnings.append(
                f"Found {gap_count} date gaps >10 days. "
                "Data may be incomplete."
            )
    
    def _check_price_consistency(self, df: pd.DataFrame, ticker: str, warnings: List[str]):
        """Check for basic price consistency rules."""
        # Check: Close should generally be between Low and High
        close_out_of_range = (df["close"] > df["high"]) | (df["close"] < df["low"])
        
        if close_out_of_range.any():
            bad_count = close_out_of_range.sum()
            warnings.append(
                f"Found {bad_count} rows where close price is outside high/low range. "
                "This might indicate data quality issues."
            )
        
        # Check: Open should generally be between Low and High
        open_out_of_range = (df["open"] > df["high"]) | (df["open"] < df["low"])
        
        if open_out_of_range.any():
            bad_count = open_out_of_range.sum()
            warnings.append(
                f"Found {bad_count} rows where open price is outside high/low range. "
                "This might indicate data quality issues."
            )
    
    def validate_single_record(self, record: Dict) -> Tuple[bool, List[str]]:
        """
        Validate a single price record.
        
        Args:
            record: Dict with keys [ticker, date, open, high, low, close, volume]
        
        Returns:
            Tuple of (is_valid, error_messages)
        """
        errors = []
        
        # Required fields
        required = ["ticker", "date", "open", "high", "low", "close", "volume"]
        for field in required:
            if field not in record or record[field] is None:
                errors.append(f"Missing required field: {field}")
        
        if errors:
            return False, errors
        
        # Type and value checks
        try:
            open_price = float(record["open"])
            high = float(record["high"])
            low = float(record["low"])
            close = float(record["close"])
            volume = int(record["volume"])
            
            if open_price <= 0:
                errors.append("Open price must be positive")
            if high <= 0:
                errors.append("High price must be positive")
            if low <= 0:
                errors.append("Low price must be positive")
            if close <= 0:
                errors.append("Close price must be positive")
            if volume < 0:
                errors.append("Volume must be non-negative")
            if high < low:
                errors.append(f"High ({high}) must be >= Low ({low})")
            if close > high or close < low:
                errors.append(f"Close ({close}) must be between High ({high}) and Low ({low})")
        
        except (ValueError, TypeError) as e:
            errors.append(f"Invalid data type: {e}")
        
        return len(errors) == 0, errors


# Example usage and testing
if __name__ == "__main__":
    print("\n=== DataValidator Test ===\n")
    
    validator = DataValidator()
    
    # Test 1: Valid data
    print("Test 1: Valid data")
    valid_data = pd.DataFrame([
        {"ticker": "AAPL", "date": pd.Timestamp("2024-01-15"), "open": 185.0, "high": 187.0, "low": 184.0, "close": 186.0, "volume": 1000000},
        {"ticker": "AAPL", "date": pd.Timestamp("2024-01-16"), "open": 186.0, "high": 188.0, "low": 185.0, "close": 187.0, "volume": 1100000},
    ])
    
    clean_df, result = validator.validate_dataframe(valid_data, "AAPL")
    print(f"Valid: {result.is_valid}")
    print(f"Passed: {result.records_passed}/{result.records_validated}")
    print(f"Errors: {result.errors}")
    print(f"Warnings: {result.warnings}")
    
    print("\n" + "-"*50 + "\n")
    
    # Test 2: Invalid data (negative prices)
    print("Test 2: Invalid data (negative prices)")
    invalid_data = pd.DataFrame([
        {"ticker": "AAPL", "date": pd.Timestamp("2024-01-15"), "open": -185.0, "high": 187.0, "low": 184.0, "close": 186.0, "volume": 1000000},
        {"ticker": "AAPL", "date": pd.Timestamp("2024-01-16"), "open": 186.0, "high": 180.0, "low": 185.0, "close": 187.0, "volume": 1100000},  # high < low
    ])
    
    clean_df, result = validator.validate_dataframe(invalid_data, "AAPL")
    print(f"Valid: {result.is_valid}")
    print(f"Passed: {result.records_passed}/{result.records_validated}")
    print(f"Errors: {result.errors}")
    
    print("\n" + "-"*50 + "\n")
    
    # Test 3: Data with duplicates
    print("Test 3: Data with duplicate dates")
    duplicate_data = pd.DataFrame([
        {"ticker": "AAPL", "date": pd.Timestamp("2024-01-15"), "open": 185.0, "high": 187.0, "low": 184.0, "close": 186.0, "volume": 1000000},
        {"ticker": "AAPL", "date": pd.Timestamp("2024-01-15"), "open": 185.0, "high": 187.0, "low": 184.0, "close": 186.0, "volume": 1000000},  # Duplicate
        {"ticker": "AAPL", "date": pd.Timestamp("2024-01-16"), "open": 186.0, "high": 188.0, "low": 185.0, "close": 187.0, "volume": 1100000},
    ])
    
    clean_df, result = validator.validate_dataframe(duplicate_data, "AAPL")
    print(f"Valid: {result.is_valid}")
    print(f"Passed: {result.records_passed}/{result.records_validated}")
    print(f"Warnings: {result.warnings}")

