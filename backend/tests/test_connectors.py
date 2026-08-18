import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from connectors.base_connector import BaseConnector
from connectors.entra_connector import EntraConnector


# Concrete implementation of BaseConnector for testing
class MockConnector(BaseConnector):
    """Mock implementation of BaseConnector for testing"""

    async def validate_connection(self) -> bool:
        return True

    async def query_readonly(self, query: str, params: tuple = ()):
        return []


class TestBaseConnector:
    """Tests for BaseConnector.validate_readonly"""

    def test_validate_readonly_blocks_insert(self):
        """Test that validate_readonly blocks INSERT queries"""
        connector = MockConnector("test")

        with pytest.raises(PermissionError) as exc_info:
            connector.validate_readonly("INSERT INTO users VALUES ('test')")
        assert "INSERT" in str(exc_info.value)
        assert "Read-only only" in str(exc_info.value)

    def test_validate_readonly_blocks_delete(self):
        """Test that validate_readonly blocks DELETE queries"""
        connector = MockConnector("test")

        with pytest.raises(PermissionError) as exc_info:
            connector.validate_readonly("DELETE FROM users WHERE id = 1")
        assert "DELETE" in str(exc_info.value)

    def test_validate_readonly_blocks_update(self):
        """Test that validate_readonly blocks UPDATE queries"""
        connector = MockConnector("test")

        with pytest.raises(PermissionError) as exc_info:
            connector.validate_readonly("UPDATE users SET name = 'test'")
        assert "UPDATE" in str(exc_info.value)

    def test_validate_readonly_blocks_drop(self):
        """Test that validate_readonly blocks DROP queries"""
        connector = MockConnector("test")

        with pytest.raises(PermissionError) as exc_info:
            connector.validate_readonly("DROP TABLE users")
        assert "DROP" in str(exc_info.value)

    def test_validate_readonly_blocks_truncate(self):
        """Test that validate_readonly blocks TRUNCATE queries"""
        connector = MockConnector("test")

        with pytest.raises(PermissionError) as exc_info:
            connector.validate_readonly("TRUNCATE TABLE users")
        assert "TRUNCATE" in str(exc_info.value)

    def test_validate_readonly_blocks_alter(self):
        """Test that validate_readonly blocks ALTER queries"""
        connector = MockConnector("test")

        with pytest.raises(PermissionError) as exc_info:
            connector.validate_readonly("ALTER TABLE users ADD COLUMN age INT")
        assert "ALTER" in str(exc_info.value)

    def test_validate_readonly_blocks_create(self):
        """Test that validate_readonly blocks CREATE queries"""
        connector = MockConnector("test")

        with pytest.raises(PermissionError) as exc_info:
            connector.validate_readonly("CREATE TABLE users (id INT)")
        assert "CREATE" in str(exc_info.value)

    def test_validate_readonly_blocks_exec(self):
        """Test that validate_readonly blocks EXEC queries"""
        connector = MockConnector("test")

        with pytest.raises(PermissionError) as exc_info:
            connector.validate_readonly("EXEC sp_something")
        assert "EXEC" in str(exc_info.value)

    def test_validate_readonly_blocks_execute(self):
        """Test that validate_readonly blocks EXECUTE queries"""
        connector = MockConnector("test")

        with pytest.raises(PermissionError) as exc_info:
            connector.validate_readonly("EXECUTE sp_something")
        # EXEC is checked first and matches within EXECUTE
        assert "EXEC" in str(exc_info.value)

    def test_validate_readonly_blocks_grant(self):
        """Test that validate_readonly blocks GRANT queries"""
        connector = MockConnector("test")

        with pytest.raises(PermissionError) as exc_info:
            connector.validate_readonly("GRANT SELECT ON users TO user1")
        assert "GRANT" in str(exc_info.value)

    def test_validate_readonly_blocks_revoke(self):
        """Test that validate_readonly blocks REVOKE queries"""
        connector = MockConnector("test")

        with pytest.raises(PermissionError) as exc_info:
            connector.validate_readonly("REVOKE SELECT ON users FROM user1")
        assert "REVOKE" in str(exc_info.value)

    def test_validate_readonly_allows_select(self):
        """Test that validate_readonly allows SELECT queries"""
        connector = MockConnector("test")

        result = connector.validate_readonly("SELECT * FROM users")
        assert result is True

    def test_validate_readonly_allows_select_lowercase(self):
        """Test that validate_readonly allows lowercase select queries"""
        connector = MockConnector("test")

        result = connector.validate_readonly("select * from users where id = 1")
        assert result is True

    def test_validate_readonly_case_insensitive(self):
        """Test that validate_readonly is case insensitive"""
        connector = MockConnector("test")

        with pytest.raises(PermissionError):
            connector.validate_readonly("insert into users values ('test')")


class TestEntraConnector:
    """Tests for EntraConnector"""

    @pytest.mark.asyncio
    async def test_validate_token_returns_none_for_bad_token(self):
        """Test that validate_token returns None for invalid token"""
        connector = EntraConnector()

        result = await connector.validate_token("invalid.token.here")
        assert result is None

    @pytest.mark.asyncio
    async def test_validate_token_returns_none_for_empty_token(self):
        """Test that validate_token returns None for empty token"""
        connector = EntraConnector()

        result = await connector.validate_token("")
        assert result is None

    @pytest.mark.asyncio
    async def test_get_user_roles_returns_guest_when_not_configured(self):
        """Test that get_user_roles returns ['Guest'] when Entra ID not configured"""
        connector = EntraConnector()

        roles = await connector.get_user_roles("test_user")
        assert roles == ["Guest"]

    @pytest.mark.asyncio
    async def test_get_user_roles_caches_results(self):
        """Test that get_user_roles caches results"""
        connector = EntraConnector()

        # First call
        roles1 = await connector.get_user_roles("test_user")
        assert roles1 == ["Guest"]

        # Second call should use cache
        roles2 = await connector.get_user_roles("test_user")
        assert roles2 == ["Guest"]

        # Verify cache contains the user
        assert "test_user" in connector._cache

    @pytest.mark.asyncio
    async def test_validate_connection_returns_false_when_not_configured(self):
        """Test that validate_connection returns False when tenant ID not configured"""
        connector = EntraConnector()

        result = await connector.validate_connection()
        assert result is False

    @pytest.mark.asyncio
    async def test_validate_connection_logs_warning_when_not_configured(self):
        """Test that validate_connection logs warning when not configured"""
        connector = EntraConnector()

        with patch.object(connector.logger, 'warning') as mock_warning:
            result = await connector.validate_connection()
            mock_warning.assert_called()
            assert "not configured" in mock_warning.call_args[0][0].lower()

    @pytest.mark.asyncio
    async def test_get_user_roles_handles_exception(self):
        """Test that get_user_roles handles exceptions gracefully"""
        connector = EntraConnector()

        # Mock _fetch_roles_from_graph to raise an exception
        connector._fetch_roles_from_graph = AsyncMock(side_effect=Exception("API Error"))

        roles = await connector.get_user_roles("test_user")
        assert roles == ["Guest"]
