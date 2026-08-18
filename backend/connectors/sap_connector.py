# backend/connectors/sap_connector.py
import logging
import requests
from typing import Dict, Any, Optional
from connectors.base_connector import BaseConnector
from config import settings
from requests.auth import HTTPBasicAuth

logger = logging.getLogger(__name__)

class SAPConnector(BaseConnector):
    """Base SAP connector (REST/OData)"""

    def __init__(self, name: str, base_url: str, user: str, password: str):
        super().__init__(name)
        self.base_url = base_url
        self.auth = HTTPBasicAuth(user, password)
        self.headers = {
            "Content-Type": "application/json",
            "Accept": "application/json"
        }

    async def validate_connection(self) -> bool:
        """Test SAP connection"""
        try:
            response = requests.get(
                f"{self.base_url}/ping",
                auth=self.auth,
                headers=self.headers,
                timeout=5
            )
            if response.status_code in [200, 404]:  # 404 OK if /ping doesn't exist
                self.logger.info(f"✅ {self.name} connected")
                return True
            else:
                self.logger.error(f"❌ {self.name} returned {response.status_code}")
                return False
        except Exception as e:
            self.logger.error(f"❌ {self.name} connection failed: {e}")
            return False

    async def query_readonly(self, endpoint: str, params: Optional[Dict] = None) -> Dict:
        """Execute OData/REST GET query (read-only by design — GET only)"""
        try:
            url = f"{self.base_url}{endpoint}"
            self.logger.debug(f"GET {url} params={params}")

            response = requests.get(
                url,
                auth=self.auth,
                headers=self.headers,
                params=params,
                timeout=30
            )
            response.raise_for_status()
            return response.json()

        except Exception as e:
            self.logger.error(f"SAP query failed: {e}")
            raise
