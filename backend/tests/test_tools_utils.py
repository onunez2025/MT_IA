# backend/tests/test_tools_utils.py
import time
import pytest
from tools.utils import aggregate_sales_data, format_currency, format_percentage, SimpleCache
from tools.schemas import (
    SalesSummaryParams, SalesTargetParams, SalesForecastParams,
    CustomerInsightsParams, SalesPerformanceParams, InventoryParams
)


# --- aggregate_sales_data ---

def test_aggregate_empty_rows():
    result = aggregate_sales_data([])
    assert result["total_sales"] == 0.0
    assert result["num_orders"] == 0
    assert result["num_customers"] == 0
    assert result["avg_order_value"] == 0.0


def test_aggregate_basic():
    rows = [
        {"DE_neto": 1000, "VC_solicitante_codigo": "CLI1"},
        {"DE_neto": 2000, "VC_solicitante_codigo": "CLI2"},
        {"DE_neto": 1500, "VC_solicitante_codigo": "CLI1"},
    ]
    result = aggregate_sales_data(rows)
    assert result["total_sales"] == 4500.0
    assert result["num_orders"] == 3
    assert result["num_customers"] == 2  # CLI1 deduplicated
    assert result["avg_order_value"] == 1500.0


def test_aggregate_none_values():
    """Rows with None DE_neto treated as 0"""
    rows = [
        {"DE_neto": None, "VC_solicitante_codigo": "CLI1"},
        {"DE_neto": 500, "VC_solicitante_codigo": "CLI2"},
    ]
    result = aggregate_sales_data(rows)
    assert result["total_sales"] == 500.0


def test_aggregate_missing_customer_code():
    """Rows missing VC_solicitante_codigo still counted as orders"""
    rows = [{"DE_neto": 100}, {"DE_neto": 200}]
    result = aggregate_sales_data(rows)
    assert result["num_orders"] == 2
    assert result["num_customers"] == 0


# --- format_currency ---

def test_format_currency_pen():
    assert format_currency(1500.5, "PEN") == "S/ 1,500.50"


def test_format_currency_usd():
    assert format_currency(999.99, "USD") == "$ 999.99"


def test_format_currency_default_pen():
    assert format_currency(0) == "S/ 0.00"


# --- format_percentage ---

def test_format_percentage():
    assert format_percentage(87.5) == "87.50%"


def test_format_percentage_zero():
    assert format_percentage(0) == "0.00%"


# --- SimpleCache ---

def test_cache_set_get():
    cache = SimpleCache(ttl_seconds=60)
    cache.set("k1", "v1")
    assert cache.get("k1") == "v1"


def test_cache_miss():
    cache = SimpleCache(ttl_seconds=60)
    assert cache.get("nonexistent") is None


def test_cache_expiry():
    cache = SimpleCache(ttl_seconds=1)
    cache.set("k", "val")
    assert cache.get("k") == "val"
    time.sleep(1.1)
    assert cache.get("k") is None  # Expired


def test_cache_clear():
    cache = SimpleCache(ttl_seconds=60)
    cache.set("a", 1)
    cache.set("b", 2)
    assert cache.size() == 2
    cache.clear()
    assert cache.size() == 0


# --- Schemas validation ---

def test_sales_summary_valid_month():
    p = SalesSummaryParams(period="2026-08")
    assert p.period == "2026-08"


def test_sales_summary_valid_quarter():
    p = SalesSummaryParams(period="2026-Q3")
    assert p.period == "2026-Q3"


def test_sales_summary_valid_year():
    p = SalesSummaryParams(period="2026")
    assert p.period == "2026"


def test_sales_summary_invalid_period():
    with pytest.raises(Exception):
        SalesSummaryParams(period="08-2026")


def test_sales_target_invalid_month():
    with pytest.raises(Exception):
        SalesTargetParams(year=2026, month=13)


def test_sales_target_valid():
    p = SalesTargetParams(vendor_id="VEN001", year=2026, month=8)
    assert p.month == 8


def test_customer_insights_empty_id():
    with pytest.raises(Exception):
        CustomerInsightsParams(customer_id="   ")


def test_forecast_params_invalid_format():
    with pytest.raises(Exception):
        SalesForecastParams(start_period="2026", end_period="2026-12")
