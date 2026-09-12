"""
Ingestion Schemas

Pydantic models for data ingestion and validation.
"""

from datetime import datetime
from typing import List

from pydantic import BaseModel, Field, validator


class PriceData(BaseModel):
    """Validated price data structure."""

    ticker: str
    date: datetime
    open: float = Field(gt=0)
    high: float = Field(gt=0)
    low: float = Field(gt=0)
    close: float = Field(gt=0)
    volume: int = Field(ge=0)


class ValidationResult(BaseModel):
    """Result of data validation."""

    is_valid: bool
    errors: List[str] = []
    warnings: List[str] = []
    records_validated: int = 0
    records_passed: int = 0
    records_failed: int = 0
