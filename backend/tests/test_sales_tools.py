# backend/tests/test_sales_tools.py
import pytest
from unittest.mock import patch, AsyncMock
from tools.sales_tools import (
    get_sales_summary,
    get_sales_targets,
    get_sales_forecast,
    get_sales_performance,
)
from tools.utils import query_cache


@pytest.fixture(autouse=True)
def clear_cache():
    """Clear global cache before each test."""
    query_cache.clear()
    yield
    query_cache.clear()


# --- get_sales_summary ---

@pytest.mark.asyncio
async def test_sales_summary_monthly():
    mock_rows = [{"num_orders": 127, "num_customers": 45, "total_sales": 245000.50, "avg_order_value": 1929.13}]
    with patch("tools.sales_tools.azure_sql.query_readonly", new_callable=AsyncMock, return_value=mock_rows):
        result = await get_sales_summary("2026-08")
    assert result["total_sales"] == 245000.50
    assert result["num_orders"] == 127
    assert result["num_customers"] == 45
    assert result["period"] == "2026-08"
    assert result["region"] == "Global"
    assert "timestamp" in result


@pytest.mark.asyncio
async def test_sales_summary_quarterly():
    mock_rows = [{"num_orders": 300, "num_customers": 80, "total_sales": 600000.0, "avg_order_value": 2000.0}]
    with patch("tools.sales_tools.azure_sql.query_readonly", new_callable=AsyncMock, return_value=mock_rows):
        result = await get_sales_summary("2026-Q3")
    assert result["period"] == "2026-Q3"
    assert result["total_sales"] == 600000.0


@pytest.mark.asyncio
async def test_sales_summary_yearly():
    mock_rows = [{"num_orders": 1000, "num_customers": 200, "total_sales": 2000000.0, "avg_order_value": 2000.0}]
    with patch("tools.sales_tools.azure_sql.query_readonly", new_callable=AsyncMock, return_value=mock_rows):
        result = await get_sales_summary("2026")
    assert result["period"] == "2026"


@pytest.mark.asyncio
async def test_sales_summary_with_region():
    mock_rows = [{"num_orders": 50, "num_customers": 20, "total_sales": 100000.0, "avg_order_value": 2000.0}]
    with patch("tools.sales_tools.azure_sql.query_readonly", new_callable=AsyncMock, return_value=mock_rows) as mock_q:
        result = await get_sales_summary("2026-08", region="LIMA")
    assert result["region"] == "LIMA"
    # Verify region filter was included in query
    query_arg = mock_q.call_args[0][0]
    assert "LIMA" in query_arg


@pytest.mark.asyncio
async def test_sales_summary_empty_result():
    with patch("tools.sales_tools.azure_sql.query_readonly", new_callable=AsyncMock, return_value=[]):
        result = await get_sales_summary("2026-08")
    assert result["total_sales"] == 0.0
    assert result["num_orders"] == 0


@pytest.mark.asyncio
async def test_sales_summary_cache_hit():
    mock_rows = [{"num_orders": 10, "num_customers": 5, "total_sales": 5000.0, "avg_order_value": 500.0}]
    with patch("tools.sales_tools.azure_sql.query_readonly", new_callable=AsyncMock, return_value=mock_rows) as mock_q:
        await get_sales_summary("2026-08")
        await get_sales_summary("2026-08")  # Second call should hit cache
    assert mock_q.call_count == 1  # DB called only once


@pytest.mark.asyncio
async def test_sales_summary_invalid_period():
    with pytest.raises(Exception):
        await get_sales_summary("08-2026")  # Wrong format


@pytest.mark.asyncio
async def test_sales_summary_region_escaping():
    """Region value with single quote is escaped (SQL injection prevention)."""
    mock_rows = [{"num_orders": 1, "num_customers": 1, "total_sales": 100.0, "avg_order_value": 100.0}]
    with patch("tools.sales_tools.azure_sql.query_readonly", new_callable=AsyncMock, return_value=mock_rows) as mock_q:
        await get_sales_summary("2026-08", region="O'Brien Zone")
    query_arg = mock_q.call_args[0][0]
    assert "O''Brien Zone" in query_arg


# --- get_sales_targets ---

@pytest.mark.asyncio
async def test_sales_targets_returns_placeholder():
    result = await get_sales_targets(vendor_id="VEN001", year=2026, month=8)
    assert result["vendor_id"] == "VEN001"
    assert "note" in result  # placeholder note present


@pytest.mark.asyncio
async def test_sales_targets_invalid_month():
    with pytest.raises(Exception):
        await get_sales_targets(year=2026, month=13)


# --- get_sales_forecast ---

@pytest.mark.asyncio
async def test_sales_forecast_returns_periods():
    mock_rows = [
        {"Anio": 2026, "MesNumero": 9, "forecast_sales": 300000.0, "forecast_profit": 60000.0, "num_records": 50},
        {"Anio": 2026, "MesNumero": 10, "forecast_sales": 320000.0, "forecast_profit": 65000.0, "num_records": 55},
    ]
    with patch("tools.sales_tools.azure_sql.query_readonly", new_callable=AsyncMock, return_value=mock_rows):
        result = await get_sales_forecast("2026-09", "2026-12")
    assert len(result["periods"]) == 2
    assert result["periods"][0]["period"] == "2026-09"
    assert result["periods"][0]["forecast_sales"] == 300000.0


@pytest.mark.asyncio
async def test_sales_forecast_invalid_period():
    with pytest.raises(Exception):
        await get_sales_forecast("2026", "2026-12")


# --- get_sales_performance ---

@pytest.mark.asyncio
async def test_sales_performance_returns_vendors():
    mock_rows = [
        {"vendor_code": "V001", "vendor_name": "Juan Pérez", "num_orders": 45, "total_sales": 180000.0, "num_customers": 20},
        {"vendor_code": "V002", "vendor_name": "María García", "num_orders": 38, "total_sales": 150000.0, "num_customers": 18},
    ]
    with patch("tools.sales_tools.azure_sql.query_readonly", new_callable=AsyncMock, return_value=mock_rows):
        result = await get_sales_performance("2026-08")
    assert len(result["vendors"]) == 2
    assert result["vendors"][0]["vendor_name"] == "Juan Pérez"
    assert result["vendors"][0]["total_sales"] == 180000.0
