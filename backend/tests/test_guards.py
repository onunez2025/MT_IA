# backend/tests/test_guards.py
import pytest
from guards.rbac import validate_rbac, get_allowed_tools, ROLE_PERMISSIONS
from guards.audit import log_audit_entry, get_audit_log, clear_audit_log, AuditLogger
from guards.sanitization import validate_tool_name, sanitize_user_input, VALID_TOOLS


@pytest.fixture(autouse=True)
def reset_audit():
    clear_audit_log()
    yield
    clear_audit_log()


# --- RBAC ---

def test_rbac_vendedor_allowed_tools():
    assert validate_rbac(["Vendedor"], "get_sales_summary") is True
    assert validate_rbac(["Vendedor"], "get_sales_targets") is True
    assert validate_rbac(["Vendedor"], "get_customer_insights") is True


def test_rbac_vendedor_blocked_tools():
    assert validate_rbac(["Vendedor"], "get_sales_forecast") is False
    assert validate_rbac(["Vendedor"], "get_sales_performance") is False
    assert validate_rbac(["Vendedor"], "get_inventory_by_sales") is False


def test_rbac_jefe_ventas_all_tools():
    for tool in ROLE_PERMISSIONS["Jefe_Ventas"]:
        assert validate_rbac(["Jefe_Ventas"], tool) is True


def test_rbac_gerente_all_tools():
    for tool in ROLE_PERMISSIONS["Gerente"]:
        assert validate_rbac(["Gerente"], tool) is True


def test_rbac_admin_all_tools():
    for tool in ROLE_PERMISSIONS["Admin"]:
        assert validate_rbac(["Admin"], tool) is True


def test_rbac_guest_no_tools():
    for tool in VALID_TOOLS:
        assert validate_rbac(["Guest"], tool) is False


def test_rbac_empty_roles_denied():
    assert validate_rbac([], "get_sales_summary") is False


def test_rbac_unknown_role_denied():
    assert validate_rbac(["UnknownRole"], "get_sales_summary") is False


def test_rbac_multi_role_grants_access():
    """User with Vendedor + Jefe_Ventas gets Jefe_Ventas permissions."""
    assert validate_rbac(["Vendedor", "Jefe_Ventas"], "get_sales_forecast") is True


def test_get_allowed_tools_vendedor():
    tools = get_allowed_tools(["Vendedor"])
    assert "get_sales_summary" in tools
    assert "get_sales_forecast" not in tools


def test_get_allowed_tools_multiple_roles():
    tools = get_allowed_tools(["Vendedor", "Jefe_Ventas"])
    assert len(tools) == 6  # All tools


# --- Audit ---

def test_audit_log_success_entry():
    entry = log_audit_entry(
        user_id="usr-001",
        user_roles=["Vendedor"],
        tool_name="get_sales_summary",
        parameters={"period": "2026-08"},
        status="SUCCESS",
        result_row_count=1,
        tokens_used=150,
        response_time_ms=320.5,
        ip_address="192.168.1.1",
    )
    assert entry.status == "SUCCESS"
    assert entry.user_id == "usr-001"
    assert entry.tokens_used == 150


def test_audit_log_blocked_entry():
    entry = log_audit_entry(
        user_id="usr-002",
        user_roles=["Guest"],
        tool_name="get_sales_summary",
        parameters={},
        status="BLOCKED",
    )
    assert entry.status == "BLOCKED"


def test_audit_log_error_entry():
    entry = log_audit_entry(
        user_id="usr-003",
        user_roles=["Vendedor"],
        tool_name="get_sales_summary",
        parameters={},
        status="ERROR",
    )
    assert entry.status == "ERROR"


def test_audit_log_invalid_status():
    """Only SUCCESS/BLOCKED/ERROR are valid statuses."""
    with pytest.raises(Exception):
        log_audit_entry(
            user_id="usr-004",
            user_roles=[],
            tool_name="get_sales_summary",
            parameters={},
            status="INVALID_STATUS",
        )


def test_audit_get_log():
    log_audit_entry("u1", ["Vendedor"], "get_sales_summary", {}, "SUCCESS")
    log_audit_entry("u2", ["Guest"], "get_sales_summary", {}, "BLOCKED")
    entries = get_audit_log()
    assert len(entries) == 2


def test_audit_logger_helper():
    al = AuditLogger(
        user_id="usr-005",
        user_roles=["Jefe_Ventas"],
        tool_name="get_sales_forecast",
        parameters={"start_period": "2026-09"},
    )
    al.start()
    entry = al.finish(status="SUCCESS", result_row_count=3, tokens_used=200)
    assert entry.status == "SUCCESS"
    assert entry.response_time_ms >= 0


# --- Sanitization ---

def test_validate_tool_name_valid():
    for tool in VALID_TOOLS:
        assert validate_tool_name(tool) is True


def test_validate_tool_name_invalid():
    assert validate_tool_name("drop_table") is False
    assert validate_tool_name("") is False
    assert validate_tool_name("get_admin_data") is False


def test_sanitize_truncates():
    long_input = "a" * 600
    result = sanitize_user_input(long_input)
    assert len(result) <= 500


def test_sanitize_strips_whitespace():
    result = sanitize_user_input("  hola  ")
    assert result == "hola"


def test_sanitize_empty():
    assert sanitize_user_input("") == ""


def test_sanitize_dangerous_pattern_detected():
    """Dangerous patterns are logged but input still returned (not silently dropped)."""
    result = sanitize_user_input("DROP TABLE sales")
    assert "DROP TABLE sales" in result  # returned, just logged
