# Tablas Críticas para SOLE AI Fase 0

**Filtrado:** Solo tablas con `SD_` (ventas SAP) + `FORECAST` (pronóstico)  
**Última actualización:** 20 de agosto de 2026

---

## 📊 TABLAS EN AZURE SQL (soledb-puntoventa)

### Tablas SD_* (Ventas SAP)

| # | Tabla | Propósito | Para Herramienta |
|---|-------|----------|------------------|
| 1 | `SD_VENTAS` | 🔴 **CRÍTICA** - Registro principal de ventas | T1, T3, T5 |
| 2 | `SD_ENTREGAS` | Despachos/entregas de ventas | T3, T6 |
| 3 | `SD_GRUPO_MATERIAL` | Grupos de productos (nivel principal) | Catálogo |
| 4 | `SD_GRUPO_MATERIAL_1` | Subgrupo nivel 1 | Catálogo |
| 5 | `SD_GRUPO_MATERIAL_2` | Subgrupo nivel 2 | Catálogo |
| 6 | `SD_GRUPO_MATERIAL_3` | Subgrupo nivel 3 | Catálogo |
| 7 | `SD_TIENDAS` | Puntos de venta/sucursales | Dimensión |
| 8 | `SD_VENTAS_INTERLOCUTOR` | Contactos/interlocutores en ventas | T4 |
| 9 | `SAP_SD_ZTZONTRAN_ZONA_TRANSPORTE_POSTAL` | Zonas de transporte postal | Dimensión |

### Tabla FORECAST

| # | Tabla | Propósito | Para Herramienta |
|---|-------|----------|------------------|
| 10 | `WEB_FORECAST_VENTAS_REPORTE_ACTIVIDAD` | 🟢 **PRE-AGREGADA** - Ventas + Forecast consolidado | T1, T3 |

---

## 📊 TABLAS EN BD LOCAL (SIG) — A VERIFICAR

**⚠️ No pude conectar desde aquí, pero tú puedes verificar en SQL Server Management Studio:**

### Buscar Tablas FORECAST en SIG

Ejecuta esta query en SQL Server Management Studio:

```sql
-- En BD: SIG
SELECT TABLE_NAME
FROM INFORMATION_SCHEMA.TABLES
WHERE TABLE_TYPE = 'BASE TABLE'
    AND TABLE_NAME LIKE '%FORECAST%'
ORDER BY TABLE_NAME;
```

**Tablas esperadas (basado en captura anterior):**
- `FORECAST_VENTAS_REGISTRO_CARGA_20231003`
- `TBL_FORECAST_CALIDAD`
- `TBL_FORECAST_CALIDAD_ESPORÁDICOS`
- `TBL_FORECAST_CALIDAD_KARENZ508`
- `TBL_FORECAST_SOLICITANTE_USUARIO`
- `WEB_FORECAST_CA`
- `WEB_FORECAST_CANAL_SOLICITANTE`
- `WEB_FORECAST_CARGA`
- `WEB_FORECAST_COSTOS`
- `WEB_FORECAST_MATERIALES`
- `WEB_FORECAST_PRECIOS`
- `WEB_FORECAST_PRESUPUESTO*` (múltiples versiones)
- `WEB_FORECAST_VENTAS_HISTORICO`
- `WEB_FORECAST_VENTAS_REGISTRO`
- Y más...

**Las más importantes probablemente:**
- `WEB_FORECAST_PRESUPUESTO*` — Metas/presupuesto
- `WEB_FORECAST_VENTAS_HISTORICO` — Histórico de ventas
- `WEB_FORECAST_VENTAS_REGISTRO` — Registro de pronósticos

---

## 🎯 RESUMEN FINAL PARA FASE 0

### Tablas Confirmadas en Azure:

✅ **SD_VENTAS** — Transacciones de venta (121 columnas)  
✅ **SD_ENTREGAS** — Despachos (75 columnas)  
✅ **SD_GRUPO_MATERIAL** — Catálogo de grupos  
✅ **SD_TIENDAS** — Puntos de venta  
✅ **SD_VENTAS_INTERLOCUTOR** — Contactos  
✅ **WEB_FORECAST_VENTAS_REPORTE_ACTIVIDAD** — Consolidado pre-agregado (91 columnas)  

### Tablas Pendientes en SIG:

⏳ **Tablas FORECAST** (presupuesto/metas)  
⏳ **Tablas Inventario** (si existen)  
⏳ **Tablas NPS** (si existen)

---

## 📌 PRÓXIMO PASO

**Oscar:** Ejecuta esta query en tu BD local SIG para confirmar tablas FORECAST:

```sql
USE SIG;  -- Cambiar si el nombre es diferente

SELECT TABLE_NAME
FROM INFORMATION_SCHEMA.TABLES
WHERE TABLE_TYPE = 'BASE TABLE'
    AND TABLE_NAME LIKE '%FORECAST%'
ORDER BY TABLE_NAME;
```

Luego comparte los resultados para actualizar el análisis.

---

**Total tablas a analizar en Fase 0:**
- ✅ 6 tablas en Azure SQL (confirmadas)
- ⏳ ~5-10 tablas FORECAST en SIG (por confirmar)

