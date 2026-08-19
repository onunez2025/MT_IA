# backend/config.py
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    """Application configuration from environment variables"""

    # Environment
    environment: str = "development"
    debug: bool = True
    log_level: str = "INFO"

    # Entra ID (Microsoft Azure AD)
    entra_tenant_id: str = ""
    entra_client_id: str = ""
    entra_client_secret: str = ""

    # SAP
    sap_host: str = ""
    sap_user: str = ""
    sap_password: str = ""

    # SQL Local (SIG)
    sql_server: str = ""
    sql_database: str = "SIG"
    sql_user: str = ""
    sql_password: str = ""

    # SQL Local — PUNTO_VENTA (material master / maestro de materiales)
    # En producción: apuntar a la réplica Azure de PUNTO_VENTA si existe,
    # o dejar vacío (las queries funcionan sin filtro de tipo de material).
    pv_sql_server: str = ""          # default: mismo server que sql_server
    pv_sql_database: str = "PUNTO_VENTA"
    pv_sql_user: str = ""            # default: mismo user que sql_user
    pv_sql_password: str = ""        # default: mismo pass que sql_password

    # Azure SQL
    azure_sql_server: str = ""
    azure_sql_database: str = ""
    azure_sql_user: str = ""
    azure_sql_password: str = ""

    # Deepseek API
    deepseek_api_key: str = ""
    deepseek_base_url: str = "https://api.deepseek.com/v1"

    # URL pública del backend (para links de descarga en respuestas del agente)
    # Ej: https://gac-sole-mt-ia.jppsfv.easypanel.host
    public_url: str = ""

    class Config:
        env_file = ".env"
        case_sensitive = False


settings = Settings()
