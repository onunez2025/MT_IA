# backend/Dockerfile
# Contexto de build: raíz del repositorio (EasyPanel / CI)
# Build local: docker-compose.yml usa el mismo contexto raíz

# Pinamos a Bookworm (Debian 12) para garantizar compatibilidad con
# el repo de Microsoft ODBC 18 — Trixie (Debian 13) no tiene apt-key
FROM python:3.11-slim-bookworm

# Instalar ODBC Driver 18 for SQL Server
# Usamos gpg --dearmor en vez de apt-key (deprecado desde Debian 12)
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    gnupg2 \
    unixodbc-dev \
    && curl -sSL https://packages.microsoft.com/keys/microsoft.asc \
       | gpg --dearmor -o /usr/share/keyrings/microsoft-prod.gpg \
    && echo "deb [arch=amd64 signed-by=/usr/share/keyrings/microsoft-prod.gpg] \
       https://packages.microsoft.com/debian/12/prod bookworm main" \
       > /etc/apt/sources.list.d/mssql-release.list \
    && apt-get update \
    && ACCEPT_EULA=Y apt-get install -y --no-install-recommends msodbcsql18 \
    && apt-get clean \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Dependencias Python (ruta relativa a raíz del repo)
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
