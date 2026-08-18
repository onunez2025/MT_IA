# backend/tests/test_security.py
"""
Security tests for SOLE AI Fase 0.
Validates read-only guarantees, SQL injection prevention, RBAC enforcement.
"""
import pytest
from connectors.sql_connector import SQLConnector
from connectors.base_connector import BaseConnector
from guards.rbac import validate_rbac, ROLE_PERMISSIONS
from guards.sanitization import sanitize_user_input, VALID_TOOLS


# Concrete connector for testing BaseConnector.validate_readonly directly
class _TestConnector(BaseConnector):
    async def validate_connection(self) -> bool:
        return True

    async def query_readonly(self, query: str, params: tuple = ()):
        self.validate_readonly(query)
        return []


class TestReadOnlyGuarantee:
    """Read-only is enforced at connector level per spec."""

    def test_base_connector_blocks_insert(self):
        conn = _TestConnector("test")
        with pytest.raises(PermissionError):
            conn.validate_readonly("INSERT INTO t VALUES (1)")

    def test_base_connector_blocks_update(self):
        conn = _TestConnector("test")
        with pytest.raises(PermissionError):
            conn.validate_readonly("UPDATE t SET x=1")

    def test_base_connector_blocks_delete(self):
        conn = _TestConnector("test")
        with pytest.raises(PermissionError):
            conn.validate_readonly("DELETE FROM t")

    def test_base_connector_blocks_drop(self):
        conn = _TestConnector("test")
        with pytest.raises(PermissionError):
            conn.validate_readonly("DROP TABLE t")

    def test_base_connector_blocks_truncate(self):
        conn = _TestConnector("test")
        with pytest.raises(PermissionError):
            conn.validate_readonly("TRUNCATE TABLE t")

    def test_base_connector_blocks_alter(self):
        conn = _TestConnector("test")
        with pytest.raises(PermissionError):
            conn.validate_readonly("ALTER TABLE t ADD col INT")

    def test_base_connector_blocks_exec(self):
        conn = _TestConnector("test")
        with pytest.raises(PermissionError):
            conn.validate_readonly("EXEC sp_something")

    def test_base_connector_blocks_grant(self):
        conn = _TestConnector("test")
        with pytest.raises(PermissionError):
            conn.validate_readonly("GRANT SELECT TO user1")

    def test_base_connector_blocks_revoke(self):
        conn = _TestConnector("test")
        with pytest.raises(PermissionError):
            conn.validate_readonly("REVOKE SELECT FROM user1")

    def test_base_connector_blocks_create(self):
        conn = _TestConnector("test")
        with pytest.raises(PermissionError):
            conn.validate_readonly("CREATE TABLE t (id INT)")

    def test_base_connector_allows_select(self):
        conn = _TestConnector("test")
        result = conn.validate_readonly("SELECT * FROM t")
        assert result is True

    def test_sql_connector_blocks_all_writes(self):
        sql = SQLConnector(db_type="azure")
        forbidden = ["INSERT", "UPDATE", "DELETE", "DROP", "TRUNCATE", "ALTER",
                     "EXEC", "EXECUTE", "GRANT", "REVOKE", "CREATE"]
        for keyword in forbidden:
            with pytest.raises(PermissionError):
                sql.validate_readonly(f"{keyword} something")

    def test_sql_connector_case_insensitive(self):
        """Blocking is case-insensitive."""
        sql = SQLConnector(db_type="azure")
        with pytest.raises(PermissionError):
            sql.validate_readonly("insert into t values (1)")
        with pytest.raises(PermissionError):
            sql.validate_readonly("Insert Into T Values (1)")

    def test_sql_connector_allows_select(self):
        sql = SQLConnector(db_type="azure")
        assert sql.validate_readonly("SELECT TOP 100 * FROM SD_VENTAS") is True

    def test_error_message_names_forbidden_keyword(self):
        """PermissionError message identifies the blocked keyword."""
        sql = SQLConnector(db_type="azure")
        with pytest.raises(PermissionError) as exc_info:
            sql.validate_readonly("DROP TABLE SD_VENTAS")
        assert "DROP" in str(exc_info.value)


class TestRBACEnforcement:
    """RBAC matrix enforced correctly."""

    def test_all_roles_defined(self):
        assert set(ROLE_PERMISSIONS.keys()) == {"Vendedor", "Jefe_Ventas", "Gerente", "Admin", "Guest"}

    def test_guest_zero_access(self):
        assert ROLE_PERMISSIONS["Guest"] == []
        for tool in VALID_TOOLS:
            assert validate_rbac(["Guest"], tool) is False

    def test_vendedor_limited_access(self):
        allowed = set(ROLE_PERMISSIONS["Vendedor"])
        all_tools = set(VALID_TOOLS)
        blocked = all_tools - allowed
        assert len(blocked) > 0  # Vendedor lacks some tools
        for tool in blocked:
            assert validate_rbac(["Vendedor"], tool) is False

    def test_full_access_roles(self):
        for role in ["Jefe_Ventas", "Gerente", "Admin"]:
            for tool in VALID_TOOLS:
                assert validate_rbac([role], tool) is True

    def test_privilege_escalation_prevented(self):
        """Unknown roles get zero access."""
        assert validate_rbac(["SuperAdmin"], "get_sales_summary") is False
        assert validate_rbac(["root"], "get_sales_summary") is False
        assert validate_rbac(["Admin'"], "get_sales_summary") is False

    def test_empty_roles_denied(self):
        assert validate_rbac([], "get_sales_summary") is False

    def test_multi_role_grants_union(self):
        """User with multiple roles gets union of permissions."""
        assert validate_rbac(["Guest", "Vendedor"], "get_sales_summary") is True
        assert validate_rbac(["Guest", "Vendedor"], "get_sales_forecast") is False


class TestInputSanitization:
    """Input is sanitized before processing."""

    def test_max_length_enforced(self):
        long_text = "x" * 1000
        result = sanitize_user_input(long_text)
        assert len(result) <= 500

    def test_sql_keyword_in_question_still_returned(self):
        """Questions with SQL keywords are NOT blocked; they're logged and passed through."""
        result = sanitize_user_input("DROP TABLE ventas por favor")
        assert result is not None
        assert len(result) > 0

    def test_empty_input(self):
        assert sanitize_user_input("") == ""

    def test_whitespace_only_input(self):
        assert sanitize_user_input("   ") == ""

    def test_normal_question_unchanged(self):
        q = "cuales fueron las ventas de agosto"
        assert sanitize_user_input(q) == q

    def test_valid_tools_set_size(self):
        assert len(VALID_TOOLS) == 6

    def test_valid_tools_contains_expected(self):
        expected = {
            "get_sales_summary", "get_sales_targets", "get_sales_forecast",
            "get_customer_insights", "get_sales_performance", "get_inventory_by_sales",
        }
        assert VALID_TOOLS == expected

    def test_validate_tool_name_valid(self):
        from guards.sanitization import validate_tool_name
        assert validate_tool_name("get_sales_summary") is True
        assert validate_tool_name("get_inventory_by_sales") is True

    def test_validate_tool_name_invalid(self):
        from guards.sanitization import validate_tool_name
        assert validate_tool_name("unknown_tool") is False
        assert validate_tool_name("") is False
        assert validate_tool_name("DROP TABLE") is False
