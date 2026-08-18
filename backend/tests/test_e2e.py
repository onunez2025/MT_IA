# backend/tests/test_e2e.py
"""
End-to-end integration tests for SOLE AI Fase 0.
Tests the full flow: question -> orchestrator -> tool -> response
"""
import pytest
from unittest.mock import patch, AsyncMock
from layers.orchestrator import Orchestrator, _format_response
from models.user import User
from guards.audit import clear_audit_log, get_audit_log


@pytest.fixture(autouse=True)
def reset_audit():
    clear_audit_log()
    yield
    clear_audit_log()


ROLES_JEFE = ["Jefe_Ventas"]
JEFE = User(user_id="e2e-jefe", email="jefe@mt.com", roles=ROLES_JEFE, is_admin=False)
VENDEDOR = User(user_id="e2e-vend", email="vend@mt.com", roles=["Vendedor"], is_admin=False)
ADMIN = User(user_id="e2e-admin", email="admin@mt.com", roles=["Admin"], is_admin=True)


# --- Full flow: question -> response ---

@pytest.mark.asyncio
async def test_e2e_ventas_question():
    """Full flow: sales question -> get_sales_summary -> formatted response."""
    orch = Orchestrator()
    mock_result = {
        "period": "2026-08", "region": "Global",
        "total_sales": 850000.0, "num_orders": 320,
        "num_customers": 95, "avg_order_value": 2656.25,
        "timestamp": "2026-08-18T10:00:00",
    }
    with patch("layers.orchestrator.get_sales_summary", new_callable=AsyncMock, return_value=mock_result):
        resp = await orch.process_question(JEFE, "cuales fueron las ventas del mes")
    assert resp.status == "success"
    assert "850,000.00" in resp.response
    assert resp.sources[0]["tool"] == "get_sales_summary"


@pytest.mark.asyncio
async def test_e2e_forecast_question():
    """Full flow: forecast question -> get_sales_forecast -> formatted response."""
    orch = Orchestrator()
    mock_result = {
        "start_period": "2026-09", "end_period": "2026-12", "region": "Global",
        "periods": [
            {"period": "2026-09", "forecast_sales": 900000.0, "forecast_profit": 180000.0, "num_records": 60},
            {"period": "2026-10", "forecast_sales": 950000.0, "forecast_profit": 190000.0, "num_records": 65},
        ],
        "timestamp": "2026-08-18T10:00:00",
    }
    with patch("layers.orchestrator.get_sales_forecast", new_callable=AsyncMock, return_value=mock_result):
        resp = await orch.process_question(JEFE, "cual es el forecast del Q4")
    assert resp.status == "success"
    assert "1,850,000.00" in resp.response


@pytest.mark.asyncio
async def test_e2e_rbac_vendedor_cant_see_forecast():
    """Vendedor cannot access forecast - RBAC blocks and logs."""
    orch = Orchestrator()
    resp = await orch.process_question(VENDEDOR, "cual es el forecast")
    assert resp.status == "blocked"
    log = get_audit_log()
    assert any(e["status"] == "BLOCKED" for e in log)


@pytest.mark.asyncio
async def test_e2e_vendedor_can_see_ventas():
    """Vendedor CAN access sales summary."""
    orch = Orchestrator()
    mock_result = {
        "period": "2026-08", "region": "Global",
        "total_sales": 300000.0, "num_orders": 100,
        "num_customers": 40, "avg_order_value": 3000.0,
        "timestamp": "2026-08-18T10:00:00",
    }
    with patch("layers.orchestrator.get_sales_summary", new_callable=AsyncMock, return_value=mock_result):
        resp = await orch.process_question(VENDEDOR, "ventas del mes")
    assert resp.status == "success"


@pytest.mark.asyncio
async def test_e2e_admin_all_tools():
    """Admin can access all tools."""
    from guards.rbac import validate_rbac, ROLE_PERMISSIONS
    for tool in ROLE_PERMISSIONS["Admin"]:
        assert validate_rbac(["Admin"], tool) is True


@pytest.mark.asyncio
async def test_e2e_audit_trail_complete():
    """Every interaction generates an audit entry with correct statuses."""
    orch = Orchestrator()
    mock_result = {
        "period": "2026-08", "region": "Global",
        "total_sales": 100.0, "num_orders": 1,
        "num_customers": 1, "avg_order_value": 100.0,
        "timestamp": "2026-08-18T10:00:00",
    }
    with patch("layers.orchestrator.get_sales_summary", new_callable=AsyncMock, return_value=mock_result):
        await orch.process_question(JEFE, "ventas de agosto")
    await orch.process_question(VENDEDOR, "forecast del Q4")    # BLOCKED
    await orch.process_question(JEFE, "bla bla sin sentido")    # ERROR (no match)

    log = get_audit_log()
    statuses = [e["status"] for e in log]
    assert "SUCCESS" in statuses
    assert "BLOCKED" in statuses
    assert "ERROR" in statuses


@pytest.mark.asyncio
async def test_e2e_readonly_guarantee():
    """SQL connector blocks all write operations - read-only guarantee."""
    from connectors.sql_connector import SQLConnector
    sql = SQLConnector(db_type="azure")
    write_queries = [
        "INSERT INTO SD_VENTAS VALUES (1)",
        "UPDATE SD_VENTAS SET col=1",
        "DELETE FROM SD_VENTAS",
        "DROP TABLE SD_VENTAS",
        "TRUNCATE TABLE SD_VENTAS",
        "ALTER TABLE SD_VENTAS ADD col INT",
    ]
    for q in write_queries:
        with pytest.raises(PermissionError):
            await sql.query_readonly(q)


@pytest.mark.asyncio
async def test_e2e_performance_question():
    """Full flow: performance question -> get_sales_performance."""
    orch = Orchestrator()
    mock_result = {
        "period": "2026-08", "region": "Global",
        "vendors": [
            {"vendor_code": "V001", "vendor_name": "Top Seller", "num_orders": 80,
             "total_sales": 400000.0, "num_customers": 35},
        ],
        "timestamp": "2026-08-18T10:00:00",
    }
    with patch("layers.orchestrator.get_sales_performance", new_callable=AsyncMock, return_value=mock_result):
        resp = await orch.process_question(JEFE, "cual es el rendimiento de los vendedores")
    assert resp.status == "success"
    assert "Top Seller" in resp.response


@pytest.mark.asyncio
async def test_e2e_targets_question():
    """Full flow: targets question -> get_sales_targets."""
    orch = Orchestrator()
    mock_result = {
        "vendor_id": "V001", "target": 500000, "actual": 420000,
        "pct_achievement": 84.0, "note": "On track",
        "timestamp": "2026-08-18T10:00:00",
    }
    with patch("layers.orchestrator.get_sales_targets", new_callable=AsyncMock, return_value=mock_result):
        resp = await orch.process_question(JEFE, "cual es la meta de ventas")
    assert resp.status == "success"
    assert "84.0%" in resp.response


@pytest.mark.asyncio
async def test_e2e_customer_question():
    """Full flow: customer question -> get_customer_insights."""
    orch = Orchestrator()
    mock_result = {
        "customer_id": "C123", "num_transactions": 12,
        "total_spent": 75000.0, "last_purchase_date": "2026-07-15",
        "timestamp": "2026-08-18T10:00:00",
    }
    with patch("layers.orchestrator.get_customer_insights", new_callable=AsyncMock, return_value=mock_result):
        resp = await orch.process_question(JEFE, "historial del cliente")
    assert resp.status == "success"
    assert "C123" in resp.response
    assert "75,000.00" in resp.response


@pytest.mark.asyncio
async def test_e2e_inventory_question():
    """Full flow: inventory question -> get_inventory_by_sales."""
    orch = Orchestrator()
    mock_result = {
        "materials": [
            {"material_code": "M001", "description": "Cable RJ45", "quantity_delivered": 5000},
        ],
        "timestamp": "2026-08-18T10:00:00",
    }
    with patch("layers.orchestrator.get_inventory_by_sales", new_callable=AsyncMock, return_value=mock_result):
        resp = await orch.process_question(JEFE, "que materiales tenemos en inventario")
    assert resp.status == "success"
    assert "Cable RJ45" in resp.response


# --- _format_response edge cases ---

def test_format_response_forecast_empty_periods():
    """_format_response returns no-data message when periods list is empty."""
    result = _format_response("get_sales_forecast", {"periods": [], "start_period": "2026-09", "end_period": "2026-12"})
    assert "No se encontraron" in result


def test_format_response_performance_empty_vendors():
    """_format_response returns no-data message when vendors list is empty."""
    result = _format_response("get_sales_performance", {"vendors": [], "period": "2026-08"})
    assert "No se encontraron" in result


def test_format_response_inventory_empty_materials():
    """_format_response returns no-data message when materials list is empty."""
    result = _format_response("get_inventory_by_sales", {"materials": []})
    assert "No se encontraron" in result


def test_format_response_unknown_tool_fallback():
    """_format_response falls back to str(result) for unknown tools."""
    result = _format_response("unknown_tool", {"key": "value"})
    assert "value" in result


def test_format_response_sales_summary_fields():
    """_format_response for get_sales_summary includes all key fields."""
    result = _format_response("get_sales_summary", {
        "period": "2026-08", "region": "Lima",
        "total_sales": 200000.0, "num_orders": 50, "num_customers": 20,
    })
    assert "200,000.00" in result
    assert "Lima" in result
    assert "50" in result


def test_format_response_sales_targets_fields():
    """_format_response for get_sales_targets includes achievement %."""
    result = _format_response("get_sales_targets", {
        "vendor_id": "ALL", "target": 1000000, "actual": 750000,
        "pct_achievement": 75.0, "note": "Behind plan",
    })
    assert "75.0%" in result
    assert "Behind plan" in result


def test_format_response_customer_insights_fields():
    """_format_response for get_customer_insights includes customer_id."""
    result = _format_response("get_customer_insights", {
        "customer_id": "CUST-999", "num_transactions": 5,
        "total_spent": 15000.0, "last_purchase_date": "2026-06-01",
    })
    assert "CUST-999" in result
    assert "15,000.00" in result
