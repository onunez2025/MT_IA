# EcosistemaIA — Proyecto Completo MT Industrial

**Documento Maestro para Claude Code y desarrollo**

---

## 📋 TABLA DE CONTENIDOS

1. [Contexto Empresarial](#contexto-empresarial)
2. [Visión y Objetivos](#visión-y-objetivos)
3. [Arquitectura del Sistema](#arquitectura-del-sistema)
4. [Cronograma Detallado](#cronograma-detallado)
5. [Equipo y Roles](#equipo-y-roles)
6. [Supuestos y Riesgos](#supuestos-y-riesgos)
7. [Requerimientos Funcionales](#requerimientos-funcionales)
8. [Requerimientos No-Funcionales](#requerimientos-no-funcionales)
9. [Matriz de Acceso (RBAC)](#matriz-de-acceso-rbac)
10. [Casos de Uso](#casos-de-uso)
11. [Integración de Datos](#integración-de-datos)
12. [Hitos Críticos](#hitos-críticos)
13. [Decisiones Pendientes](#decisiones-pendientes)
14. [Contactos Clave](#contactos-clave)

---

## 🏢 CONTEXTO EMPRESARIAL

### Organización: MT Industrial

**Presidente:** Sandro Sattler Finazzi

**Vicepresidente:** Akinori Ando

**Auditor Interno:** Julio Ugarte Espejo

### Estructura de Gerencias

| Gerencia | Jefe | Reporta a |
|---|---|---|
| Metusa | Benjamin Arrospide | Vicepresidencia |
| Innovación y Calidad | Cristhian Sevillano | Vicepresidencia |
| Marketing y Producto | Jessica Alva | Vicepresidencia |
| Admin, Finanzas y Operaciones | Juan Sanguineti Corzo | Vicepresidencia |
| └─ RRHH y Procesos | Andrea Cárdenas Silva | Juan Sanguineti |
| └─ Legal y Contratos | Renato Saldaña Jaimes | Juan Sanguineti |
| └─ Finanzas | Kevin Gomez | Juan Sanguineti |
| └─ Tecnología e Información | Manuel Calderón Montoro | Juan Sanguineti |
| └─ Cadena de Suministro | Alejandra Silva | Juan Sanguineti |
| └─ Almacén | Ana Flores | Juan Sanguineti |
| Ventas | Martin Castro Bravo (104 personas) | Juan Sanguineti |
| UN Institucional | Omar Barahona | Juan Sanguineti |
| **Atención al Cliente** | **Sergio González Vesga** | **Juan Sanguineti** |
| └─ **Oscar Armando Núñez Vargas** | **Especialista IA** | **Sergio González** |

---

## 🎯 VISIÓN Y OBJETIVOS

### Pilares Estratégicos (CEO)

1. **Información sin silos / Autoservicio:** Acceso democratizado a datos por rol
2. **Journey del cliente:** Optimización de la experiencia del cliente
3. **Gasto de personal no lineal con crecimiento:** Automatización que no requiere contratación proporcional
4. **Inventario y obsolescencia:** Gestión predictiva

### Objetivo Principal

Construir un **asistente conversacional corporativo (Corporate RAG)** que:
- Responda preguntas en lenguaje natural español
- Acceda a datos centrales (SQL, SAP C4C, SAP FSM, SharePoint, RRHH, Legal)
- Respete permisos por rol (RBAC)
- Genere documentos (PPT, Excel) automáticamente
- Permita investigación externa (noticias, competencia)
- Marque claramente datos vs. proyecciones
- Cumpla con requisitos legales (especialmente RRHH y Legal)

---

## 🏗️ ARQUITECTURA DEL SISTEMA

### 6 Capas

```
┌──────────────────────────────────────────────────────────────┐
│ Capa 1: SOLE AI PORTAL (Interfaz de Usuario)                │
│ Web / Teams / Mobile / Apps internas                         │
├──────────────────────────────────────────────────────────────┤
│ Capa 2: Microsoft Entra ID (Autenticación)                   │
│ SSO + MFA + RBAC + Identificación de rol                     │
├──────────────────────────────────────────────────────────────┤
│ Capa 3: SOLE AI GATEWAY (Orquestación de Seguridad)          │
│ Validación de permisos · Auditoría · Costos · Guardrails    │
├──────────────────────────────────────────────────────────────┤
│ Capa 4: AGENT ORCHESTRATOR (Enrutamiento por Dominio)        │
│ 8 dominios: Ventas, Finanzas, RRHH, Legal, etc.             │
├──────────────────────────────────────────────────────────────┤
│ Capa 5: MEMORIA E INTELIGENCIA                               │
│ ┌─────────────────────┬──────────────────────────────┐       │
│ │ SOLE MEMORY         │ AI MODELS                    │       │
│ │ (Corporate RAG +    │ (Claude principal +          │       │
│ │  Vector Search)     │  otros + Local LLM futuro)   │       │
│ └─────────────────────┴──────────────────────────────┘       │
├──────────────────────────────────────────────────────────────┤
│ Capa 6: FUENTES DE DATOS (Integraciones)                     │
│ SQL Central | SAP C4C/FSM | SharePoint | RRHH | Legal        │
└──────────────────────────────────────────────────────────────┘
```

### Flujo de Conversación

```
Usuario pregunta en español
    ↓
Entra ID valida identidad + rol
    ↓
Gateway valida permisos (RBAC)
    ↓
Orchestrator enruta a dominio correcto
    ↓
Claude genera respuesta con context de RAG
    ↓
Pre-agregación de datos (nunca tablas crudas)
    ↓
Respuesta + auditoría + costo registrado
    ↓
Usuario recibe respuesta citada con fuentes
```

---

## 📅 CRONOGRAMA DETALLADO

### FASE 0: PILOTO EN VENTAS (Ago 2026 — Feb 2027)

| ID | Tarea | Responsable | Inicio | Fin | Días |
|---|---|---|---|---|---|
| 1 | Aprobación de alcance (Fase 0) | Manuel / Oscar | 24/08/2026 | 28/08/2026 | 5 |
| 2 | Aprobación de presupuesto CAPEX | Finanzas / Manuel | 24/08/2026 | 28/08/2026 | 5 |
| 3 | Definir responsable técnico (Héctor / recurso) | Manuel | 24/08/2026 | 28/08/2026 | 5 |
| 4 | Acceso a APIs SAP C4C y SAP FSM | TI | 31/08/2026 | 11/09/2026 | 12 |
| 5 | Catálogo de preguntas del piloto - Ventas | Oscar / Ventas | 31/08/2026 | 04/09/2026 | 5 |
| 6 | Diseño de capa de permisos (RBAC piloto) | Oscar | 31/08/2026 | 11/09/2026 | 12 |
| 7 | Desarrollo del orquestador (prototipo) | Oscar | 14/09/2026 | 02/10/2026 | 19 |
| 8 | Integración con SQL central | Oscar | 14/09/2026 | 25/09/2026 | 12 |
| 9 | Testing y ajuste de prompts | Oscar | 05/10/2026 | 16/10/2026 | 12 |
| 10 | Medición de consumo real de tokens | Oscar | 12/10/2026 | 16/10/2026 | 5 |
| 11 | Ajuste de OPEX con datos reales | Oscar | 19/10/2026 | 23/10/2026 | 5 |
| 12 | **Piloto en producción - Ventas** | Ventas / Oscar | **19/10/2026** | **15/02/2027** | **120** |
| 13 | Evaluación de resultados piloto Ventas | Oscar / Manuel | 22/02/2027 | 26/02/2027 | 5 |

### FASE 1: AMPLIACIÓN A OTRAS ÁREAS (Mar 2027 — Abr 2027)

**Áreas expandidas en paralelo:**
- UN Institucional (cotizaciones, leads, forecast)
- Metusa (ventas, trade marketing)
- Atención al Cliente (tickets FSM, NPS)
- Innovación y Calidad (calidad, obsolescencia)
- Finanzas (proyecciones de ventas y compras)
- Servicio Técnico (integración FSM)

**Estructura por área:**
1. Catálogo de preguntas (5 días)
2. Validación y testing (12 días)
3. Deploy en producción (12 días)

Duración Fase 1: 01/03/2027 — 16/04/2027 (47 días)

### FASE 1.5: FUNCIONALIDADES TRANSVERSALES (Abr—May 2027)

- Motor de generación de documentos (PPT/Excel/diagramas): 26/04 — 07/05
- Módulo de investigación externa (competencia, noticias): 26/04 — 07/05
- Testing y validación: 10/05 — 21/05
- Deploy a todos: 24/05 — 04/06

### FASE 1.75: DOCUMENTACIÓN INSTITUCIONAL (May—Jul 2027)

- Indexación de políticas, procedimientos, manuales: 07/06 — 25/06
- Validación de acceso universal: 28/06 — 09/07
- Deploy a todos: 12/07 — 23/07

### FASE 2: RRHH Y LEGAL (Abr—Jul 2027)

**Requisitos especiales:**
- Validación Legal previa (27 abr — 21 may)
- Validación RRHH (27 abr — 21 may)
- Aprobación formal de Andrea Cárdenas y Renato Saldaña **antes de cualquier deploy**

**Datos sensibles:**
- RRHH: sueldos (solo propio empleado + RRHH), vacaciones (solo agregados para jefe), permisos
- Legal: contratos cerrados, alertas normativas

### FASE 3: ROLLOUT GENERAL (Jul—Dic 2027)

- Consolidación acceso general: 26/07 — 20/08
- Marketing y Producto: 26/07 — 20/08
- Capacitación transversal: 23/08 — 17/09
- Monitoreo y optimización: 20/09 — 15/10
- Ajustes finales: 18/10 — 12/11
- Revisión ROI (6 meses post-Fase 0): 15/11 — 10/12
- Sistema en operación normal: 13/12 — 31/12/2027

---

## 👥 EQUIPO Y ROLES

### Oscar Armando Núñez Vargas
- **Rol:** Especialista de Transformación Digital e IA
- **Reporta a:** Sergio González Vesga (Gerencia Atención al Cliente)
- **Responsabilidades:** Desarrollo principal con Claude, coordinación, stakeholder management
- **Dedicación:** ~70% (estimado)
- **Herramientas:** Claude, Claude Code, Python, openpyxl

### Héctor Antaurco Ayca
- **Rol:** Analista de Procesos y Data
- **Reporta a:** Andrea Cárdenas Silva (RRHH/Procesos)
- **Responsabilidades:** Validación de datos, catalogación de preguntas, documentación de procesos
- **Dedicación:** ~20% (estimado)
- **Nota:** NO es desarrollador ni recurso de TI ejecutivo

### Manuel Calderón Montoro
- **Rol:** Jefe de Tecnología e Información
- **Reporta a:** Juan Sanguineti Corzo (Admin/Finanzas/Ops)
- **Responsabilidades:** Aprobación de proyecto, acceso a infraestructura, supervisión, gobernanza
- **Decisiones clave:** Acceso SAP, SQL central, Azure, licencias Claude

### Andrea Cárdenas Silva
- **Rol:** Jefe de RRHH y Procesos
- **Responsabilidades:** Validación de RRHH, documentación institucional, matriz de acceso
- **Decisión crítica:** Aprobación formal de Fase 2 (datos de RRHH)

### Renato Saldaña Jaimes
- **Rol:** Jefe de Legal y Contratos
- **Responsabilidades:** Validación legal, cumplimiento GDPR/datos personales, riesgos legales
- **Decisión crítica:** Aprobación formal de Fase 2 (datos de Legal)

---

## ⚠️ SUPUESTOS Y RIESGOS

### SUPUESTOS DE DISPONIBILIDAD

| Supuesto | Valor | Justificación |
|---|---|---|
| Oscar dedicación | ~70% | Desarrollo + coordinación + reuniones |
| Héctor dedicación | ~20% | Validación en paralelo, no bloqueante |
| Acceso SAP C4C/FSM | 31/08/2026 | Requerido para desarrollo orquestador |
| SQL central disponible | 31/08/2026 | Ya existe en MT Industrial |
| Respuesta de Ventas (catálogo) | 5 días (31 ago — 04 sep) | Ventana cerrada, no negociable |

### SUPUESTOS DE TECNOLOGÍA

| Supuesto | Valor | Nota |
|---|---|---|
| Claude como acelerador | 3-5x más rápido que manual | Pruebas iniciales con intake platform exitosas |
| Modelo LLM | Claude Sonnet 5 o superior | Function calling maduro, 200K token window |
| Arquitectura | A definir (Orquestador único vs. Multiagente) | Análisis de tokens sugiere multiagente ~24% más barato |
| Hosting | Azure / infraestructura MT Industrial | TI responsable de infraestructura |
| Licencias Claude | Pendiente adquisición | Oscar + Manuel coordinan con Finanzas |

### RIESGOS PRINCIPALES

| Riesgo | Severidad | Mitigación |
|---|---|---|
| Oscar indisponible (enfermedad, cambio) | **ALTO** | Documentar código bien, establecer backup TI, conocimiento compartido con Héctor |
| RBAC más complejo de lo estimado | **MEDIO** | Incluir buffer en cronograma, validar con Legal desde inicio (Renato), iteración temprana |
| Alucinaciones LLM en datos sensibles (RRHH/Legal) | **ALTO** | Guardrails + validación humana, Fase 2 requiere 2 capas de revisión, testing exhaustivo |
| Acceso tardío a APIs SAP | **MEDIO** | Desarrollo paralelo con datos de prueba, fallback a SQL central solamente |
| Presunción en proyecciones (climate, market) | **MEDIO** | Documentar variables externas en UI, marcar como "supuesto", no como "dato" |
| Sobre-estimación de velocidad con Claude | **MEDIO** | Tomar Fase 0 como validación real, ajustar Fase 1+ si es necesario |
| Falta de adopción en áreas (Fase 1+) | **BAJO** | Capacitación transversal (Fase 3), diseño UI intuitivo, quick wins visibles |

---

## 📋 REQUERIMIENTOS FUNCIONALES

### RF-001 a RF-003: Autenticación (Fase 0)
- Autenticación vía Microsoft Entra ID (Azure AD)
- SSO + MFA
- Identificación automática de rol del usuario
- Sin login adicional (hereda credenciales MT Industrial)

### RF-010 a RF-015: Consulta Básica (Fase 0)
- Aceptar input en español (conversación natural)
- Validar permisos ANTES de consultar base de datos
- Ejecutar contra fuente REAL (nunca generar/inventar datos)
- Respuesta citada con fuente original
- Marcar si es dato vs. proyección
- Auditar todas las consultas (quién, cuándo, qué)

### RF-020 a RF-023: Proyecciones y Modelos (Fase 1)
- Distinguir dato existente vs. proyección
- Aviso explícito: "Esta es una PROYECCIÓN, no un dato oficial"
- Proyección de compras = usa como insumo proyección de ventas
- Proyección de personal = valida capacidad operativa

### RF-030 a RF-032: Investigación Externa (Fase 1.5)
- Buscar información fuera de MT Industrial (noticias, competencia)
- Distinguir "dato interno" de "información externa"
- Aviso de confiabilidad externa ("Esta información proviene de fuentes públicas, validar antes de tomar decisión")
- Marcar fecha de consulta externa

### RF-040 a RF-042: Generación de Documentos (Fase 1.5)
- Generar PPT con datos de conversación (formato profesional)
- Generar Excel con tablas (fórmulas funcionales)
- Generar diagramas (organizacionales, flujos)
- Incluir fecha, fuente, disclaimers

### RF-060 a RF-063: RRHH y Legal (Fase 2)
- **RRHH:**
  - Sueldo/bonos: solo propio empleado ve el suyo + RRHH ve todos
  - Vacaciones/permisos: solo jefe ve AGREGADOS (no individuales)
  - Capacitación/beneficios: acceso por rol
- **Legal:**
  - Contratos cerrados: acceso controlado
  - Alertas normativas: solo Legal + Ejecutiva
- **Seguridad:** RF-063 requiere aprobación formal de Andrea Cárdenas y Renato Saldaña ANTES de activarse

### RF-070 a RF-072: Auditoría y Monitoreo
- Auditoría completa: quién consultó, cuándo, qué preguntó, respuesta, costo en tokens
- Monitoreo de consumo tokens por usuario/mes
- Dashboard de uso por gerencia
- Alertas de consultas anómalas (ej: usuario no-RRHH intentó acceder a sueldos)

---

## 🛡️ REQUERIMIENTOS NO-FUNCIONALES

### RNF-001: Agregación de Datos (CRÍTICO)
- **Nunca** pasar tablas crudas a Claude
- Pre-agregar resultados SQL (suma, promedio, conteo, etc.)
- Esto reduce consumo de tokens + mejora precisión + protege datos sensibles

### RNF-002: Latencia Máxima
- Respuesta en < 10 segundos para 95% de consultas
- Definir valor concreto con Manuel/TI

### RNF-003: Disponibilidad
- Uptime >= 99% durante horario comercial
- Degradación elegante si SAP/SQL falla (usar cache, decir "datos pueden estar desactualizados")

### RNF-004: Configurabilidad
- Prompts y reglas de permisos actualizables sin nuevo despliegue
- Admin panel para cambiar guardrails (sin recompilar código)

### RNF-005: Resiliencia
- Si una fuente (SAP, SQL, SharePoint) falla: degradar sin exponer datos
- **NUNCA** inventar respuesta de respaldo
- Ejemplo: "Disculpe, no pude conectar con SAP C4C en este momento. Reintente en 5 minutos"

### RNF-006: Privacidad
- Datos RRHH/Legal nunca en logs accesibles a roles no autorizados
- Encrytar en tránsito y en reposo
- Cumplimiento GDPR/normativa local

### RNF-007: Escalabilidad
- Arquitectura multiagente evaluable como alternativa
- Estudios iniciales: ~24% ahorro OPEX con multiagente vs. orquestador único

---

## 🔐 MATRIZ DE ACCESO (RBAC)

### Por Fase y Datos

#### FASE 0 (Ventas)

| Rol | Ventas | Inventario | NPS | Cadena Suministro |
|---|---|---|---|---|
| Martin Castro (Ventas) | ✅ Completo | ✅ Lectura | ✅ Filtrado | ✅ Filtrado |
| UN Institucional | ✅ Lectura | ❌ No | ✅ Filtrado | ✅ Filtrado |
| Oscar | ✅ Completo | ✅ Completo | ✅ Completo | ✅ Completo |
| Manuel (TI) | ✅ Lectura | ✅ Lectura | ✅ Lectura | ✅ Lectura |

#### FASE 1 (Ampliación)

Se agrega acceso a Proyecciones (Ventas, Compras, Personal)
- **Finanzas:** ✅ Acceso completo a proyecciones
- **Operaciones:** ✅ Acceso lectura proyecciones
- Otros: ✅ Acceso filtrado (ver propios datos)

#### FASE 2 (RRHH/Legal) — REQUIERE APROBACIÓN FORMAL

**RRHH:**
- Andrea Cárdenas + jefes: ✅ Acceso completo
- Empleado: ✅ Solo su propio registro
- Otros: ❌ Sin acceso

**Legal:**
- Renato Saldaña: ✅ Acceso completo
- Ejecutiva: ✅ Lectura (contratos activos, alertas)
- Otros: ❌ Sin acceso

#### FASE 3 (Rollout General)

Todas las gerencias con acceso "self-service" limitado a su data + información transversal (documentación institucional, noticias, recursos públicos)

---

## 💡 CASOS DE USO

### CU-01: Consulta Directa de Ventas (Fase 0)

**Actor:** Martin Castro (Vendedor o jefe de Ventas)

**Flujo:**
1. Usuario: "¿Cuál fue el volumen de ventas en agosto 2026?"
2. Sistema autentica (Entra ID)
3. RBAC valida: Martin = Vendedor, acceso a Ventas = ✅
4. Oracle consulta SQL central (suma volumen mes de ago 2026)
5. Claude formula respuesta: "El volumen en agosto fue $X, un aumento de Y% vs. julio"
6. Auditoría registra: Martin consultó ventas agosto el 15/12/2026 10:34 AM

---

### CU-02: Proyección de Ventas (Fase 1)

**Actor:** Finanzas (Kevin Gomez)

**Flujo:**
1. Usuario: "¿Cuál es la proyección de ventas para Q1 2027 considerando la estacionalidad?"
2. Claude accede a:
   - Histórico de ventas (SQL central)
   - Variables externas (noticias, competencia, económicas)
   - Modelos de estacionalidad (en documentación)
3. Claude formula: "Proyección Q1 2027: $X (rango $Y a $Z). Basado en: estacionalidad histórica, tendencia 2026, factor competencia"
4. **MARCA EXPLÍCITA:** "Esta es una PROYECCIÓN. Variables externas pueden cambiar"

---

### CU-03: Intento de Acceso No-Autorizado (Fase 2)

**Actor:** Vendedor (sin acceso a RRHH)

**Flujo:**
1. Usuario: "¿Cuál es el sueldo de Andrea Cárdenas?"
2. Sistema autentica
3. RBAC valida: Vendedor + consulta RRHH = ❌
4. Claude responde: "No tengo acceso a esa información. Si necesitas datos de personal, contacta con RRHH"
5. Auditoría registra: Vendedor (ID X) intentó acceso no-autorizado a RRHH el 15/12/2026 10:45 AM

---

### CU-04: Generación de PPT desde Conversación (Fase 1.5)

**Actor:** Marketing (Jessica Alva)

**Flujo:**
1. Usuario: "Crea una presentación con los KPIs de ventas Q3 2026"
2. Claude accede a:
   - KPIs de SQL central
   - Benchmarks de competencia (investigación externa)
   - Branding MT Industrial (SharePoint)
3. Claude genera PPT:
   - Portada con logo
   - Slide 1: KPIs principales
   - Slide 2: Vs. competencia
   - Slide 3: Recomendaciones
   - Pie de página: Fecha, fuente, aviso "Datos a 15/12/2026"
4. Usuario descarga PPT, edita si necesario

---

## 🔌 INTEGRACIÓN DE DATOS

### Fuentes de Datos Requeridas

| Fuente | Tipo | Acceso | Responsable | Estado |
|---|---|---|---|---|
| **SQL Central** | Base de datos relacional | API / SQL directo | TI | ✅ Existe |
| **SAP C4C** | CRM (clientes, oportunidades) | API REST | TI | ⏳ Acceso 31/08/2026 |
| **SAP FSM** | Service Management (tickets) | API REST | TI | ⏳ Acceso 31/08/2026 |
| **Microsoft Entra ID** | Identidades + roles | Azure AD API | TI | ✅ Existe |
| **SharePoint** | Documentos compartidos | Microsoft Graph API | TI | ✅ Existe |
| **Sistema RRHH** | Nómina, vacaciones, permisos | API propietaria | Andrea Cárdenas | ✅ Existe (Fase 2) |
| **Sistema Legal** | Contratos, documentos legales | Manual o API | Renato Saldaña | ✅ Existe (Fase 2) |

### Flujo de Integración

```
Usuario pregunta
    ↓
Gateway identifica dominio (Ventas, Finanzas, etc.)
    ↓
Orchestrator selecciona fuentes necesarias
    ↓
Para cada fuente:
  • Conectar via API/SQL
  • Validar permisos del usuario
  • Traer datos
  • Pre-agregar resultados
  • Cachear si es posible
    ↓
Combinar resultados
    ↓
Pasar a Claude (contexto + pre-agregados)
    ↓
Claude formula respuesta
    ↓
Auditoría registra (query, user, cost, timestamp)
    ↓
Respuesta + cita de fuentes
```

---

## 🎯 HITOS CRÍTICOS

### Hito 1: Aprobación de Alcance (Fase 0)
- **Fecha:** 28 de agosto 2026
- **Responsable:** Manuel Calderón + Oscar
- **Deliverable:** Email confirma alcance: solo Ventas, sin RRHH/Legal en Fase 0
- **Decisión:** Go/No-go proyecto

### Hito 2: Acceso SAP C4C/FSM Obtenido
- **Fecha:** 31 de agosto 2026
- **Responsable:** Manuel Calderón (TI)
- **Criterio de éxito:** API funcionando, credenciales en ambiente, test conexión OK
- **Bloqueo:** Sin esto, desarrollo no avanza

### Hito 3: Catálogo de Preguntas Ventas
- **Fecha:** 4 de septiembre 2026
- **Responsable:** Oscar + Martin Castro (Ventas)
- **Deliverable:** Lista de 10-15 preguntas reales que Ventas hace hoy manualmente
- **Criterio:** Preguntas concretas, no genéricas ("¿cuál fue el forecast del mes X?" not "¿qué datos tienen?")

### Hito 4: Orquestador + Integración SQL FUNCIONAL
- **Fecha:** 25 de septiembre 2026
- **Responsable:** Oscar
- **Criterio:** Prueba end-to-end: pregunta → respuesta en < 5 seg, 0 alucinaciones

### Hito 5: Piloto en Producción
- **Fecha:** 19 de octubre 2026
- **Responsable:** Oscar + Ventas + TI
- **Criterio:** 3 usuarios reales usando diariamente, mínimo 50 consultas/semana, 0 datos expuestos indebidamente

### Hito 6: Evaluación Piloto (Go/No-go Fase 1)
- **Fecha:** 26 de febrero 2027
- **Responsable:** Oscar + Manuel
- **Criterio:**
  - ✅ Consumo real < presupuesto estimado
  - ✅ Adopción en Ventas >= 60%
  - ✅ 0 brechas de seguridad
  - ✅ Feedback positivo en capacitación
- **Decisión:** Proceder a Fase 1 (expansión)

### Hito 7: Validación Legal/RRHH (Fase 2)
- **Fecha:** 21 de mayo 2027
- **Responsable:** Renato Saldaña + Andrea Cárdenas
- **Criterio:** Aprobación formal (email firmado) de matriz de acceso Fase 2
- **Bloqueo:** Sin esto, NO deploy de RRHH/Legal

### Hito 8: Rollout General Completado
- **Fecha:** 31 de diciembre 2027
- **Responsable:** Oscar + Ejecutiva
- **Criterio:**
  - ✅ Todas las gerencias con acceso
  - ✅ ROI >= payback especificado
  - ✅ Transición a operación normal (sin "pilot mode")

---

## ❓ DECISIONES PENDIENTES

### Decisión 1: Nombre del Sistema
- **Opciones:** "EcosistemaIA" (Oscar) vs. "SOLE AI" (Manuel)
- **Responsable:** Akinori Ando
- **Plazo:** Antes del 28 de agosto
- **Impacto:** Branding, comunicación interna, nombre de portal

### Decisión 2: Arquitectura Técnica
- **Opciones:**
  - A) Orquestador único (más simple, menos escalable)
  - B) Multiagente especializado (más complejo, 24% ahorro OPEX)
- **Responsable:** Oscar + Manuel
- **Plazo:** Antes del 31 de agosto
- **Criterio:** Estudio tokens Fase 0 + benchmarks de velocidad

### Decisión 3: Hosting / Cloud
- **Opciones:**
  - A) Azure (Microsoft, integración nativa con Entra ID)
  - B) AWS (cost)
  - C) On-premises (seguridad)
- **Responsable:** Manuel Calderón + TI
- **Plazo:** Antes del 31 de agosto
- **Impacto:** Costo, seguridad, compliance

### Decisión 4: Presupuesto Licencias Claude
- **Información:** Precios agosto 2026: Claude Sonnet 5 = $2/$10 MTok entrada/salida
- **Estimado Fase 0:** $150-350/mes
- **Estimado rollout completo:** $650-900/mes
- **Responsable:** Manuel + Kevin Gomez (Finanzas)
- **Plazo:** Antes del 28 de agosto
- **Criterio:** Incluir en CAPEX proyecto

### Decisión 5: Backup de Oscar
- **Problema:** Alto riesgo si Oscar se enferma/renuncia
- **Opciones:**
  - A) Designar junior TI en paralelo (documentar código)
  - B) Contrato con consultor externo "on-call"
  - C) Aceptar riesgo (mitigación post-pilot)
- **Responsable:** Manuel + Oscar
- **Plazo:** Antes del 30 de septiembre (después Fase 0 aprobada)

---

## 📞 CONTACTOS CLAVE

| Persona | Rol | Email | Teléfono | Notas |
|---|---|---|---|---|
| Oscar Armando Núñez Vargas | Especialista IA | oscar.nunez@mtindustrial.com | +51-XXX-XXXX | Desarrollador principal |
| Manuel Calderón Montoro | Jefe TI | manuel.calderon@mtindustrial.com | +51-XXX-XXXX | Aprobador, acceso infraestructura |
| Sergio González Vesga | Jefe Atención al Cliente | sergio.gonzalez@mtindustrial.com | +51-XXX-XXXX | Oscar reporta aquí |
| Héctor Antaurco Ayca | Analista Procesos/Data | hector.antaurco@mtindustrial.com | +51-XXX-XXXX | Validación datos |
| Andrea Cárdenas Silva | Jefe RRHH | andrea.cardenas@mtindustrial.com | +51-XXX-XXXX | Aprobador Fase 2 (RRHH) |
| Renato Saldaña Jaimes | Jefe Legal | renato.saldana@mtindustrial.com | +51-XXX-XXXX | Aprobador Fase 2 (Legal) |
| Martin Castro Bravo | Jefe Ventas | martin.castro@mtindustrial.com | +51-XXX-XXXX | Piloto Fase 0 |
| Kevin Gomez | Jefe Finanzas | kevin.gomez@mtindustrial.com | +51-XXX-XXXX | CAPEX, presupuesto |
| Akinori Ando | Vicepresidente | akinori.ando@mtindustrial.com | +51-XXX-XXXX | Decisiones estratégicas |
| Sandro Sattler Finazzi | Presidente | sandro.sattler@mtindustrial.com | +51-XXX-XXXX | Sponsor ejecutivo |

---

## 📊 INDICADORES Y MÉTRICAS (Fase 3 en adelante)

### Adoptación
- % de usuarios activos por gerencia
- Consultas por usuario / mes
- Utilización en horario comercial vs. fuera de horario

### Eficiencia
- Tiempo ahorrado en reportes manuales (horas/mes)
- Reducción de "preguntas no contestadas" (de 30% a < 5%)
- Velocidad promedio respuesta (target < 8 seg)

### Financiero
- Consumo tokens real vs. presupuesto
- Payback (inversión inicial / ahorro mensual)
- ROI a 6 y 12 meses

### Calidad
- Tasa de alucinaciones (target 0 en datos sensibles)
- % de respuestas "útiles" (survey)
- Incidentes de seguridad (target 0)

### Satisfacción
- NPS (Net Promoter Score) por gerencia
- Feedback en capacitación
- Tickets de soporte/bugs

---

## 🚀 PRÓXIMOS PASOS INMEDIATOS

1. **Hoy (17 ago 2026):** Oscar presenta archivo Excel `EcosistemaIA-Plan-de-Trabajo.xlsx` a Manuel Calderón
2. **Antes del 28 ago:** Reunion con Manuel para aprobar alcance, presupuesto, nombre, arquitectura
3. **Antes del 31 ago:** Acceso SAP C4C/FSM activo
4. **Antes del 04 sep:** Catálogo de preguntas Ventas definido con Martin Castro
5. **14 sep en adelante:** Oscar inicia desarrollo del orquestador con Claude

---

**Documento maestro completo. Última actualización: 17 de agosto de 2026**

