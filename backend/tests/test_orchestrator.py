# backend/tests/test_orchestrator.py
import pytest
from unittest.mock import patch, AsyncMock, MagicMock
from layers.orchestrator import Orchestrator, _select_tool, _format_response, TOOL_REGISTRY
from models.user import User
from guards.audit import clear_audit_log


@pytest.fixture(autouse=True)
def reset_audit():
    clear_audit_log()
    yield
    clear_audit_log()


JEFE_USER = User(user_id="u-001", email="jefe@mt.com", roles=["Jefe_Ventas"], is_admin=False)
VENDEDOR_USER = User(user_id="u-002", email="vend@mt.com", roles=["Vendedor"], is_admin=False)
GUEST_USER = User(user_id="u-003", email="guest@mt.com", roles=["Guest"], is_admin=False)


# --- Tool selection heuristics ---

def test_select_tool_ventas():
    result = _select_tool("¿cuáles fueron las ventas de agosto?")
    assert result["tool"] == "get_sales_summary"

def test_select_tool_forecast():
    result = _select_tool("¿cuál es el forecast del Q4?")
    assert result["tool"] == "get_sales_forecast"

def test_select_tool_metas():
    result = _select_tool("¿cuál es la meta de ventas?")
    assert result["tool"] == "get_sales_targets"

def test_select_tool_rendimiento():
    result = _select_tool("¿cuál es el rendimiento de los vendedores?")
    assert result["tool"] == "get_sales_performance"

def test_select_tool_cliente():
    result = _select_tool("dame el historial del cliente")
    assert result["tool"] == "get_customer_insights"

def test_select_tool_inventario():
    result = _select_tool("¿qué materiales tenemos en inventario?")
    assert result["tool"] == "get_inventory_by_sales"

def test_select_tool_no_match():
    result = _select_tool("hola cómo estás")
    assert result is None


# --- Orchestrator process_question ---

@pytest.mark.asyncio
async def test_orchestrator_success_jefe():
    """Jefe_Ventas can access get_sales_summary."""
    orch = Orchestrator()
    mock_result = {
        "period": "2026-08", "region": "Global",
        "total_sales": 500000.0, "num_orders": 200,
        "num_customers": 80, "avg_order_value": 2500.0,
        "timestamp": "2026-08-18T00:00:00",
    }
    with patch("layers.orchestrator.get_sales_summary", new_callable=AsyncMock, return_value=mock_result):
        response = await orch.process_question(JEFE_USER, "¿cuáles fueron las ventas de agosto?")
    assert response.status == "success"
    assert "500,000.00" in response.response
    assert len(response.sources) == 1
    assert response.sources[0]["tool"] == "get_sales_summary"


@pytest.mark.asyncio
async def test_orchestrator_rbac_blocked():
    """Vendedor cannot access get_sales_forecast → blocked."""
    orch = Orchestrator()
    response = await orch.process_question(VENDEDOR_USER, "¿cuál es el forecast del Q4?")
    assert response.status == "blocked"
    assert response.error_message == "RBAC denied"


@pytest.mark.asyncio
async def test_orchestrator_guest_blocked():
    """Guest is blocked from all tools."""
    orch = Orchestrator()
    response = await orch.process_question(GUEST_USER, "¿cuáles fueron las ventas de agosto?")
    assert response.status == "blocked"


@pytest.mark.asyncio
async def test_orchestrator_no_tool_match():
    """Unknown question returns error, not crash."""
    orch = Orchestrator()
    response = await orch.process_question(JEFE_USER, "hola cómo estás")
    assert response.status == "error"
    assert response.error_message == "No matching tool found"


@pytest.mark.asyncio
async def test_orchestrator_tool_exception():
    """Tool exception returns error response, not crash."""
    orch = Orchestrator()
    with patch("layers.orchestrator.get_sales_summary", new_callable=AsyncMock, side_effect=Exception("DB down")):
        response = await orch.process_question(JEFE_USER, "¿cuáles fueron las ventas?")
    assert response.status == "error"
    assert "DB down" in response.error_message


@pytest.mark.asyncio
async def test_orchestrator_empty_question():
    """Empty question returns error."""
    orch = Orchestrator()
    response = await orch.process_question(JEFE_USER, "")
    assert response.status == "error"


@pytest.mark.asyncio
async def test_orchestrator_audit_logged_on_success():
    """Audit entry created on successful tool call."""
    from guards.audit import get_audit_log
    orch = Orchestrator()
    mock_result = {
        "period": "2026-08", "region": "Global",
        "total_sales": 100.0, "num_orders": 1,
        "num_customers": 1, "avg_order_value": 100.0,
        "timestamp": "2026-08-18T00:00:00",
    }
    with patch("layers.orchestrator.get_sales_summary", new_callable=AsyncMock, return_value=mock_result):
        await orch.process_question(JEFE_USER, "ventas de agosto")
    log = get_audit_log()
    assert len(log) == 1
    assert log[0]["status"] == "SUCCESS"
    assert log[0]["user_id"] == "u-001"


@pytest.mark.asyncio
async def test_orchestrator_audit_logged_on_blocked():
    """Audit entry created on BLOCKED request."""
    from guards.audit import get_audit_log
    orch = Orchestrator()
    await orch.process_question(GUEST_USER, "ventas de agosto")
    log = get_audit_log()
    assert len(log) == 1
    assert log[0]["status"] == "BLOCKED"
