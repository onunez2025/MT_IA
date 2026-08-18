# backend/config.py
import os
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    """Application configuration from environment"""

    # Environment
    environment: str = os.getenv("ENVIRONMENT", "development")
    debug: bool = os.getenv("DEBUG", "True").lower() == "true"
    log_level: str = os.getenv("LOG_LEVEL", "INFO")

    # Entera ID
    entra_tenant_id: str = os.getenv("ENTRA_TENANT_ID", "")
    entra_client_id: str = os.getenv("ENTRA_CLIENT_ID", "")
    entra_client_secret: str = os.getenv("ENTRA_CLIENT_SECRET", "")

    # SAP
    sap_host: str = os.getenv("SAP_HOST", "")
    sap_user: str = os.getenv("SAP_USER", "")
    sap_password: str = os.getenv("SAP_PASSWORD", "")

    # SQL Local (SIG)
    sql_server: str = os.getenv("SQL_SERVER", "")
    sql_database: str = os.getenv("SQL_DATABASE", "SIG")
    sql_user: str = os.getenv("SQL_USER", "")
    sql_password: str = os.getenv("SQL_PASSWORD", "")

    # Azure SQL
    azure_sql_server: str = os.getenv("AZURE_SQL_SERVER", "")
    azure_sql_database: str = os.getenv("AZURE_SQL_DATABASE", "")
    azure_sql_user: str = os.getenv("AZURE_SQL_USER", "")
    azure_sql_password: str = os.getenv("AZURE_SQL_PASSWORD", "")

    # Deepseek
    deepseek_api_key: str = os.getenv("DEEPSEEK_API_KEY", "")
    deepseek_base_url: str = "https://api.deepseek.com/v1"

    class Config:
        env_file = ".env"
        case_sensitive = False


settings = Settings()
