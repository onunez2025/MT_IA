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

    # Azure SQL
    azure_sql_server: str = ""
    azure_sql_database: str = ""
    azure_sql_user: str = ""
    azure_sql_password: str = ""

    # Deepseek API
    deepseek_api_key: str = ""
    deepseek_base_url: str = "https://api.deepseek.com/v1"

    class Config:
        env_file = ".env"
        case_sensitive = False


settings = Settings()
