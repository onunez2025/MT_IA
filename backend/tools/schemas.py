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


# ── Nuevas herramientas Fase 0+ ────────────────────────────────────────────

class GapToTargetParams(BaseModel):
    """Parameters for get_gap_to_target"""
    vendor_id: Optional[str] = None
    year: int = 2026
    month: Optional[int] = None

    @field_validator("month")
    @classmethod
    def validate_month(cls, v: Optional[int]) -> Optional[int]:
        if v is not None and not (1 <= v <= 12):
            raise ValueError(f"month must be 1-12, got {v}")
        return v


class InactiveCustomersParams(BaseModel):
    """Parameters for get_inactive_customers"""
    days: int = 60
    vendor_id: Optional[str] = None
    region: Optional[str] = None
    top_n: int = 20

    @field_validator("days")
    @classmethod
    def validate_days(cls, v: int) -> int:
        if not (1 <= v <= 365):
            raise ValueError(f"days must be 1-365, got {v}")
        return v

    @field_validator("top_n")
    @classmethod
    def validate_top_n(cls, v: int) -> int:
        if not (1 <= v <= 100):
            raise ValueError(f"top_n must be 1-100, got {v}")
        return v


class SalesByChannelParams(BaseModel):
    """Parameters for get_sales_by_channel"""
    period: str  # "2026-08" or "2026"
    region: Optional[str] = None

    @field_validator("period")
    @classmethod
    def validate_period(cls, v: str) -> str:
        if re.match(r"^\d{4}$", v):
            return v
        if re.match(r"^\d{4}-\d{2}$", v):
            return v
        raise ValueError(f"Invalid period: {v!r}. Use YYYY or YYYY-MM")


class MonthlyTrendParams(BaseModel):
    """Parameters for get_monthly_trend"""
    months: int = 6
    region: Optional[str] = None

    @field_validator("months")
    @classmethod
    def validate_months(cls, v: int) -> int:
        if not (2 <= v <= 24):
            raise ValueError(f"months must be 2-24, got {v}")
        return v


class NewCustomersParams(BaseModel):
    """Parameters for get_new_customers"""
    period: str  # "2026-08" or "2026"
    vendor_id: Optional[str] = None
    region: Optional[str] = None

    @field_validator("period")
    @classmethod
    def validate_period(cls, v: str) -> str:
        if re.match(r"^\d{4}$", v):
            return v
        if re.match(r"^\d{4}-\d{2}$", v):
            return v
        raise ValueError(f"Invalid period: {v!r}. Use YYYY or YYYY-MM")


class TopMarginProductsParams(BaseModel):
    """Parameters for get_top_margin_products"""
    period: Optional[str] = None
    top_n: int = 10
    category: Optional[str] = None

    @field_validator("top_n")
    @classmethod
    def validate_top_n(cls, v: int) -> int:
        if not (1 <= v <= 50):
            raise ValueError(f"top_n must be 1-50, got {v}")
        return v


class ForecastReportParams(BaseModel):
    """Parameters for generate_forecast_report"""
    year: int = 2026
    month: int = 9
    vendor_id: Optional[str] = None

    @field_validator("month")
    @classmethod
    def validate_month(cls, v: int) -> int:
        if not (1 <= v <= 12):
            raise ValueError(f"month must be 1-12, got {v}")
        return v
