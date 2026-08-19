# backend/Dockerfile
# Contexto de build: raíz del repositorio (para EasyPanel / CI)
# Build local con docker-compose: context: ./backend (docker-compose.yml)
FROM python:3.11-slim

# Instalar ODBC Driver 18 for SQL Server
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    gnupg \
    unixodbc-dev \
    && curl https://packages.microsoft.com/keys/microsoft.asc | apt-key add - \
    && curl https://packages.microsoft.com/config/debian/12/prod.list \
        > /etc/apt/sources.list.d/mssql-release.list \
    && apt-get update \
    && ACCEPT_EULA=Y apt-get install -y --no-install-recommends msodbcsql18 \
    && apt-get clean \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Dependencias Python — ruta relativa a raíz del repo
COPY backend/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Código de la aplicación
COPY backend/ .

# Usuario sin privilegios
RUN useradd --create-home --shell /bin/bash appuser \
    && chown -R appuser:appuser /app
USER appuser

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=10s --start-period=10s --retries=3 \
    CMD curl -f http://localhost:8000/health || exit 1

CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "2"]
