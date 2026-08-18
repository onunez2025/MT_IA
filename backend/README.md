# SOLE AI — Backend API

**Versión:** 0.1.0  
**Fase:** 0 (Piloto Ventas)  
**Stack:** FastAPI + Python 3.11 + Deepseek API + Azure SQL + Microsoft Entra ID

---

## 🎯 ¿Qué hace?

SOLE AI responde preguntas de negocio en lenguaje natural español sobre datos de ventas de MT Industrial. Conecta con SAP (a través de Azure SQL y SAP C4C OData) y responde consultas como:

- "¿Cuáles fueron las ventas de agosto 2026?"
- "¿Cuál es el forecast del Q4?"
- "¿Cómo va el rendimiento de los vendedores este mes?"

---

## 🏗️ Arquitectura

```
Usuario → Entra ID → /api/chat → Orchestrator → Tool → SQL/SAP → Respuesta
                          ↓
                    RBAC Guard → Audit Log
```

**6 Herramientas disponibles:**

| Tool | Descripción | Fuente |
|------|------------|--------|
| `get_sales_summary` | Ventas totales por período | Azure SQL (SD_VENTAS) |
| `get_sales_targets` | Metas vs actual | SIG (pendiente) |
| `get_sales_forecast` | Pronóstico por período | Azure SQL (WEB_FORECAST_VENTAS_REPORTE_ACTIVIDAD) |
| `get_customer_insights` | Historial de cliente | SQL + SAP C4C |
| `get_sales_performance` | Top vendedores | Azure SQL (SD_VENTAS) |
| `get_inventory_by_sales` | Materiales entregados | Azure SQL (SD_ENTREGAS) |

---

## 🔒 Seguridad

- **Read-Only:** 3 niveles — credenciales BD, validación de keywords SQL, HTTP GET-only en SAP
- **RBAC:** Roles via Microsoft Entra ID (Vendedor, Jefe_Ventas, Gerente, Admin, Guest)
- **Auditoría:** Cada consulta registrada con usuario, herramienta, timestamps, tokens, resultado
- **Sin credenciales en código:** Todo via variables de entorno

**Matriz RBAC:**

| Role | Herramientas disponibles |
|------|--------------------------|
| Vendedor | summary, targets, customer_insights |
| Jefe_Ventas | Todas (6) |
| Gerente | Todas (6) |
| Admin | Todas (6) + panel admin |
| Guest | Ninguna |

---

## 🚀 Instalación Local (Desarrollo)

### Prerequisitos
- Python 3.11+
- ODBC Driver 17 for SQL Server
- pip

### Setup

```bash
# 1. Clonar y entrar al directorio
cd backend

# 2. Crear entorno virtual
python -m venv venv
# Windows:
venv\Scripts\activate

# 3. Instalar dependencias
pip install -r requirements.txt

# 4. Configurar variables de entorno
cp .env.example .env
# Editar .env con credenciales reales

# 5. Ejecutar servidor
uvicorn main:app --reload --host 0.0.0.0 --port 8000
```

### Verificar instalación

```bash
curl http://localhost:8000/health
# {"status": "ok", "version": "0.1.0"}
```

---

## 🧪 Tests

```bash
cd backend

# Ejecutar todos los tests
python -m pytest tests/ -v

# Con cobertura
python -m pytest tests/ --cov=. --cov-report=term-missing

# Test específico
python -m pytest tests/test_guards.py -v
```

**Estado actual:** 208 tests, 92% cobertura

---

## 🌐 API Endpoints

### `GET /health`
Estado del servicio.

```json
{"status": "ok", "version": "0.1.0"}
```

### `POST /api/chat`
Consulta en lenguaje natural.

**Request:**
```json
{"question": "¿Cuáles fueron las ventas de agosto 2026?"}
```

**Response:**
```json
{
  "status": "success",
  "response": "En el período 2026-08 (Global): ventas totales S/ 850,000.00, 320 pedidos, 95 clientes.",
  "sources": [{"tool": "get_sales_summary", "source": "SAP/SQL", "timestamp": "..."}],
  "tokens_used": null,
  "error_message": null
}
```

### `GET /api/tools`
Herramientas disponibles para el usuario autenticado.

```json
{"user_id": "usr-001", "allowed_tools": ["get_sales_summary", "get_sales_targets"]}
```

---

## 📁 Estructura del Proyecto

```
backend/
├── main.py                  # FastAPI app + endpoints
├── config.py                # Settings (pydantic-settings)
├── requirements.txt         # Dependencias Python
├── .env.example             # Template de variables
├── Dockerfile               # Contenedor Docker
├── .dockerignore
│
├── connectors/              # Conexiones a fuentes de datos
│   ├── base_connector.py    # Clase base + validación read-only
│   ├── entra_connector.py   # Microsoft Entra ID / Azure AD
│   ├── sql_connector.py     # Azure SQL + SQL Server local (SIG)
│   ├── sap_connector.py     # SAP base (REST)
│   └── c4c_connector.py     # SAP C4C OData + SAP ERP
│
├── tools/                   # 6 herramientas de consulta
│   ├── schemas.py           # Pydantic params por herramienta
│   ├── utils.py             # Pre-agregación, caché, formato
│   ├── sales_tools.py       # summary, targets, forecast, performance
│   ├── customer_tools.py    # customer_insights
│   └── inventory_tools.py   # inventory_by_sales
│
├── guards/                  # Seguridad
│   ├── rbac.py              # Validación de roles
│   ├── audit.py             # Registro de auditoría
│   └── sanitization.py      # Sanitización de input
│
├── layers/
│   └── orchestrator.py      # Routing pregunta → herramienta
│
├── models/                  # Pydantic models
│   ├── user.py              # User, Role, Permission
│   ├── query.py             # QueryRequest, QueryResponse
│   └── audit.py             # AuditLog
│
└── tests/                   # 208 tests, 92% cobertura
    ├── test_connectors.py
    ├── test_sap_connectors.py
    ├── test_tools_utils.py
    ├── test_sales_tools.py
    ├── test_customer_inventory_tools.py
    ├── test_guards.py
    ├── test_orchestrator.py
    ├── test_e2e.py
    └── test_security.py
```

---

## ⚙️ Variables de Entorno

Ver `.env.example` para lista completa. Variables críticas:

| Variable | Descripción |
|----------|------------|
| `AZURE_SQL_SERVER` | Servidor Azure SQL (SAP SD data) |
| `AZURE_SQL_DATABASE` | Nombre de BD Azure |
| `AZURE_SQL_USER` | Usuario solo-lectura Azure SQL |
| `AZURE_SQL_PASSWORD` | Contraseña Azure SQL |
| `SQL_SERVER` | Servidor SQL local (SIG — forecast/metas) |
| `SQL_DATABASE` | Nombre de BD local (SIG) |
| `ENTRA_TENANT_ID` | Azure AD Tenant ID |
| `ENTRA_CLIENT_ID` | Azure AD App Client ID |
| `ENTRA_CLIENT_SECRET` | Azure AD App Secret |
| `DEEPSEEK_API_KEY` | Clave Deepseek API (LLM) |

---

## 🗺️ Roadmap

| Fase | Estado | Descripción |
|------|--------|-------------|
| **Fase 0** | ✅ Completo | Piloto Ventas — 6 tools, Azure SQL, Entra ID, Docker |
| Fase 1 | 📋 Planeado | Integración Qualtrics NPS, LLM routing con Claude Sonnet 5 |
| Fase 2 | 📋 Planeado | Inventario + Finanzas, SAP FSM |
| Fase 3 | 📋 Planeado | Rollout completo MT Industrial |

---

## 👤 Contacto

**Oscar Armando Núñez Vargas**  
Especialista IA — MT Industrial  
Email: onunez.sole@gmail.com
