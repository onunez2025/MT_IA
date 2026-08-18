# backend/tests/test_sap_connectors.py
import pytest
from unittest.mock import patch, MagicMock, AsyncMock
from connectors.sap_connector import SAPConnector
from connectors.c4c_connector import C4CConnector, ERPConnector


class TestSAPConnector:
    def test_sap_connector_inherits_base(self):
        """SAPConnector inherits from BaseConnector"""
        from connectors.base_connector import BaseConnector
        sap = SAPConnector("test_sap", "https://example.com", "user", "pass")
        assert isinstance(sap, BaseConnector)

    def test_sap_connector_sets_auth(self):
        """SAPConnector stores auth credentials"""
        sap = SAPConnector("test_sap", "https://example.com", "myuser", "mypass")
        assert sap.auth.username == "myuser"
        assert sap.auth.password == "mypass"

    def test_sap_connector_sets_headers(self):
        """SAPConnector sets JSON headers"""
        sap = SAPConnector("test_sap", "https://example.com", "u", "p")
        assert sap.headers["Accept"] == "application/json"
        assert sap.headers["Content-Type"] == "application/json"

    @pytest.mark.asyncio
    async def test_validate_connection_success_200(self):
        """validate_connection returns True on HTTP 200"""
        sap = SAPConnector("test", "https://example.com", "u", "p")
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        with patch("connectors.sap_connector.requests.get", return_value=mock_resp):
            result = await sap.validate_connection()
        assert result is True

    @pytest.mark.asyncio
    async def test_validate_connection_success_404(self):
        """validate_connection returns True on HTTP 404 (ping endpoint may not exist)"""
        sap = SAPConnector("test", "https://example.com", "u", "p")
        mock_resp = MagicMock()
        mock_resp.status_code = 404
        with patch("connectors.sap_connector.requests.get", return_value=mock_resp):
            result = await sap.validate_connection()
        assert result is True

    @pytest.mark.asyncio
    async def test_validate_connection_failure_500(self):
        """validate_connection returns False on HTTP 500"""
        sap = SAPConnector("test", "https://example.com", "u", "p")
        mock_resp = MagicMock()
        mock_resp.status_code = 500
        with patch("connectors.sap_connector.requests.get", return_value=mock_resp):
            result = await sap.validate_connection()
        assert result is False

    @pytest.mark.asyncio
    async def test_validate_connection_exception(self):
        """validate_connection returns False on network exception"""
        sap = SAPConnector("test", "https://example.com", "u", "p")
        with patch("connectors.sap_connector.requests.get", side_effect=Exception("timeout")):
            result = await sap.validate_connection()
        assert result is False

    @pytest.mark.asyncio
    async def test_query_readonly_get_only(self):
        """query_readonly executes GET and returns parsed JSON"""
        sap = SAPConnector("test", "https://example.com", "u", "p")
        mock_resp = MagicMock()
        mock_resp.json.return_value = {"d": {"results": [{"ID": "1"}]}}
        mock_resp.raise_for_status = MagicMock()
        with patch("connectors.sap_connector.requests.get", return_value=mock_resp):
            result = await sap.query_readonly("/CustomerSet")
        assert result["d"]["results"][0]["ID"] == "1"


class TestC4CConnector:
    @pytest.mark.asyncio
    async def test_get_customer_list_returns_results(self):
        """get_customer_list parses d.results from OData response"""
        c4c = C4CConnector()
        mock_resp = MagicMock()
        mock_resp.json.return_value = {
            "d": {"results": [
                {"ObjectID": "1", "Name": "Acme", "Email": "acme@test.com", "Phone": "999"},
                {"ObjectID": "2", "Name": "Beta", "Email": "beta@test.com", "Phone": "888"},
            ]}
        }
        mock_resp.raise_for_status = MagicMock()
        mock_resp.status_code = 200
        with patch("connectors.sap_connector.requests.get", return_value=mock_resp):
            customers = await c4c.get_customer_list()
        assert len(customers) == 2
        assert customers[0]["Name"] == "Acme"

    @pytest.mark.asyncio
    async def test_get_customer_list_empty(self):
        """get_customer_list returns empty list when no results"""
        c4c = C4CConnector()
        mock_resp = MagicMock()
        mock_resp.json.return_value = {"d": {"results": []}}
        mock_resp.raise_for_status = MagicMock()
        with patch("connectors.sap_connector.requests.get", return_value=mock_resp):
            result = await c4c.get_customer_list()
        assert result == []

    @pytest.mark.asyncio
    async def test_get_sales_orders(self):
        """get_sales_orders filters by customer_id"""
        c4c = C4CConnector()
        mock_resp = MagicMock()
        mock_resp.json.return_value = {"d": {"results": [{"OrderID": "SO-001"}]}}
        mock_resp.raise_for_status = MagicMock()
        with patch("connectors.sap_connector.requests.get", return_value=mock_resp) as mock_get:
            orders = await c4c.get_sales_orders("CLI-001")
        assert len(orders) == 1
        # Verify filter param was passed
        call_kwargs = mock_get.call_args[1]
        assert "CLI-001" in str(call_kwargs.get("params", {}))

    @pytest.mark.asyncio
    async def test_get_sales_orders_escapes_single_quotes(self):
        """get_sales_orders escapes single quotes in customer_id (OData injection prevention)"""
        c4c = C4CConnector()
        mock_resp = MagicMock()
        mock_resp.json.return_value = {"d": {"results": []}}
        mock_resp.raise_for_status = MagicMock()
        with patch("connectors.sap_connector.requests.get", return_value=mock_resp) as mock_get:
            await c4c.get_sales_orders("O'Brien")
        call_kwargs = mock_get.call_args[1]
        # Single quote must be escaped as ''
        assert "O''Brien" in str(call_kwargs.get("params", {}))

    @pytest.mark.asyncio
    async def test_get_material_info(self):
        """ERPConnector.get_material_info returns d dict"""
        erp = ERPConnector()
        mock_resp = MagicMock()
        mock_resp.json.return_value = {"d": {"Material": "MAT-001", "Description": "Widget"}}
        mock_resp.raise_for_status = MagicMock()
        with patch("connectors.sap_connector.requests.get", return_value=mock_resp):
            result = await erp.get_material_info("MAT-001")
        assert result["Material"] == "MAT-001"


class TestQueryReadonlyError:
    @pytest.mark.asyncio
    async def test_query_readonly_raises_on_http_error(self):
        """query_readonly raises on HTTP error"""
        sap = SAPConnector("test", "https://example.com", "u", "p")
        mock_resp = MagicMock()
        mock_resp.raise_for_status.side_effect = Exception("HTTP 500")
        with patch("connectors.sap_connector.requests.get", return_value=mock_resp):
            with pytest.raises(Exception):
                await sap.query_readonly("/SomeEndpoint")
