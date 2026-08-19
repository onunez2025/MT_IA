# ECOSISTEMAIA — Fase 0 Design Document

**Proyecto:** Sistema Conversacional Corporativo (Corporate RAG) para MT Industrial  
**Fase:** Fase 0 (Piloto Ventas)  
**Responsable:** Oscar Armando Núñez Vargas  
**Fecha:** 20 de agosto de 2026  
**Estado:** En revisión (aprobación de diseño pendiente)

---

## 📋 TABLA DE CONTENIDOS

1. [Resumen Ejecutivo](#resumen-ejecutivo)
2. [Arquitectura de 6 Capas](#arquitectura-de-6-capas)
3. [Componentes y Herramientas](#componentes-y-herramientas)
4. [Autenticación y Seguridad](#autenticación-y-seguridad)
5. [Admin Panel](#admin-panel)
6. [Flujo de Datos End-to-End](#flujo-de-datos-end-to-end)
7. [Testing y Validación](#testing-y-validación)
8. [Estructura de Código](#estructura-de-código)
9. [Stack Tecnológico](#stack-tecnológico)
10. [Cronograma Fase 0](#cronograma-fase-0)
11. [Riesgos y Mitigación](#riesgos-y-mitigación)
12. [Decisiones de Diseño](#decisiones-de-diseño)

---

## 🎯 RESUMEN EJECUTIVO

**Objetivo Fase 0:**  
Construir un MVP (Minimum Viable Product) de SOLE AI que permita a vendedores de MT Industrial hacer consultas en lenguaje natural sobre ventas, metas, forecast e inventario, obteniendo respuestas en < 10 segundos con garantía de solo lectura (read-only) y trazabilidad completa.

**Alcance Fase 0:**
- ✅ Autenticación via Microsoft Entra ID (Azure AD)
- ✅ Acceso a SAP C4C, SAP FSM, SQL Central
- ✅ 6 herramientas principales (sales_summary, targets, forecast, etc.)
- ✅ RBAC (Role-Based Access Control) básico para Ventas
- ✅ Garantía read-only en todas las consultas
- ✅ Auditoría completa (quién, qué, cuándo, costo en tokens)
- ✅ Admin panel para gestión de usuarios/roles
- ✅ Piloto con 3+ vendedores reales (19 oct — 15 feb 2027)

**No incluido en Fase 0:**
- ❌ Integración RRHH/Legal (→ Fase 2)
- ❌ Generación de documentos (PPT/Excel) (→ Fase 1.5)
- ❌ Investigación externa (noticias, competencia) (→ Fase 1.5)
- ❌ Modelos locales (futuro, evaluación post-Fase 0)

**Modelo de IA Seleccionado:**  
**Deepseek API** (para Fase 0 pruebas/desarrollo por costo)  
Se evalúa Claude Sonnet 5 post-piloto para Fase 1+ según resultados

**Estimado de Costo Fase 0:**  
$50-150/mes (Deepseek) vs. $150-350/mes (Claude Sonnet 5)

---

## 🏗️ ARQUITECTURA DE 6 CAPAS

### Diagrama General

```
┌──────────────────────────────────────────────────────────────┐
│ Capa 1: SOLE AI PORTAL (Interfaz de Usuario)                │
│ Web browser / Teams / Mobile apps                            │
├──────────────────────────────────────────────────────────────┤
│ Capa 2: Microsoft Entra ID (Autenticación & Identidad)       │
│ SSO + MFA + Identificación de rol (sin login adicional)      │
├──────────────────────────────────────────────────────────────┤
│ Capa 3: SOLE AI GATEWAY (Orquestación de Seguridad)          │
│ Validación RBAC · Auditoría · Guardrails · Rate Limiting    │
├──────────────────────────────────────────────────────────────┤
│ Capa 4: AGENT ORCHESTRATOR (Enrutamiento por Dominio)        │
│ Selección de herramientas · Validación semántica             │
├──────────────────────────────────────────────────────────────┤
│ Capa 5: MEMORIA + IA                                         │
│ ┌─────────────────────┬──────────────────────────┐          │
│ │ SOLE MEMORY         │ AI MODELS                │          │
│ │ (Vector DB + RAG +  │ (Deepseek API primario  │          │
│ │  Histórico)         │  + evaluación Claude)   │          │
│ └─────────────────────┴──────────────────────────┘          │
├──────────────────────────────────────────────────────────────┤
│ Capa 6: FUENTES DE DATOS (Fase 0 — Ventas)                  │
│ SQL Central | SAP C4C | SAP FSM | Qualtrics                 │
└──────────────────────────────────────────────────────────────┘
```

### Flujo de Conversación

```
Usuario pregunta en SOLE AI Portal (español natural)
    ↓
Entra ID valida identidad + rol
    ↓
Gateway valida permisos RBAC
    ↓
Orchestrator identifica intent + selecciona herramientas
    ↓
Para cada herramienta:
  • Conectar a API/BD via conector
  • Validar permisos del usuario
  • Pre-agregar datos (nunca tablas crudas)
  • Cachear si aplica
    ↓
Pasar contexto pre-agregado a Deepseek
    ↓
Deepseek formula respuesta en lenguaje natural
    ↓
Gateway audita (usuario, tool, costo, timestamp, status)
    ↓
Portal renderiza respuesta + citas de fuentes
    ↓
Usuario recibe respuesta en < 10 segundos
```

---

## 🔧 COMPONENTES Y HERRAMIENTAS

### Herramientas Fase 0 (6 principales)

| ID | Herramienta | Fuente | Descripción | Pre-Agregación | RBAC |
|----|-------------|--------|-------------|----------------|------|
| T1 | `get_sales_summary` | SAP ERP (SD) | Total ventas por período/región/cliente | SUM, COUNT, AVG, Trend% | Ventas, Finanzas, Admin |
| T2 | `get_sales_targets` | SQL Central / C4C | Meta vs realizado por vendedor/equipo | % Cumplimiento, Δ vs meta | Ventas, Finanzas, Admin |
| T3 | `get_sales_forecast` | SQL Central | Forecast de ventas futuras | Agregado mes/trimestre/región | Ventas, Finanzas, Admin |
| T4 | `get_customer_insights` | C4C + Qualtrics | Cliente, histórico, satisfacción NPS | Métricas agregadas, no PII | Ventas, Admin |
| T5 | `get_sales_performance` | C4C + SQL | Ranking vendedores, tendencias | Comparativas calculadas | Ventas, Finanzas, Admin |
| T6 | `get_inventory_by_sales` | SAP FSM / SQL | Stock disponible (lectura) | Totales por categoría/SKU | Ventas, UN Institucional, Admin |

### Estructura de Archivos (Backend)

```
backend/
├── main.py                           # FastAPI app
├── config.py                         # Configuración: env vars, secretos
├── .env                              # Credenciales read-only (NO en git)
├── .env.example                      # Template para variables
│
├── layers/
│   ├── gateway.py                    # Capa 3: RBAC + Auditoría
│   ├── orchestrator.py               # Capa 4: Enrutamiento de tools
│   └── ai_engine.py                  # Capa 5: Wrapper Deepseek API
│
├── tools/                            # Capa 4: Definición de herramientas
│   ├── __init__.py
│   ├── sales_tools.py                # T1-T5 (ventas)
│   ├── inventory_tools.py            # T6 (inventario)
│   ├── schemas.py                    # Pydantic models para tools
│   └── utils.py                      # Helpers: agregación, caché
│
├── connectors/                       # Capa 6: Conectores a APIs/BDs
│   ├── sap_connector.py              # SAP ERP REST API
│   ├── c4c_connector.py              # SAP C4C OData
│   ├── fsm_connector.py              # SAP FSM REST API
│   ├── sql_connector.py              # SQL Central (pyodbc)
│   ├── qualtrics_connector.py        # Qualtrics API
│   └── entra_connector.py            # Microsoft Entra ID
│
├── guards/                           # Seguridad
│   ├── rbac.py                       # Validación de permisos
│   ├── audit.py                      # Log inmutable de auditoría
│   ├── sanitization.py               # Bloqueo INSERT/UPDATE/DELETE
│   └── rate_limiter.py               # Límite de consultas por usuario/min
│
├── models/                           # Pydantic models
│   ├── user.py                       # User, Role, Permission
│   ├── query.py                      # QueryRequest, QueryResponse
│   ├── audit.py                      # AuditLog, RBACChangeLog
│   └── admin.py                      # Admin models
│
├── rag/                              # RAG (Fase 0 básico)
│   ├── vector_store.py               # Vector DB (MongoDB recomendado)
│   ├── embeddings.py                 # VoyageAI embeddings
│   ├── memory.py                     # Histórico conversaciones
│   └── context_builder.py            # Construir contexto para LLM
│
├── admin/                            # Admin panel backend
│   ├── routes.py                     # Endpoints: /admin/*
│   ├── service.py                    # Lógica de negocio RBAC
│   └── validators.py                 # Validación cambios RBAC
│
├── tests/
│   ├── test_sales_tools.py           # Unit + E2E tests
│   ├── test_security.py              # Tests RBAC + read-only
│   ├── test_performance.py           # Latencia + tokens
│   └── fixtures.py                   # Mock data
│
├── requirements.txt                  # Dependencias
├── .gitignore                        # Excluir .env, __pycache__
└── README.md                         # Instrucciones setup
```

### Ejemplo: Herramienta `get_sales_summary`

```python
# tools/sales_tools.py
from datetime import datetime
from typing import Optional, Dict, Any

async def get_sales_summary(
    period: str,           # Ej: "2026-08", "2026-Q3"
    region: Optional[str] = None,
    user_id: str = None,
) -> Dict[str, Any]:
    """
    Retorna resumen agregado de ventas.
    
    GARANTÍAS:
    - Pre-agregado: SUM, COUNT, AVG (nunca tabla cruda)
    - Read-only: query bloqueada si contiene INSERT/UPDATE/DELETE
    - RBAC: user_id validado antes de ejecutar
    
    Args:
        period: "2026-08" o "2026-Q3" o "2026"
        region: Opcional, filtro por región
        user_id: Para auditoría
    
    Returns:
        dict con: total_sales, num_orders, customers, avg_order_value, trend_vs_prior
    """
    
    # 1. Validar RBAC
    if not await validate_rbac(user_id, "get_sales_summary"):
        raise PermissionError(f"User {user_id} sin acceso a ventas")
    
    # 2. Conectar a SAP ERP y ejecutar query pre-agregada
    query = """
    SELECT 
        SUM(AMOUNT) as total_sales,
        COUNT(*) as num_orders,
        COUNT(DISTINCT CUSTOMER_ID) as num_customers,
        AVG(AMOUNT) as avg_order_value
    FROM SALES
    WHERE PERIOD = ? AND REGION = ?
    """
    
    result = await sap_connector.query_readonly(query, (period, region or "ALL"))
    
    # 3. Calcular trend vs período anterior
    prior_period = calculate_prior_period(period)
    prior_result = await sap_connector.query_readonly(
        query, (prior_period, region or "ALL")
    )
    
    trend_pct = ((result["total_sales"] - prior_result["total_sales"]) 
                 / prior_result["total_sales"] * 100)
    
    # 4. Retornar pre-agregado (NO tablas crudas)
    return {
        "period": period,
        "region": region or "Global",
        "total_sales": float(result["total_sales"]),
        "num_orders": int(result["num_orders"]),
        "num_customers": int(result["num_customers"]),
        "avg_order_value": float(result["avg_order_value"]),
        "trend_vs_prior_pct": round(trend_pct, 2),
        "timestamp": datetime.utcnow().isoformat(),
    }
```

---

## 🔐 AUTENTICACIÓN Y SEGURIDAD

### Capa 2: Microsoft Entra ID

**Flujo:**
1. Usuario abre portal SOLE AI
2. Redirige a Entra ID (OAuth 2.0)
3. Usuario autentica con credencial corporativa MT Industrial
4. Entera ID retorna `id_token` + grupo/role
5. Gateway extrae `user_id`, `email`, `roles` del token
6. Usuario conectado (sin login adicional requerido)

**Configuración Requerida (por Manuel/TI):**
- Registrar aplicación SOLE AI en Entra ID
- Configurar redirect URI: `https://{portal-domain}/callback`
- Asignar grupos: "SOLE_Ventas", "SOLE_Finanzas", "SOLE_Admin"

---

### Capa 3: Gateway (RBAC + Validación)

**Matriz de Permisos Fase 0:**

| Rol | Herramientas Permitidas | Datos Visibles |
|-----|-------------------------|----------------|
| **Ventas** (Martin Castro + equipo) | T1, T2, T3, T4, T5, T6 | Todas ventas, clientes, inventario |
| **UN Institucional** | T1 (global only), T6 (global only) | Ventas agregadas (sin detalles) |
| **Finanzas** (Kevin Gomez) | T1, T2, T3 | Todas (para análisis financiero) |
| **Oscar (Admin/Dev)** | Todas (para testing) | Todas |
| **Manuel (TI)** | T1-T6 (lectura) | Todas (auditoría) |

**Validación en Tiempo Real:**

```python
# layers/gateway.py

async def validate_request(
    user_id: str,
    tool_name: str,
    params: dict,
) -> bool:
    """
    Pre-ejecución: ¿Este usuario puede usar esta herramienta?
    """
    # 1. Traer rol desde cache (refresh cada 5 min desde Entra ID)
    user_roles = await entra_cache.get_roles(user_id)
    
    # 2. Consultar matriz RBAC
    rbac_matrix = await rbac_service.get_matrix()
    allowed_tools = rbac_matrix.get(user_roles[0], [])
    
    # 3. Validar
    if tool_name not in allowed_tools:
        await audit_log.log_blocked_access(
            user_id, tool_name, "RBAC_DENIED"
        )
        raise PermissionError(
            f"Rol '{user_roles[0]}' no permitido para '{tool_name}'"
        )
    
    # 4. Validar parametros (no intenten acceder a datos de otros usuarios sin permisos)
    if not await validate_data_access(user_id, user_roles, params):
        await audit_log.log_blocked_access(
            user_id, tool_name, "DATA_ACCESS_DENIED"
        )
        raise PermissionError("Sin acceso a estos datos específicos")
    
    return True
```

---

### Garantía Read-Only (3 Niveles)

**Nivel 1: Credenciales Admin → Usuario Read-Only**

Configuración única (antes del 31 ago):

```
SAP ERP:
  Usuario: IA_READONLY_VENTAS
  Permisos: SELECT solo en tablas SD (Sales & Distribution)
  Roles: READ_SALES_MASTER

SAP C4C:
  Usuario: IA_READONLY
  Rol: View (no Edit)

SQL Server:
  Usuario: IA_READONLY
  Permisos: SELECT en tablas permitidas
  Roles: db_datareader (no db_datawriter)

Qualtrics:
  API Key: scope = "read_survey_data" (sin create/edit)
```

**Nivel 2: Bloqueo en FastAPI**

```python
# guards/sanitization.py

def validate_query_is_readonly(query: str) -> bool:
    """
    Rechaza INSERT, UPDATE, DELETE, DROP, ALTER, EXEC, etc.
    """
    forbidden = [
        "INSERT", "UPDATE", "DELETE", "DROP", "TRUNCATE",
        "ALTER", "EXEC", "EXECUTE", "GRANT", "REVOKE", "CREATE"
    ]
    
    query_upper = query.upper()
    for keyword in forbidden:
        if keyword in query_upper:
            raise PermissionError(
                f"Operación '{keyword}' bloqueada. "
                f"Solo lectura permitida."
            )
    
    return True

# Usado en cada conector
async def query_sql(query: str):
    validate_query_is_readonly(query)  # ← Bloquea antes de ejecutar
    return await sql_connector.execute(query)
```

**Nivel 3: Validación Semántica**

```python
# guards/rbac.py

readonly_tools = {
    "get_sales_summary": ["period", "region"],        # Solo filtros
    "get_sales_targets": ["vendor_id", "year"],
    "get_customer_insights": ["customer_id"],
    # Cada tool define qué parámetros son "read-only seguros"
}

async def validate_tool_is_readonly(tool_name: str, params: dict) -> bool:
    if tool_name not in readonly_tools:
        raise PermissionError(f"Tool '{tool_name}' no es read-only")
    
    allowed = readonly_tools[tool_name]
    for param in params.keys():
        if param not in allowed:
            raise PermissionError(
                f"Parámetro '{param}' no seguro en '{tool_name}'"
            )
    
    return True
```

---

### Auditoría Completa

Todas las consultas se registran en BD de auditoría:

```python
# guards/audit.py

async def log_query(
    user_id: str,
    tool_name: str,
    params: dict,
    result_row_count: int,
    status: str,  # "SUCCESS" | "BLOCKED" | "ERROR"
    tokens_used: int,
    response_time_ms: float,
    timestamp: datetime,
):
    audit_entry = {
        "timestamp": timestamp,
        "user_id": user_id,
        "user_roles": await entra_connector.get_user_roles(user_id),
        "tool": tool_name,
        "params": params,  # Se loguean (no sensibles, solo filtros)
        "status": status,
        "result_row_count": result_row_count,
        "tokens_deepseek": tokens_used,
        "response_time_ms": response_time_ms,
        "ip_address": request.client.host,
        "user_agent": request.headers.get("user-agent"),
    }
    
    await audit_collection.insert_one(audit_entry)
    
    # Alerta si intento bloqueado
    if status == "BLOCKED":
        await alert_ti(
            f"⚠️ Acceso bloqueado: {user_id} intentó {tool_name} "
            f"desde {request.client.host}"
        )
```

**Consultas de Auditoría:**
- "¿Quién consultó qué?" → /admin/audit?user_id=X&start_date=&end_date=
- "¿Cuántos tokens consumimos?" → /admin/audit?metric=tokens&period=week
- "¿Hay intentos sospechosos?" → Alertas automáticas si status=BLOCKED

---

## 👨‍💼 ADMIN PANEL

### Interfaz Principal

```
┌─────────────────────────────────────────────────────────┐
│  SOLE AI — Admin Dashboard                              │
├─────────────────────────────────────────────────────────┤
│                                                          │
│  📊 DASHBOARD  |  👤 USUARIOS  |  🎭 ROLES  |  🔑 PERMISOS
│                                                          │
├─────────────────────────────────────────────────────────┤
│                                                          │
│  TAB: 📊 DASHBOARD DE USO                               │
│  ├─ Consultas esta semana: 247                          │
│  ├─ Tokens consumidos: 1.2M (Deepseek)                  │
│  ├─ Costo estimado: $15.80                              │
│  ├─ Usuarios activos: 8 / 10                            │
│  │                                                       │
│  ├─ Top herramientas:                                   │
│  │  1. get_sales_summary (142 calls)                    │
│  │  2. get_sales_targets (85 calls)                     │
│  │  3. get_customer_insights (20 calls)                 │
│  │                                                       │
│  └─ Alertas RBAC:                                       │
│     • 3 intentos acceso bloqueado (yesterday)           │
│     • 1 usuario sin consultas 30 días (posible inactivo)│
│                                                          │
│  TAB: 👤 GESTIÓN DE USUARIOS                            │
│  ┌──────────────────────────────────────────────────┐   │
│  │ Filtro: [Rol: Ventas ▼] [Estado: Activo ▼]     │   │
│  ├──────────────────────────────────────────────────┤   │
│  │ Usuario      | Email           | Rol    | 🗑 Acciones
│  ├──────────────────────────────────────────────────┤   │
│  │ Martin      | martin@mtind... | Ventas | ✏️ 🗑  │   │
│  │ Kevin       | kevin@mtind...  | Fin.   | ✏️ 🗑  │   │
│  │ Oscar (YOU) | oscar@mtind...  | Admin  | ✏️ 🗑  │   │
│  └──────────────────────────────────────────────────┘   │
│  [+ Agregar Usuario]                                    │
│                                                          │
│  TAB: 🎭 GESTIÓN DE ROLES                               │
│  ┌──────────────────────────────────────────────────┐   │
│  │ Rol          | Tools (N) | Usuarios (N) | Editar│    │
│  ├──────────────────────────────────────────────────┤   │
│  │ Ventas       | 6 tools   | 8 usuarios   | ✏️    │    │
│  │ Finanzas     | 3 tools   | 2 usuarios   | ✏️    │    │
│  │ Admin        | All       | 2 usuarios   | ✏️    │    │
│  └──────────────────────────────────────────────────┘   │
│  [+ Crear Rol]                                          │
│                                                          │
└─────────────────────────────────────────────────────────┘
```

### Endpoints Admin API

```
GET    /admin/dashboard              — Stats generales
GET    /admin/users                  — Listar usuarios
POST   /admin/users                  — Crear usuario
PUT    /admin/users/{user_id}        — Editar usuario
DELETE /admin/users/{user_id}        — Desactivar usuario

GET    /admin/roles                  — Listar roles
POST   /admin/roles                  — Crear rol
PUT    /admin/roles/{role_id}        — Editar rol
DELETE /admin/roles/{role_id}        — Eliminar rol

POST   /admin/roles/{role_id}/tools  — Asignar tool a rol
DELETE /admin/roles/{role_id}/tools/{tool} — Revocar tool

GET    /admin/audit-log              — Ver historial auditoría
GET    /admin/rbac-changes           — Ver cambios de permisos
```

### Seguridad del Admin Panel

- ✅ Solo usuarios con rol "Admin" pueden acceder
- ✅ Todos los cambios RBAC se auditan (quién, qué, cuándo)
- ✅ Cambios aplican inmediatamente (cache refresh)
- ✅ Validación: NO crear usuarios/roles sin validar en Entra ID

---

## 📊 FLUJO DE DATOS END-TO-END

### Ejemplo Completo: Usuario Pregunta

**Escenario:** Martin Castro (Ventas) pregunta "¿Cuál fue el volumen de ventas en agosto 2026?"

**Timeline (< 10 segundos):**

```
T=0ms:    Usuario escribe pregunta en portal
          "¿Cuál fue el volumen de ventas en agosto 2026?"

T=50ms:   Portal envía POST /api/chat
          {
            "user_id": "martin@mtind.com",
            "question": "¿Cuál fue el volumen de ventas en agosto 2026?",
            "conversation_id": "conv-abc123"
          }

T=100ms:  GATEWAY recibe request
          ├─ Valida token Entra ID ✓
          ├─ Extrae roles: ["Ventas"]
          ├─ Log inicio: user_id, timestamp, pregunta
          └─ Start timer

T=150ms:  ORCHESTRATOR analiza pregunta
          ├─ NLP: intent = "consultar_ventas"
          ├─ Extrae parámetros: {"period": "2026-08"}
          ├─ Selecciona tool: "get_sales_summary"
          ├─ Valida RBAC: Ventas ✓ tiene acceso a T1
          └─ Valida params: {"period"} ✓ permitido

T=200ms:  EJECUTAR HERRAMIENTA: get_sales_summary()
          ├─ Conectar SAP ERP con user IA_READONLY_VENTAS
          ├─ Ejecutar:
          │  SELECT SUM(amount) as total,
          │         COUNT(*) as orders,
          │         AVG(amount) as avg
          │  FROM sales WHERE month='2026-08'
          ├─ Query bloqueada por sanitization (readonly ✓)
          ├─ Resultado pre-agregado:
          │  {
          │    "total_sales": 245000.50,
          │    "num_orders": 127,
          │    "avg_order_value": 1929.45,
          │    "trend_vs_july": "+12%"
          │  }
          └─ Cache resultado (1 hora)

T=1000ms: DEEPSEEK genera respuesta
          ├─ Enviar context a API Deepseek:
          │  {
          │    "system": "Eres asistente de ventas MT Industrial...",
          │    "tools_available": [
          │      {
          │        "name": "get_sales_summary",
          │        "description": "...",
          │        "parameters": {...}
          │      }
          │    ],
          │    "context": {
          │      "role": "Ventas",
          │      "available_data": {
          │        "sales_august_2026": {
          │          "total_sales": 245000.50,
          │          "num_orders": 127,
          │          "trend": "+12%"
          │        }
          │      }
          │    },
          │    "messages": [
          │      {
          │        "role": "user",
          │        "content": "¿Cuál fue el volumen de ventas agosto 2026?"
          │      }
          │    ]
          │  }
          │
          └─ Deepseek responde en ~2 seg:
             "El volumen de ventas en agosto 2026 fue de $245,000.50,
              con 127 órdenes (promedio $1,929.45). Esto representa
              un incremento del 12% respecto a julio."

T=3200ms: GATEWAY AUDITA y RETORNA
          ├─ Log resultado:
          │  {
          │    "user_id": "martin@mtind.com",
          │    "tool": "get_sales_summary",
          │    "status": "SUCCESS",
          │    "tokens_used": 610,
          │    "response_time_ms": 3200,
          │    "timestamp": "2026-08-20T14:35:22Z"
          │  }
          │
          ├─ Response a portal:
          │  {
          │    "status": "success",
          │    "response": "El volumen de ventas en agosto...",
          │    "sources": [
          │      {
          │        "tool": "get_sales_summary",
          │        "source": "SAP ERP",
          │        "timestamp": "2026-08-20T14:35:22Z"
          │      }
          │    ],
          │    "tokens_used": 610
          │  }

T=3250ms: PORTAL RENDERIZA
          Usuario ve:
          ┌────────────────────────────────────────────────┐
          │ RESPUESTA (Fuente: SAP ERP, 20/08/2026 14:35) │
          │                                                │
          │ El volumen de ventas en agosto 2026 fue de    │
          │ $245,000.50 USD, con 127 órdenes registradas.│
          │ Incremento del 12% vs. julio.                │
          │                                                │
          │ [💬 Hacer otra pregunta] [📊 Ver detalles]   │
          └────────────────────────────────────────────────┘

T=3250ms: ✅ TIEMPO TOTAL: 3.25 segundos (< 10 seg target)
          ✅ 0 alucinaciones (datos reales de SAP)
          ✅ Auditoría completa registrada
          ✅ Costo: ~$0.002 (610 tokens × $0.003/1M)
```

---

## 🧪 TESTING Y VALIDACIÓN

### Estrategia de Testing

| Nivel | Pruebas | Ejemplo | Target |
|-------|---------|---------|--------|
| **Unit** | Tools en aislamiento | `get_sales_summary()` retorna dict | 95% coverage |
| **Integration** | Tools + connectors | Conexión SAP funciona | 0 fallos |
| **E2E** | Pregunta completa | Pregunta → respuesta < 5s | 5/5 pasan |
| **Security** | RBAC + read-only | Usuario bloqueado si no autorizado | 0 brechas |
| **Performance** | Latencia + tokens | < 10 seg, < 1000 tokens promedio | 95% queries |

### Test Cases Críticos

```python
# tests/test_sales_tools.py

class TestSalesTools:
    
    async def test_get_sales_summary_aggregated_only():
        """Unit: Retorna pre-agregado, nunca tabla cruda"""
        result = await get_sales_summary(period="2026-08")
        
        assert "total_sales" in result
        assert "num_orders" in result
        assert "raw_rows" not in result  # ← Tabla cruda bloqueada
    
    async def test_rbac_blocks_unauthorized():
        """Security: Usuario sin permiso bloqueado"""
        user_id = "random@mtind.com"  # No en Ventas
        
        with pytest.raises(PermissionError):
            await validate_request(user_id, "get_sales_summary")
    
    async def test_sanitization_blocks_delete():
        """Security: DELETE statement bloqueado"""
        malicious = "DELETE FROM sales WHERE id=1"
        
        with pytest.raises(PermissionError):
            validate_query_is_readonly(malicious)
    
    async def test_e2e_response_latency():
        """E2E: Respuesta < 5 segundos"""
        import time
        start = time.time()
        
        response = await orchestrator.process_question(
            user_id="martin@mtind.com",
            question="¿Cuál fue volumen agosto 2026?"
        )
        
        elapsed = time.time() - start
        assert response["status"] == "success"
        assert elapsed < 5  # Garantía
```

### Validación Pre-Producción (Hito 5)

Antes de 19 oct (piloto producción):

✅ **Seguridad:**
- 0 fallos en tests RBAC
- 0 alucinaciones en datos sensibles (50 respuestas manuales)
- 0 accesos no-autorizados en auditoría

✅ **Performance:**
- Latencia promedio < 8 seg
- Consumo tokens < $150/mes
- 95%+ queries exitosas

✅ **Adoption:**
- 3+ vendedores usando diariamente
- > 50 consultas/semana
- Feedback positivo

---

## 💾 ESTRUCTURA DE CÓDIGO

### Inicialización (setup.py)

```python
# setup.py / main.py startup

import asyncio
from fastapi import FastAPI
from layers.gateway import Gateway
from layers.orchestrator import Orchestrator
from layers.ai_engine import DeepseekEngine

app = FastAPI(title="SOLE AI - Fase 0")

# 1. Validar credenciales read-only están disponibles
async def startup_event():
    print("🚀 Iniciando SOLE AI Fase 0...")
    
    # Validar todas las conexiones
    await sap_connector.validate_connection()
    await c4c_connector.validate_connection()
    await sql_connector.validate_connection()
    await entra_connector.validate_connection()
    
    # Cargar matriz RBAC en cache
    await rbac_service.load_matrix()
    
    # Inicializar Deepseek client
    ai_engine = DeepseekEngine(api_key=config.DEEPSEEK_API_KEY)
    
    print("✅ Todas las conexiones OK. Sistema listo.")

app.add_event_handler("startup", startup_event)

# 2. Endpoint principal: chat
@app.post("/api/chat")
async def chat(request: QueryRequest):
    user_id = request.user_id
    question = request.question
    
    # Procesar request
    response = await orchestrator.process_question(user_id, question)
    
    return response
```

---

## 🛠️ STACK TECNOLÓGICO

### Backend

| Componente | Tecnología | Justificación |
|------------|-----------|---------------|
| **Framework** | FastAPI (Python) | Async, rápido, tipado, auditoría fácil |
| **LLM API** | Deepseek (Fase 0) | 70% más barato que Claude Sonnet 5 |
| **Autenticación** | Microsoft Entra ID | SSO corporativo existente |
| **Base de Datos** | SQL Server (MT) | Existe, T-SQL, acceso directo |
| **Vector DB** | MongoDB (futuro RAG) | Flexible, escalable |
| **Embeddings** | VoyageAI (futuro) | Mayor integración |
| **Conectores SAP** | SAP Connector (REST/OData) | APIs nativas SAP |
| **Cache** | Redis (opcional) | Pre-caché 1 hora resultados |
| **Auditoría** | MongoDB + SQL Server | Logs inmutables |

### Frontend (Fase 1)

| Componente | Tecnología |
|-----------|-----------|
| **Framework** | Vue.js / React |
| **UI Components** | Shadcn UI / Material |
| **State** | Pinia / Redux |
| **API Client** | Axios / Fetch |

### DevOps

| Componente | Tecnología |
|-----------|-----------|
| **Hosting** | Azure (Manuel/TI) |
| **Container** | Docker |
| **Orquestación** | Kubernetes (futuro) |
| **CI/CD** | GitHub Actions (futuro) |

### Dependencias Python (requirements.txt)

```
fastapi==0.104.1
uvicorn==0.24.0
python-dotenv==1.0.0
pydantic==2.4.2

# Connectors
pyodbc==5.0.1          # SQL Server
requests==2.31.0       # REST APIs (SAP)
msgraph-core==0.2.2    # Azure AD

# LLM / RAG
deepseek-client==0.1.0  # Deepseek API (provisional)
llamaindex==0.9.0
voyageai==0.1.0        # Embeddings

# Database
pymongo==4.6.0         # Vector DB + audit logs
sqlalchemy==2.0.23

# Testing
pytest==7.4.3
pytest-asyncio==0.21.1
pytest-cov==4.1.0

# Monitoring
python-json-logger==2.0.7
opentelemetry-api==1.21.0
```

---

## 📅 CRONOGRAMA FASE 0

| ID | Tarea | Responsable | Duración | Inicio | Fin | Hito |
|----|-------|-------------|----------|--------|-----|------|
| 1 | **Aprobación diseño** | Oscar + Manuel | 5 días | 20/08 | 25/08 | ✓ H1 |
| 2 | **Acceso APIs SAP** | Manuel (TI) | 12 días | 26/08 | 06/09 | ✓ H2 |
| 3 | **Catálogo preguntas Ventas** | Oscar + Martin | 5 días | 26/08 | 30/08 | ✓ H3 |
| 4 | **Setup ambiente dev** | Oscar | 7 días | 31/08 | 06/09 |  |
| 5 | **Develop connectors** | Oscar | 12 días | 07/09 | 18/09 |  |
| 6 | **Develop tools** | Oscar | 12 días | 07/09 | 18/09 |  |
| 7 | **Testing + ajustes** | Oscar | 10 días | 19/09 | 28/09 | ✓ H4 |
| 8 | **Medición tokens** | Oscar | 5 días | 29/09 | 03/10 |  |
| 9 | **Deploy staging** | Oscar + Manuel | 5 días | 04/10 | 08/10 |  |
| 10 | **Validación seguridad** | Manuel + Oscar | 7 días | 09/10 | 15/10 |  |
| 11 | **Deploy producción** | Oscar + Manuel | 4 días | 16/10 | 19/10 | ✓ H5 |
| 12 | **Piloto Ventas** | Ventas + Oscar | 120 días | 19/10 | 15/02 | ✓ H5 |
| 13 | **Evaluación piloto** | Oscar + Manuel | 5 días | 16/02 | 20/02 | ✓ H6 |

---

## ⚠️ RIESGOS Y MITIGACIÓN

| Riesgo | Severidad | Mitigación |
|--------|-----------|-----------|
| Acceso tardío a APIs SAP | ALTO | Hito 2 (31 ago) es no-negociable. Comunicar urgencia a Manuel día 1. Fallback: usar SQL Central como proxy si SAP retrasado. |
| Consumo tokens mayor presupuesto | MEDIO | Medir en Hito 8 (5 oct). Si > $150, escalar a Kevin Gomez. Opciones: optimizar prompts, cambiar a Claude Sonnet (más caro pero más eficiente), reducir frecuencia caché. |
| Alucinaciones del modelo | ALTO | Hardcodear herramientas (nunca generar queries dinámicamente). Validación manual de 50 respuestas en staging. Testing exhaustivo RBAC. |
| Oscar indisponible | ALTO | Documentar código bien. Héctor como backup (20% dedicación). Contacto directo con Manuel para escalación. |
| Baja adopción en Ventas | MEDIO | Capacitación temprana (semana 1 piloto). Demo con Martin. Quick wins: preguntas fáciles y útiles primero. |
| Performance < esperado | MEDIO | Optimizar queries SQL (índices). Cachear resultados. Pre-agregar datos. Monitor latencia en staging. |

---

## 🎯 DECISIONES DE DISEÑO

### Decisión 1: Modelo de IA (Deepseek vs. Claude)

**Opción A (Seleccionada):** Deepseek para Fase 0  
✅ 70% más barato ($50-150/mes vs. $150-350/mes)  
✅ Permite iterar rápido sin quebrar presupuesto  
✅ Cambiar a Claude después es trivial (swap en config)

**Opción B:** Claude Sonnet 5 desde inicio  
✅ Mayor calidad (función calling maduro, 200K token window)  
❌ Caro para prototipado  
❌ Difícil de justificar ante Kevin (Finanzas) sin validación

**Decisión:** Usar Deepseek Fase 0. Post-piloto, evaluar Claude si necesita mayor calidad.

---

### Decisión 2: Herramientas Pre-Definidas vs. Dinámicas

**Opción A (Seleccionada):** 6 herramientas pre-definidas  
✅ Seguridad garantizada (no generar queries dinámicamente)  
✅ RBAC fácil de auditar  
✅ Testing exhaustivo  
✅ Escalable a más herramientas en Fase 1

**Opción B:** Queries dinámicas (LLM genera SQL)  
❌ Alto riesgo de alucinaciones  
❌ Difícil controlar read-only  
❌ Más difícil de auditar

**Decisión:** 6 herramientas fijas. Escalar con más tools definidas conforme agreguemos funcionalidad.

---

### Decisión 3: Ubicación del Orchestrator

**Opción A (Seleccionada):** FastAPI local (backend)  
✅ Control total  
✅ Auditoría fácil  
✅ RBAC centralizadoV

**Opción B:** LangChain orchestration  
✅ Framework maduro  
❌ Menos control  
❌ Auditoría más compleja

**Decisión:** FastAPI. Usar LangChain/LlamaIndex como referencia pero architecture propia.

---

## ✅ LISTA DE VERIFICACIÓN PRE-IMPLEMENTACIÓN

- [ ] Aprobación de este design document (Manuel + Oscar)
- [ ] Confirmación acceso SAP C4C / SAP FSM (Manuel/TI)
- [ ] Catálogo de preguntas Ventas definido (Martin + Oscar)
- [ ] Credenciales read-only configuradas (TI)
- [ ] Entera ID app registrada (TI)
- [ ] Presupuesto Deepseek aprobado (Kevin/Finanzas)
- [ ] Ambiente dev setup (laptop Oscar + opcional staging Azure)
- [ ] Repo Git inicializado con .gitignore
- [ ] Dependencias Python en requirements.txt
- [ ] Tests framework setup (pytest)

---

## 📞 CONTACTOS Y ESCALACIONES

| Rol | Persona | Email | Tema |
|-----|---------|-------|------|
| **Ejecutivo** | Akinori Ando | akinori.ando@mtind.com | Decisiones estratégicas |
| **TI** | Manuel Calderón | manuel.calderon@mtind.com | Acceso APIs, infraestructura |
| **Ventas** | Martin Castro | martin.castro@mtind.com | Catálogo preguntas, piloto |
| **Finanzas** | Kevin Gomez | kevin.gomez@mtind.com | Presupuesto, tokens |
| **Especialista IA** | Oscar Núñez | oscar.nunez@mtind.com | Desarrollo principal |

---

**Documento Aprobado Por:**

- [ ] Oscar Armando Núñez Vargas (Especialista IA) — Fecha:
- [ ] Manuel Calderón Montoro (Jefe TI) — Fecha:
- [ ] Sergio González Vesga (Gerencia Atención al Cliente) — Fecha:

---

**Próximos Pasos Post-Aprobación:**

1. Invocar `writing-plans` skill para crear plan de implementación detallado
2. Iniciar Hito 1: Aprobación del diseño (28 ago)
3. Confirmar Hito 2: Acceso SAP (31 ago)
4. Comenzar desarrollo (14 sep)

---

*Documento Maestro Fase 0. Última actualización: 20 de agosto de 2026*
