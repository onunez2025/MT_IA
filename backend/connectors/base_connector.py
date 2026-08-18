import logging
from abc import ABC, abstractmethod
from typing import Any

logger = logging.getLogger(__name__)

class BaseConnector(ABC):
    """Abstract base for all data connectors"""

    def __init__(self, name: str):
        self.name = name
        self.logger = logging.getLogger(f"connector.{name}")

    @abstractmethod
    async def validate_connection(self) -> bool:
        """Test connection on startup"""
        pass

    @abstractmethod
    async def query_readonly(self, query: str, params: tuple = ()) -> Any:
        """Execute read-only query"""
        pass

    def validate_readonly(self, query: str) -> bool:
        """Block INSERT, UPDATE, DELETE, DROP, ALTER, EXEC, GRANT, REVOKE, CREATE, TRUNCATE"""
        forbidden = [
            "INSERT", "UPDATE", "DELETE", "DROP", "TRUNCATE",
            "ALTER", "EXEC", "EXECUTE", "GRANT", "REVOKE", "CREATE"
        ]
        query_upper = query.upper()
        for keyword in forbidden:
            if keyword in query_upper:
                self.logger.warning(f"Blocked {keyword} in query")
                raise PermissionError(f"Operation '{keyword}' blocked. Read-only only.")
        return True
