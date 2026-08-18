# backend/tools/schemas.py
from pydantic import BaseModel, field_validator
from typing import Optional
import re


class SalesSummaryParams(BaseModel):
    """Parameters for get_sales_summary"""
    period: str  # "2026-08", "2026-Q3", "2026"
    region: Optional[str] = None

    @field_validator("period")
    @classmethod
    def validate_period(cls, v: str) -> str:
        # Accept: YYYY, YYYY-MM, YYYY-QN
        if re.match(r"^\d{4}$", v):
            return v
        if re.match(r"^\d{4}-\d{2}$", v):
            return v
        if re.match(r"^\d{4}-Q[1-4]$", v):
            return v
        raise ValueError(f"Invalid period format: {v!r}. Use YYYY, YYYY-MM, or YYYY-QN")


class SalesTargetParams(BaseModel):
    """Parameters for get_sales_targets"""
    vendor_id: Optional[str] = None
    year: int = 2026
    month: Optional[int] = None

    @field_validator("month")
    @classmethod
    def validate_month(cls, v: Optional[int]) -> Optional[int]:
        if v is not None and not (1 <= v <= 12):
            raise ValueError(f"month must be 1-12, got {v}")
        return v


class SalesForecastParams(BaseModel):
    """Parameters for get_sales_forecast"""
    start_period: str  # "2026-09"
    end_period: str    # "2026-12"
    region: Optional[str] = None

    @field_validator("start_period", "end_period")
    @classmethod
    def validate_period(cls, v: str) -> str:
        if not re.match(r"^\d{4}-\d{2}$", v):
            raise ValueError(f"Period must be YYYY-MM, got {v!r}")
        return v


class CustomerInsightsParams(BaseModel):
    """Parameters for get_customer_insights"""
    customer_id: str

    @field_validator("customer_id")
    @classmethod
    def validate_customer_id(cls, v: str) -> str:
        if not v.strip():
            raise ValueError("customer_id cannot be empty")
        return v.strip()


class SalesPerformanceParams(BaseModel):
    """Parameters for get_sales_performance"""
    period: str  # "2026-08"
    region: Optional[str] = None

    @field_validator("period")
    @classmethod
    def validate_period(cls, v: str) -> str:
        if not re.match(r"^\d{4}-\d{2}$", v):
            raise ValueError(f"Period must be YYYY-MM, got {v!r}")
        return v


class InventoryParams(BaseModel):
    """Parameters for get_inventory_by_sales"""
    material_code: Optional[str] = None
    region: Optional[str] = None
