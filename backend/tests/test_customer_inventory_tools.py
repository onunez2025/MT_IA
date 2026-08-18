# backend/tests/test_customer_inventory_tools.py
import pytest
from unittest.mock import patch, AsyncMock, MagicMock
from tools.customer_tools import get_customer_insights
from tools.inventory_tools import get_inventory_by_sales
from tools.utils import query_cache


@pytest.fixture(autouse=True)
def clear_cache():
    query_cache.clear()
    yield
    query_cache.clear()


# --- get_customer_insights ---

@pytest.mark.asyncio
async def test_customer_insights_with_sql_data():
    """Returns aggregated history from SQL."""
    mock_sql_rows = [{
        "num_transactions": 15,
        "total_spent": 75000.0,
        "avg_transaction_value": 5000.0,
        "last_purchase_date": "2026-07-15",
        "first_purchase_date": "2025-01-10",
    }]
    mock_c4c_customers = [{"Name": "Empresa ABC", "Email": "abc@test.com", "Phone": "999888777"}]

    with patch("tools.customer_tools.azure_sql.query_readonly", new_callable=AsyncMock, return_value=mock_sql_rows), \
         patch("tools.customer_tools.c4c.get_customer_list", new_callable=AsyncMock, return_value=mock_c4c_customers):
        result = await get_customer_insights("CLI-001")

    assert result["customer_id"] == "CLI-001"
    assert result["num_transactions"] == 15
    assert result["total_spent"] == 75000.0
    assert result["name"] == "Empresa ABC"
    assert result["email"] == "abc@test.com"
    assert "timestamp" in result


@pytest.mark.asyncio
async def test_customer_insights_c4c_fallback():
    """C4C failure is graceful — returns SQL data with None profile fields."""
    mock_sql_rows = [{"num_transactions": 5, "total_spent": 10000.0, "avg_transaction_value": 2000.0,
                      "last_purchase_date": "2026-06-01", "first_purchase_date": "2025-06-01"}]

    with patch("tools.customer_tools.azure_sql.query_readonly", new_callable=AsyncMock, return_value=mock_sql_rows), \
         patch("tools.customer_tools.c4c.get_customer_list", new_callable=AsyncMock, side_effect=Exception("C4C unavailable")):
        result = await get_customer_insights("CLI-002")

    assert result["num_transactions"] == 5
    assert result["name"] is None
    assert result["email"] is None


@pytest.mark.asyncio
async def test_customer_insights_empty_history():
    """Customer with no transactions returns zeros."""
    with patch("tools.customer_tools.azure_sql.query_readonly", new_callable=AsyncMock, return_value=[]), \
         patch("tools.customer_tools.c4c.get_customer_list", new_callable=AsyncMock, return_value=[]):
        result = await get_customer_insights("CLI-NEW")

    assert result["num_transactions"] == 0
    assert result["total_spent"] == 0.0


@pytest.mark.asyncio
async def test_customer_insights_cache_hit():
    """Second call uses cache, DB called only once."""
    mock_sql = [{"num_transactions": 1, "total_spent": 1000.0, "avg_transaction_value": 1000.0,
                 "last_purchase_date": "2026-01-01", "first_purchase_date": "2026-01-01"}]
    with patch("tools.customer_tools.azure_sql.query_readonly", new_callable=AsyncMock, return_value=mock_sql) as mock_q, \
         patch("tools.customer_tools.c4c.get_customer_list", new_callable=AsyncMock, return_value=[]):
        await get_customer_insights("CLI-003")
        await get_customer_insights("CLI-003")
    assert mock_q.call_count == 1


@pytest.mark.asyncio
async def test_customer_insights_sql_injection_prevention():
    """Single quote in customer_id is escaped in SQL query."""
    mock_sql = [{"num_transactions": 0, "total_spent": 0.0, "avg_transaction_value": 0.0,
                 "last_purchase_date": None, "first_purchase_date": None}]
    with patch("tools.customer_tools.azure_sql.query_readonly", new_callable=AsyncMock, return_value=mock_sql) as mock_q, \
         patch("tools.customer_tools.c4c.get_customer_list", new_callable=AsyncMock, return_value=[]):
        await get_customer_insights("O'Brien")
    query_arg = mock_q.call_args[0][0]
    assert "O''Brien" in query_arg


@pytest.mark.asyncio
async def test_customer_insights_invalid_empty_id():
    """Empty customer_id raises validation error."""
    with pytest.raises(Exception):
        await get_customer_insights("   ")


# --- get_inventory_by_sales ---

@pytest.mark.asyncio
async def test_inventory_returns_materials():
    """Returns aggregated materials list."""
    mock_rows = [
        {"material_code": "MAT-001", "description": "Tornillo Hex", "quantity_delivered": 500.0,
         "num_deliveries": 12, "num_regions": 3},
        {"material_code": "MAT-002", "description": "Tuerca M8", "quantity_delivered": 350.0,
         "num_deliveries": 8, "num_regions": 2},
    ]
    with patch("tools.inventory_tools.azure_sql.query_readonly", new_callable=AsyncMock, return_value=mock_rows):
        result = await get_inventory_by_sales()

    assert len(result["materials"]) == 2
    assert result["materials"][0]["material_code"] == "MAT-001"
    assert result["materials"][0]["quantity_delivered"] == 500.0
    assert "timestamp" in result


@pytest.mark.asyncio
async def test_inventory_with_material_filter():
    """material_code filter appears in SQL query."""
    with patch("tools.inventory_tools.azure_sql.query_readonly", new_callable=AsyncMock, return_value=[]) as mock_q:
        await get_inventory_by_sales(material_code="MAT-001")
    query_arg = mock_q.call_args[0][0]
    assert "MAT-001" in query_arg


@pytest.mark.asyncio
async def test_inventory_with_region_filter():
    """region filter appears in SQL query."""
    with patch("tools.inventory_tools.azure_sql.query_readonly", new_callable=AsyncMock, return_value=[]) as mock_q:
        await get_inventory_by_sales(region="LIMA")
    query_arg = mock_q.call_args[0][0]
    assert "LIMA" in query_arg


@pytest.mark.asyncio
async def test_inventory_material_code_escaping():
    """Single quote in material_code is escaped."""
    with patch("tools.inventory_tools.azure_sql.query_readonly", new_callable=AsyncMock, return_value=[]) as mock_q:
        await get_inventory_by_sales(material_code="MAT'001")
    query_arg = mock_q.call_args[0][0]
    assert "MAT''001" in query_arg


@pytest.mark.asyncio
async def test_inventory_region_escaping():
    """Single quote in region is escaped."""
    with patch("tools.inventory_tools.azure_sql.query_readonly", new_callable=AsyncMock, return_value=[]) as mock_q:
        await get_inventory_by_sales(region="Lima'Norte")
    query_arg = mock_q.call_args[0][0]
    assert "Lima''Norte" in query_arg


@pytest.mark.asyncio
async def test_inventory_empty_result():
    """Empty DB result returns empty materials list."""
    with patch("tools.inventory_tools.azure_sql.query_readonly", new_callable=AsyncMock, return_value=[]):
        result = await get_inventory_by_sales()
    assert result["materials"] == []


@pytest.mark.asyncio
async def test_inventory_cache_hit():
    """Second call uses cache."""
    with patch("tools.inventory_tools.azure_sql.query_readonly", new_callable=AsyncMock, return_value=[]) as mock_q:
        await get_inventory_by_sales(region="LIMA")
        await get_inventory_by_sales(region="LIMA")
    assert mock_q.call_count == 1
