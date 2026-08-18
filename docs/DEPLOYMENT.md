# SOLE AI Fase 0 — Deployment Runbook

**Responsable TI:** Deploy en Azure App Service  
**Fecha:** Agosto 2026  
**Versión:** 0.1.0

---

## Prerequisitos

- Azure CLI instalado (`az --version`)
- Docker Desktop instalado
- Acceso a Azure Container Registry (ACR)
- Variables de entorno configuradas (ver `.env.example`)

---

## 1. Configurar Variables de Entorno

Crear `backend/.env` basado en `backend/.env.example`:

```bash
cp backend/.env.example backend/.env
# Editar con credenciales reales (NO commitear)
```

Variables críticas a configurar:
- `AZURE_SQL_SERVER` — servidor Azure SQL
- `AZURE_SQL_DATABASE` — nombre de BD
- `AZURE_SQL_USER` / `AZURE_SQL_PASSWORD` — credenciales solo-lectura
- `SQL_SERVER` / `SQL_DATABASE` — BD local SIG
- `ENTRA_TENANT_ID` / `ENTRA_CLIENT_ID` / `ENTRA_CLIENT_SECRET` — Azure AD
- `DEEPSEEK_API_KEY` — clave API Deepseek

---

## 2. Test Local con Docker

```bash
# Build imagen
docker build -t sole-ai:local ./backend

# Test con docker-compose
docker-compose up -d

# Verificar health
curl http://localhost:8000/health
# Expected: {"status":"ok","version":"0.1.0"}

# Ver logs
docker-compose logs -f sole-ai
```

---

## 3. Push a Azure Container Registry

```bash
# Login ACR
az acr login --name <tu-acr-name>

# Tag imagen
docker tag sole-ai:local <tu-acr-name>.azurecr.io/sole-ai:v0.1.0
docker tag sole-ai:local <tu-acr-name>.azurecr.io/sole-ai:latest

# Push
docker push <tu-acr-name>.azurecr.io/sole-ai:v0.1.0
docker push <tu-acr-name>.azurecr.io/sole-ai:latest
```

---

## 4. Deploy en Azure App Service

```bash
# Crear App Service (primera vez)
az webapp create \
  --resource-group <tu-rg> \
  --plan <tu-plan> \
  --name sole-ai-fase0 \
  --deployment-container-image-name <tu-acr-name>.azurecr.io/sole-ai:latest

# Configurar variables de entorno en Azure
az webapp config appsettings set \
  --resource-group <tu-rg> \
  --name sole-ai-fase0 \
  --settings \
    AZURE_SQL_SERVER="<server>" \
    AZURE_SQL_DATABASE="<db>" \
    AZURE_SQL_USER="<user>" \
    AZURE_SQL_PASSWORD="<pass>" \
    DEEPSEEK_API_KEY="<key>" \
    ENTRA_TENANT_ID="<tenant>" \
    ENTRA_CLIENT_ID="<client>" \
    ENTRA_CLIENT_SECRET="<secret>"

# Verificar deploy
az webapp show --name sole-ai-fase0 --resource-group <tu-rg> --query state
curl https://sole-ai-fase0.azurewebsites.net/health
```

---

## 5. Verificación Post-Deploy

```bash
# Health check
curl https://sole-ai-fase0.azurewebsites.net/health

# Test chat endpoint (sin autenticación en dev mode)
curl -X POST https://sole-ai-fase0.azurewebsites.net/api/chat \
  -H "Content-Type: application/json" \
  -d '{"question": "¿cuáles fueron las ventas de agosto?"}'

# Ver logs en Azure
az webapp log tail --name sole-ai-fase0 --resource-group <tu-rg>
```

---

## 6. Actualizar Deploy

```bash
# Re-build y push nueva versión
docker build -t sole-ai:v0.1.1 ./backend
docker tag sole-ai:v0.1.1 <tu-acr-name>.azurecr.io/sole-ai:latest
docker push <tu-acr-name>.azurecr.io/sole-ai:latest

# Restart App Service para aplicar nueva imagen
az webapp restart --name sole-ai-fase0 --resource-group <tu-rg>
```

---

## 7. Rollback

```bash
# Volver a versión anterior
az webapp config container set \
  --name sole-ai-fase0 \
  --resource-group <tu-rg> \
  --docker-custom-image-name <tu-acr-name>.azurecr.io/sole-ai:v0.1.0
az webapp restart --name sole-ai-fase0 --resource-group <tu-rg>
```

---

## Endpoints Disponibles

| Endpoint | Método | Descripción | Auth |
|----------|--------|-------------|------|
| `/health` | GET | Estado del servicio | No |
| `/api/chat` | POST | Consultas en lenguaje natural | Entra ID |
| `/api/tools` | GET | Herramientas disponibles para el usuario | Entra ID |

---

## Troubleshooting

| Problema | Causa | Solución |
|----------|-------|----------|
| `502 Bad Gateway` | App no levantó | Ver logs con `az webapp log tail` |
| `401 Unauthorized` | Token Entra ID inválido | Verificar ENTRA_* variables |
| `Timeout en SQL` | Firewall Azure SQL | Agregar IP de App Service a allowlist |
| `pyodbc error` | ODBC driver faltante | Verificar Dockerfile instaló msodbcsql17 |

---

## Contacto

**Oscar Armando Núñez Vargas** — Especialista IA, MT Industrial  
**Email:** onunez.sole@gmail.com
