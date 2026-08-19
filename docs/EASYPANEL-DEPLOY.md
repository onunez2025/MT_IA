# Despliegue en Hostinger VPS + EasyPanel

> **Rama:** `deploy/hostinger`  
> **Objetivo:** tener SOLE AI funcionando en el VPS mientras se gestiona el acceso a Azure Container Apps.

---

## Requisitos previos

| Ítem | Detalle |
|------|---------|
| VPS Hostinger | Con EasyPanel instalado |
| GitHub repo | `https://github.com/onunez2025/MT_IA.git` |
| Azure SQL | Firewall debe permitir la IP del VPS |
| Rama a desplegar | `deploy/hostinger` |

---

## Paso 1 — Obtener la IP del VPS

En EasyPanel → **Settings** → copia la IP pública del servidor.  
La necesitas para el paso siguiente.

---

## Paso 2 — Whitelist de la IP en Azure SQL

1. Azure Portal → **soledbserver** → **Networking**
2. **+ Add client IP** → pegar la IP del VPS
3. **Save**

Sin esto, el contenedor no podrá conectarse a la BD.

---

## Paso 3 — Crear el servicio en EasyPanel

1. EasyPanel → **Projects** → **+ New Project** → nombre: `MT-IA`
2. Dentro del proyecto → **+ New Service** → **App**
3. Nombre del servicio: `sole-ai`
4. **Source** → GitHub → seleccionar `onunez2025/MT_IA`
5. **Branch**: `deploy/hostinger`
6. **Build method**: Dockerfile
7. **Dockerfile path**: `backend/Dockerfile`
8. **Port**: `8000`

---

## Paso 4 — Variables de entorno en EasyPanel

En la pestaña **Environment** del servicio, agregar estas variables:

```
ENVIRONMENT=production
AZURE_SQL_SERVER=soledbserver.database.windows.net
AZURE_SQL_DATABASE=soledb-puntoventa
AZURE_SQL_USER=IA_READONLY_VENTAS
AZURE_SQL_PASSWORD=<contraseña del usuario de solo lectura>
SECRET_KEY=<clave aleatoria 32 chars, ej: openssl rand -hex 16>
AZURE_TENANT_ID=<tenant id de Entra — opcional por ahora>
AZURE_CLIENT_ID=<client id — opcional por ahora>
AZURE_CLIENT_SECRET=<client secret — opcional por ahora>
LOG_LEVEL=INFO
DEBUG=false
```

> **Nota:** Con `ENVIRONMENT=production` y sin token Entra, el sistema rechaza
> peticiones sin `Authorization: Bearer <token>`. Para pruebas en producción,
> cambiar temporalmente a `ENVIRONMENT=development` hasta integrar Entra.

---

## Paso 5 — Dominio (opcional)

EasyPanel → pestaña **Domains** → agregar dominio o usar el subdominio automático
`.easypanel.host` que EasyPanel asigna. HTTPS via Let's Encrypt se activa solo.

---

## Paso 6 — Deploy

1. EasyPanel → **Deploy** → esperar build (~3-5 min la primera vez)
2. Verificar con:

```bash
curl https://<tu-dominio>/health
# Debe responder: {"status":"ok","version":"0.1.0"}
```

---

## Paso 7 — Prueba funcional

```bash
# Con ENVIRONMENT=development — incluye rol en el body
curl -X POST https://<tu-dominio>/api/chat \
  -H "Content-Type: application/json" \
  -d '{
    "question": "cuanto falta para la meta de agosto",
    "user_id": "oscar",
    "roles": ["Jefe_Ventas"]
  }'
```

---

## Diferencias vs rama master (Azure)

| Aspecto | `deploy/hostinger` | `master` (Azure) |
|---------|-------------------|-----------------|
| Host | VPS Hostinger | Azure Container Apps |
| Registry | Build en el VPS | Azure Container Registry |
| HTTPS | Let's Encrypt via EasyPanel | Azure managed |
| Env vars | UI de EasyPanel | Azure App Configuration |
| Autenticación | Dev mode (sin Entra) | Entra ID completo |
| Workers uvicorn | 2 | 1 (escala horizontal) |

---

## Rollback rápido

En EasyPanel → **Deployments** → clic en cualquier deploy anterior → **Redeploy**.

---

## Actualizar el servicio

Cada `git push origin deploy/hostinger` → EasyPanel detecta el cambio
automáticamente si el **Auto-deploy** está activado (webhook de GitHub).
