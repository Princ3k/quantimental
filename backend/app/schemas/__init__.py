"""
Quantimental Schemas Package

Centralized Pydantic models for data validation and API contracts.

Usage:
    from app.schemas import PriceData, ValidationResult
    from app.schemas import AnalyzeRequest, AnalyzeMultipleRequest
"""

from app.schemas.ingestion import PriceData, ValidationResult
from app.schemas.api import AnalyzeRequest, AnalyzeMultipleRequest

__all__ = [
    "PriceData",
    "ValidationResult",
    "AnalyzeRequest",
    "AnalyzeMultipleRequest",
]
