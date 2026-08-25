# backend/connectors/sql_connector.py
import pyodbc
import logging
from typing import List, Dict, Any, Optional
from connectors.base_connector import BaseConnector
from config import settings

logger = logging.getLogger(__name__)

class SQLConnector(BaseConnector):
    """Azure SQL Server & Local SIG connector"""

    def __init__(self, db_type: str = "azure"):
        """
        Args:
            db_type: "azure" (soledb-puntoventa) or "local" (SIG)
        """
        super().__init__(f"sql_{db_type}")
        self.db_type = db_type
        self.connection_pool = {}

        if db_type == "azure":
            self.connection_string = (
                f"Driver={{ODBC Driver 18 for SQL Server}};"
                f"Server=tcp:{settings.azure_sql_server},1433;"
                f"Database={settings.azure_sql_database};"
                f"UID={settings.azure_sql_user};"
                f"PWD={settings.azure_sql_password};"
                f"Encrypt=yes;TrustServerCertificate=no;Connection Timeout=30;"
            )
        elif db_type == "punto_venta":
            # PUNTO_VENTA: prioridad de credenciales:
            #   1. PV_SQL_* explícitas
            #   2. Fallback a Azure SQL (cuando toda la data está en soledb-puntoventa)
            #   3. Fallback a SQL local (SIG) — entornos on-premise
            server = (settings.pv_sql_server
                      or settings.azure_sql_server
                      or settings.sql_server)
            user   = (settings.pv_sql_user
                      or settings.azure_sql_user
                      or settings.sql_user)
            pwd    = (settings.pv_sql_password
                      or settings.azure_sql_password
                      or settings.sql_password)
            # La base de datos PV puede ser la misma Azure o una local distinta
            database = settings.pv_sql_database or settings.azure_sql_database

            # Detectar Azure SQL para usar SSL correcto
            is_azure = "database.windows.net" in (server or "")
            if is_azure:
                self.connection_string = (
                    f"Driver={{ODBC Driver 18 for SQL Server}};"
                    f"Server=tcp:{server},1433;"
                    f"Database={database};"
                    f"UID={user};"
                    f"PWD={pwd};"
                    f"Encrypt=yes;TrustServerCertificate=no;Connection Timeout=30;"
                )
            else:
                self.connection_string = (
                    f"Driver={{ODBC Driver 18 for SQL Server}};"
                    f"Server={server};"
                    f"Database={database};"
                    f"UID={user};"
                    f"PWD={pwd};"
                    f"TrustServerCertificate=yes;Connection Timeout=30;"
                )
        else:  # local (SIG)
            self.connection_string = (
                f"Driver={{ODBC Driver 18 for SQL Server}};"
                f"Server={settings.sql_server};"
                f"Database={settings.sql_database};"
                f"UID={settings.sql_user};"
                f"PWD={settings.sql_password};"
            )

    async def validate_connection(self) -> bool:
        """Test database connection"""
        try:
            conn = pyodbc.connect(self.connection_string)
            cursor = conn.cursor()
            cursor.execute("SELECT 1")
            cursor.close()
            conn.close()
            self.logger.info(f"✅ {self.db_type.upper()} SQL connected")
            return True
        except Exception as e:
            self.logger.error(f"❌ {self.db_type.upper()} SQL connection failed: {e}")
            return False

    async def query_readonly(self, query: str, params: tuple = ()) -> List[Dict]:
        """Execute read-only query, return as list of dicts"""
        # Validate query is read-only
        self.validate_readonly(query)

        try:
            conn = pyodbc.connect(self.connection_string)
            cursor = conn.cursor()

            self.logger.debug(f"Executing: {query[:100]}...")
            cursor.execute(query, params)

            results = []
            columns = [d[0] for d in cursor.description]
            for row in cursor.fetchall():
                results.append(dict(zip(columns, row)))

            cursor.close()
            conn.close()

            self.logger.debug(f"Query returned {len(results)} rows")
            return results

        except PermissionError:
            raise
        except Exception as e:
            self.logger.error(f"Query failed: {e}")
            raise

# Singletons for easy access
azure_sql       = SQLConnector(db_type="azure")
local_sql       = SQLConnector(db_type="local")
punto_venta_sql = SQLConnector(db_type="punto_venta")
