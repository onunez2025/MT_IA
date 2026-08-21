import logging
import re
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
        """Block write/DDL keywords as whole SQL tokens (not substrings of column names).

        Uses word-boundary regex so 'insert_fecha' does NOT trigger the INSERT block,
        but 'INSERT INTO ...' does.
        """
        forbidden = [
            "INSERT", "UPDATE", "DELETE", "DROP", "TRUNCATE",
            "ALTER", "EXEC", "EXECUTE", "GRANT", "REVOKE", "CREATE"
        ]
        query_upper = query.upper()
        for keyword in forbidden:
            # \b ensures we match the keyword as a whole word, not as part of a column name
            # e.g. INSERT matches but insert_fecha does not
            if re.search(rf"\b{keyword}\b", query_upper):
                self.logger.warning(f"Blocked {keyword} in query")
                raise PermissionError(f"Operation '{keyword}' blocked. Read-only only.")
        return True
