# backend/connectors/c4c_connector.py
import logging
from typing import Dict, List, Any, Optional
from connectors.sap_connector import SAPConnector
from config import settings

logger = logging.getLogger(__name__)


class C4CConnector(SAPConnector):
    """SAP Cloud for Customer (C4C) OData connector"""

    def __init__(self):
        base_url = f"https://{settings.sap_host}/sap/c4c/odata/v4"
        super().__init__(
            name="sap_c4c",
            base_url=base_url,
            user=settings.sap_user,
            password=settings.sap_password
        )

    async def get_customer_list(self, filter_params: Optional[Dict] = None) -> List[Dict]:
        """Get customer list from C4C"""
        params = {
            "$format": "json",
            "$select": "ObjectID,Name,Email,Phone"
        }
        if filter_params:
            params.update(filter_params)
        response = await self.query_readonly("/c4c_odata_api/CustomerSet", params)
        return response.get("d", {}).get("results", [])

    async def get_sales_orders(self, customer_id: str) -> List[Dict]:
        """Get sales orders for a customer"""
        params = {
            "$format": "json",
            "$filter": f"CustomerID eq '{customer_id}'"
        }
        response = await self.query_readonly("/c4c_odata_api/SalesOrderSet", params)
        return response.get("d", {}).get("results", [])


class ERPConnector(SAPConnector):
    """SAP ERP REST connector (Fase 0: read-only inventory/material data)"""

    def __init__(self):
        base_url = f"https://{settings.sap_host}/sap/opu/odata/sap"
        super().__init__(
            name="sap_erp",
            base_url=base_url,
            user=settings.sap_user,
            password=settings.sap_password
        )

    async def get_material_info(self, material_code: str) -> Dict:
        """Get material/product info from ERP"""
        params = {
            "$format": "json",
            "$filter": f"Material eq '{material_code}'"
        }
        response = await self.query_readonly("/API_MATERIAL_DOCUMENT_SRV/A_MaterialDocumentHeader", params)
        return response.get("d", {})


# Singletons
c4c = C4CConnector()
erp = ERPConnector()
