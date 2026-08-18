import pytest
from datetime import datetime
from models import (
    User, Role, Permission,
    QueryRequest, QueryResponse, Tool, ToolParameter,
    AuditLog, RBACChangeLog,
    ToolDefinition
)


class TestUserModels:
    """Test User, Role, and Permission models"""

    def test_role_instantiation(self):
        """Test Role model can be instantiated with valid data"""
        role = Role(
            name="Ventas",
            tools=["get_sales_summary", "get_sales_targets"]
        )
        assert role.name == "Ventas"
        assert len(role.tools) == 2
        assert "get_sales_summary" in role.tools

    def test_user_instantiation(self):
        """Test User model can be instantiated with valid data"""
        user = User(
            user_id="user@mtind.com",
            email="user@mtind.com",
            roles=["Ventas", "Admin"],
            is_admin=True
        )
        assert user.user_id == "user@mtind.com"
        assert user.email == "user@mtind.com"
        assert len(user.roles) == 2
        assert user.is_admin is True

    def test_user_default_is_admin(self):
        """Test User model has is_admin default as False"""
        user = User(
            user_id="user@mtind.com",
            email="user@mtind.com",
            roles=["Ventas"]
        )
        assert user.is_admin is False

    def test_permission_instantiation(self):
        """Test Permission model can be instantiated with valid data"""
        perm = Permission(
            user_id="user@mtind.com",
            tool_name="get_sales_summary",
            role_name="Ventas",
            granted=True
        )
        assert perm.user_id == "user@mtind.com"
        assert perm.tool_name == "get_sales_summary"
        assert perm.role_name == "Ventas"
        assert perm.granted is True


class TestQueryModels:
    """Test QueryRequest, QueryResponse, Tool, and ToolParameter models"""

    def test_tool_parameter_instantiation(self):
        """Test ToolParameter model can be instantiated with valid data"""
        param = ToolParameter(
            name="start_date",
            type="date",
            required=True,
            description="Start date for the report"
        )
        assert param.name == "start_date"
        assert param.type == "date"
        assert param.required is True
        assert param.description == "Start date for the report"

    def test_tool_parameter_default_required(self):
        """Test ToolParameter model has required default as True"""
        param = ToolParameter(
            name="filter",
            type="string",
            description="Optional filter"
        )
        assert param.required is True

    def test_tool_parameter_empty_description(self):
        """Test ToolParameter model has empty description default"""
        param = ToolParameter(
            name="limit",
            type="int"
        )
        assert param.description == ""

    def test_tool_instantiation(self):
        """Test Tool model can be instantiated with valid data"""
        tool = Tool(
            name="get_sales_summary",
            description="Get sales summary by region",
            parameters=[
                ToolParameter(name="region", type="string", required=True),
                ToolParameter(name="year", type="int", required=True)
            ]
        )
        assert tool.name == "get_sales_summary"
        assert len(tool.parameters) == 2
        assert tool.parameters[0].name == "region"

    def test_query_request_instantiation(self):
        """Test QueryRequest model can be instantiated with valid data"""
        req = QueryRequest(
            user_id="user@mtind.com",
            question="What are the sales for 2024?",
            conversation_id="conv_123"
        )
        assert req.user_id == "user@mtind.com"
        assert req.question == "What are the sales for 2024?"
        assert req.conversation_id == "conv_123"

    def test_query_request_optional_conversation_id(self):
        """Test QueryRequest model has optional conversation_id"""
        req = QueryRequest(
            user_id="user@mtind.com",
            question="What are the sales for 2024?"
        )
        assert req.conversation_id is None

    def test_query_response_instantiation(self):
        """Test QueryResponse model can be instantiated with valid data"""
        resp = QueryResponse(
            status="success",
            response="Sales for 2024 are $1M",
            sources=[{"source": "database", "table": "sales"}],
            tokens_used=150,
            error_message=None
        )
        assert resp.status == "success"
        assert "Sales" in resp.response
        assert len(resp.sources) == 1
        assert resp.tokens_used == 150

    def test_query_response_blocked_status(self):
        """Test QueryResponse model with blocked status"""
        resp = QueryResponse(
            status="blocked",
            response="Access denied",
            sources=[],
            error_message="User does not have permission"
        )
        assert resp.status == "blocked"
        assert resp.error_message == "User does not have permission"

    def test_query_response_optional_fields(self):
        """Test QueryResponse model optional fields"""
        resp = QueryResponse(
            status="error",
            response="An error occurred",
            sources=[]
        )
        assert resp.tokens_used is None
        assert resp.error_message is None


class TestAuditModels:
    """Test AuditLog and RBACChangeLog models"""

    def test_audit_log_instantiation(self):
        """Test AuditLog model can be instantiated with valid data"""
        now = datetime.now()
        log = AuditLog(
            timestamp=now,
            user_id="user@mtind.com",
            user_roles=["Ventas", "Admin"],
            tool_name="get_sales_summary",
            parameters={"region": "LATAM", "year": 2024},
            status="SUCCESS",
            result_row_count=150,
            tokens_used=120,
            response_time_ms=250.5,
            ip_address="192.168.1.1"
        )
        assert log.user_id == "user@mtind.com"
        assert log.tool_name == "get_sales_summary"
        assert log.status == "SUCCESS"
        assert log.result_row_count == 150
        assert log.response_time_ms == 250.5

    def test_audit_log_blocked_status(self):
        """Test AuditLog model with BLOCKED status"""
        now = datetime.now()
        log = AuditLog(
            timestamp=now,
            user_id="user@mtind.com",
            user_roles=["Ventas"],
            tool_name="get_financial_data",
            parameters={},
            status="BLOCKED",
            result_row_count=0,
            tokens_used=50,
            response_time_ms=10.0,
            ip_address="192.168.1.1"
        )
        assert log.status == "BLOCKED"
        assert log.result_row_count == 0

    def test_audit_log_error_status(self):
        """Test AuditLog model with ERROR status"""
        now = datetime.now()
        log = AuditLog(
            timestamp=now,
            user_id="user@mtind.com",
            user_roles=["Ventas"],
            tool_name="get_sales_summary",
            parameters={"region": "LATAM"},
            status="ERROR",
            result_row_count=0,
            tokens_used=None,
            response_time_ms=100.0,
            ip_address="192.168.1.1"
        )
        assert log.status == "ERROR"
        assert log.tokens_used is None

    def test_rbac_change_log_instantiation(self):
        """Test RBACChangeLog model can be instantiated with valid data"""
        now = datetime.now()
        log = RBACChangeLog(
            timestamp=now,
            changed_by="admin@mtind.com",
            event="USER_CREATED",
            details={"user_id": "newuser@mtind.com", "roles": ["Ventas"]}
        )
        assert log.changed_by == "admin@mtind.com"
        assert log.event == "USER_CREATED"
        assert "user_id" in log.details

    def test_rbac_change_log_tool_assigned(self):
        """Test RBACChangeLog model for tool assignment"""
        now = datetime.now()
        log = RBACChangeLog(
            timestamp=now,
            changed_by="admin@mtind.com",
            event="TOOL_ASSIGNED_TO_ROLE",
            details={"role": "Finanzas", "tool": "get_financial_data"}
        )
        assert log.event == "TOOL_ASSIGNED_TO_ROLE"

    def test_rbac_change_log_user_deactivated(self):
        """Test RBACChangeLog model for user deactivation"""
        now = datetime.now()
        log = RBACChangeLog(
            timestamp=now,
            changed_by="admin@mtind.com",
            event="USER_DEACTIVATED",
            details={"user_id": "olduser@mtind.com", "reason": "Left company"}
        )
        assert log.event == "USER_DEACTIVATED"
        assert log.details["reason"] == "Left company"


class TestToolDefinition:
    """Test ToolDefinition model"""

    def test_tool_definition_instantiation(self):
        """Test ToolDefinition model can be instantiated with valid data"""
        tool = ToolDefinition(
            name="get_sales_summary",
            description="Get sales summary by region",
            parameters={"region": "string", "year": "int"},
            requires_roles=["Ventas", "Admin"]
        )
        assert tool.name == "get_sales_summary"
        assert "region" in tool.parameters
        assert len(tool.requires_roles) == 2

    def test_tool_definition_with_handler(self):
        """Test ToolDefinition model with handler function"""
        def dummy_handler():
            return "result"

        tool = ToolDefinition(
            name="test_tool",
            description="A test tool",
            parameters={},
            handler=dummy_handler,
            requires_roles=["Admin"]
        )
        assert tool.handler is not None
        assert callable(tool.handler)
        assert tool.handler() == "result"

    def test_tool_definition_handler_optional(self):
        """Test ToolDefinition model handler is optional"""
        tool = ToolDefinition(
            name="test_tool",
            description="A test tool",
            parameters={},
            requires_roles=["Admin"]
        )
        assert tool.handler is None


class TestModelIntegration:
    """Integration tests for models working together"""

    def test_user_with_query_request(self):
        """Test User and QueryRequest models together"""
        user = User(
            user_id="user@mtind.com",
            email="user@mtind.com",
            roles=["Ventas"]
        )
        req = QueryRequest(
            user_id=user.user_id,
            question="Sales summary?"
        )
        assert req.user_id == user.user_id

    def test_query_with_audit_log(self):
        """Test QueryResponse and AuditLog models together"""
        resp = QueryResponse(
            status="success",
            response="Result",
            sources=[],
            tokens_used=100
        )
        log = AuditLog(
            timestamp=datetime.now(),
            user_id="user@mtind.com",
            user_roles=["Ventas"],
            tool_name="get_sales_summary",
            parameters={},
            status=resp.status.upper(),
            result_row_count=10,
            tokens_used=resp.tokens_used,
            response_time_ms=100.0,
            ip_address="192.168.1.1"
        )
        assert log.tokens_used == resp.tokens_used
        assert log.status == "SUCCESS"

    def test_tool_definition_with_audit(self):
        """Test ToolDefinition and AuditLog models together"""
        tool = ToolDefinition(
            name="get_sales_summary",
            description="Sales summary",
            parameters={},
            requires_roles=["Ventas"]
        )
        log = AuditLog(
            timestamp=datetime.now(),
            user_id="user@mtind.com",
            user_roles=["Ventas"],
            tool_name=tool.name,
            parameters={},
            status="SUCCESS",
            result_row_count=5,
            tokens_used=50,
            response_time_ms=50.0,
            ip_address="192.168.1.1"
        )
        assert log.tool_name == tool.name
