# SQL Data Dictionary — SOLE AI Fase 0

**Última actualización:** 20 de agosto de 2026  
**Base de Datos:** Azure SQL Server (`soledb-puntoventa`)  
**Usuario Lectura:** `soledbserveradmin` (read-only)

---

## 📋 TABLA DE CONTENIDOS

1. [Mapeo Tablas → Herramientas](#mapeo-tablas--herramientas)
2. [Diccionario Detallado de Tablas](#diccionario-detallado-de-tablas)
3. [Queries de Ejemplo](#queries-de-ejemplo)
4. [Relaciones entre Tablas](#relaciones-entre-tablas)
5. [Notas Importantes](#notas-importantes)

---

## 🎯 MAPEO TABLAS → HERRAMIENTAS

| Herramienta | Tablas Principales | Tablas Soporte | Descripción |
|-------------|-------------------|----------------|-------------|
| **T1: get_sales_summary** | `SD_VENTAS` | `TB_MARA`, `TBL_CLIENTE` | Total ventas, órdenes, clientes por período/región |
| **T2: get_sales_targets** | ❓ TBD* | TBD | Meta vs realizado (requiere tabla de metas) |
| **T3: get_sales_forecast** | `WEB_FORECAST_VENTAS_REPORTE_ACTIVIDAD` | `SD_VENTAS` | Forecast + histórico |
| **T4: get_customer_insights** | `TBL_CLIENTE` | `SD_VENTAS`, `WEB_FORECAST_VENTAS_REPORTE_ACTIVIDAD` | Cliente, histórico, satisfacción |
| **T5: get_sales_performance** | `SD_VENTAS` | `TB_EMPLEADO` | Ranking vendedores, tendencias |
| **T6: get_inventory_by_sales** | ❓ TBD* | `SD_ENTREGAS` | Stock (requiere tabla de inventario) |

**\* TBD:** Tablas aún no identificadas. Requeridas después de validación con equipo de Ventas.

---

## 📚 DICCIONARIO DETALLADO DE TABLAS

### 1️⃣ **SD_VENTAS** — Registro Principal de Ventas

**Descripción:**  
Tabla central de transacciones de venta de SAP (módulo SD). Contiene TODA la información de cada línea de venta: documento, cliente, producto, cantidad, precio, vendedor, fecha, etc.

**Ubicación:** Azure SQL (`soledb-puntoventa`)  
**Registros:** ~Millones (requiere análisis post-conexión)  
**Actualización:** Diaria (sincronización SAP)  
**Acceso:** ✅ Lectura permitida

**Columnas Clave:**

| Columna | Tipo | Descripción | Ejemplo |
|---------|------|-------------|---------|
| `VC_documento_pago_numero` | VARCHAR | PK: Número de documento de venta | "100000001" |
| `VC_documento_pago_posicion` | VARCHAR | PK: Posición dentro del documento | "00001" |
| `DT_documento_pago_fecha` | SMALLDATETIME | Fecha de venta | 2026-08-15 |
| `VC_vendedor_codigo` | VARCHAR | Código del vendedor | "VEN001" |
| `VC_vendedor_nombre` | VARCHAR | Nombre del vendedor | "Juan García" |
| `VC_solicitante_codigo` | VARCHAR | FK: Código del cliente/solicitante | "CLI12345" |
| `VC_solicitante_razon_social` | VARCHAR | Nombre del cliente | "Empresa ABC S.A." |
| `VC_material_codigo` | VARCHAR | Código del producto/material | "MAT-001-XYZ" |
| `VC_material_descripcion` | VARCHAR | Descripción del producto | "Tornillo acero 1/4 x 2" |
| `DE_cantidad` | DECIMAL | Cantidad vendida | 100.00 |
| `VC_unidad_venta` | VARCHAR | Unidad (PZA, KG, LT, etc.) | "PZA" |
| `DE_bruto` | DECIMAL | Monto bruto antes descuento | 5000.00 |
| `DE_descuento` | DECIMAL | Descuento aplicado | 500.00 |
| `DE_neto` | DECIMAL | Monto neto (bruto - desc) | 4500.00 |
| `DE_igv` | DECIMAL | IGV (impuesto) | 810.00 |
| `VC_moneda` | VARCHAR | Moneda (PEN, USD, etc.) | "PEN" |
| `IN_mes` | INT | Mes (1-12) | 8 |
| `IN_anio` | INT | Año | 2026 |
| `VC_trimestre` | VARCHAR | Trimestre (Q1, Q2, etc.) | "Q3" |
| `VC_semestre` | VARCHAR | Semestre (H1, H2) | "H2" |
| `VC_zona_ventas` | VARCHAR | Zona geográfica de venta | "LIMA_NORTE" |
| `VC_grupo_material` | VARCHAR | Grupo de producto | "FERRETERIA" |
| `VC_grupo_material_1` | VARCHAR | Subgrupo nivel 1 | "TORNILLOS" |
| `DE_costo_estandar` | DECIMAL | Costo estándar | 2500.00 |
| `DE_costo_real` | DECIMAL | Costo real | 2400.00 |

**Relaciones:**
- FK: `VC_solicitante_codigo` → `TBL_CLIENTE.VC_Código_Ciente`
- FK: `VC_material_codigo` → `TB_MARA.VC_codigo_material`
- FK: `VC_vendedor_codigo` → `TB_EMPLEADO.VC_Codigo`

**Índices Importantes:**
- PK: (`VC_documento_pago_numero`, `VC_documento_pago_posicion`)
- IX: (`DT_documento_pago_fecha`, `VC_vendedor_codigo`, `VC_solicitante_codigo`)

---

### 2️⃣ **WEB_FORECAST_VENTAS_REPORTE_ACTIVIDAD** — Forecast y Histórico de Ventas

**Descripción:**  
Vista/tabla que consolida datos de ventas con información de forecast, entregas, despachados, etc. Es la tabla "lista para reportes" que SE RECOMIENDA usar para análisis de ventas.

**Ubicación:** Azure SQL (`soledb-puntoventa`)  
**Registros:** ~Millones  
**Actualización:** Diaria  
**Acceso:** ✅ Lectura permitida  
**Ventaja:** Pre-agregada, muchas columnas calculadas

**Columnas Clave (Selección):**

| Columna | Tipo | Descripción |
|---------|------|-------------|
| `Documento` | VARCHAR | Número de documento |
| `Fecha` | VARCHAR | Fecha de venta (formato texto) |
| `FechaDate` | DATE | Fecha de venta (formato date) |
| `MesNumero` | INT | Mes (1-12) |
| `MesNombre` | VARCHAR | Nombre mes ("Agosto", etc.) |
| `Anio` | INT | Año |
| `VendedorCodigo` | VARCHAR | Código vendedor |
| `VendedorNombre` | VARCHAR | Nombre vendedor |
| `SolicitanteNombre` | VARCHAR | Nombre cliente |
| `MaterialCodigo` | VARCHAR | Código producto |
| `MaterialNombre` | VARCHAR | Nombre producto |
| `Cantidad` | DECIMAL | Cantidad |
| `ImporteSoles` | DECIMAL | Importe en soles (ya con IGV) |
| `ImporteBrutoSoles` | DECIMAL | Bruto |
| `DescuentoSoles` | DECIMAL | Descuento |
| `CostoEstandarSoles` | DECIMAL | Costo estándar |
| `CostoRealSoles` | DECIMAL | Costo real |
| `UtilidadSoles` | DECIMAL | Utilidad (Importe - Costo Real) |
| `MargenRealPorcentaje` | DECIMAL | Margen % |
| `REGION` | VARCHAR | Región de venta |
| `Canal` | VARCHAR | Canal de venta |
| `GrupoMaterial` | VARCHAR | Grupo de producto |
| `DespachoEstado` | VARCHAR | Estado despacho (PENDIENTE, DESPACHADO, etc.) |
| `DespachoFecha` | DATETIME | Fecha despacho real |

**¿Cuándo usarla?**
- ✅ Para reportes ejecutivos (totales, promedios)
- ✅ Para análisis de ventas por período/región/vendedor
- ✅ Para margen y rentabilidad
- ❌ Para transacciones individuales (mejor usar `SD_VENTAS`)

---

### 3️⃣ **TBL_CLIENTE** — Catálogo de Clientes

**Descripción:**  
Registro maestro de clientes. Información básica de cada cliente: código, nombre, RUC/DNI.

**Columnas:**

| Columna | Tipo | Descripción |
|---------|------|-------------|
| `VC_Código_Ciente` | VARCHAR | PK: Código único del cliente |
| `VC_Nombre` | VARCHAR | Razón social del cliente |
| `VC_DNI` | VARCHAR | DNI (si es persona natural) |
| `VC_RUC` | VARCHAR | RUC (si es empresa) |

**Nota:** Tabla pequeña y simple. Información básica. Para datos adicionales (contacto, dirección, etc.), revisar `SD_VENTAS` que contiene campos `Solicitante*`.

---

### 4️⃣ **TB_MARA** — Catálogo de Productos (Material Master de SAP)

**Descripción:**  
Registro maestro de materiales/productos de SAP. Definiciones de productos, atributos técnicos, pesos, volúmenes, etc.

**Columnas Clave:**

| Columna | Tipo | Descripción |
|---------|------|-------------|
| `VC_codigo_material` | VARCHAR | PK: Código único del material |
| `VC_tipo_material` | VARCHAR | Tipo (FERT, HALB, ROH, etc.) |
| `VC_grupo_articulo` | VARCHAR | Grupo de artículo |
| `VC_unidad_base` | VARCHAR | Unidad base (PZA, KG, etc.) |
| `DE_peso_bruto` | DECIMAL | Peso bruto |
| `DE_peso_neto` | DECIMAL | Peso neto |
| `VC_unidad_peso` | VARCHAR | Unidad peso (KG, GR, etc.) |
| `DE_volumen` | DECIMAL | Volumen |
| `VC_ean_upc` | VARCHAR | Código de barras |

---

### 5️⃣ **TB_MAKT** — Descripción de Materiales

**Descripción:**  
Descripciones de materiales en diferentes idiomas/variantes.

**Columnas:**

| Columna | Tipo | Descripción |
|---------|------|-------------|
| `VC_codigo_material` | VARCHAR | FK: Código material (de TB_MARA) |
| `VC_denominacion_material_1` | VARCHAR | Descripción 1 |
| `VC_denominacion_material_2` | VARCHAR | Descripción 2 |

---

### 6️⃣ **TB_PRECIO** — Catálogo de Precios

**Descripción:**  
Precios por cliente y producto. Contiene precios netos, con IGV, precios lista, y control de promociones.

**Columnas Clave:**

| Columna | Tipo | Descripción |
|---------|------|-------------|
| `VC_codigo_cliente` | VARCHAR | FK: Cliente |
| `VC_codigo_material` | VARCHAR | FK: Material/Producto |
| `DE_precio_neto` | DECIMAL | Precio sin IGV |
| `DE_precio_igv` | DECIMAL | Precio con IGV |
| `DE_precio_total` | DECIMAL | Precio total |
| `DE_precio_lista` | DECIMAL | Precio de lista |
| `CH_indicador_promocion` | CHAR | ¿Está en promoción? (S/N) |
| `DT_fecha_inicio_promocion` | DATE | Inicio promoción |
| `DT_fecha_fin_promocion` | DATE | Fin promoción |
| `DT_fecha` | DATE | Fecha vigencia precio |

---

### 7️⃣ **TB_EMPLEADO** — Registro de Empleados (Vendedores)

**Descripción:**  
Catálogo de empleados/vendedores. Información laboral básica.

**Columnas Clave:**

| Columna | Tipo | Descripción |
|---------|------|-------------|
| `VC_Codigo` | VARCHAR | PK: Código del empleado |
| `VC_Nombre` | VARCHAR | Nombre completo |
| `VC_CodigoRol` | VARCHAR | Código del rol |
| `VC_CodigoPuesto` | VARCHAR | Código del puesto |
| `VC_CodigoArea` | VARCHAR | Código del área |
| `VC_Usuario` | VARCHAR | Usuario corporativo |
| `VC_Correo` | VARCHAR | Email corporativo |
| `VC_EsAprobador` | VARCHAR | ¿Es aprobador? (S/N) |
| `VC_Estado` | VARCHAR | Estado (ACTIVO, INACTIVO) |
| `DT_FechaIngreso` | DATETIME | Fecha de ingreso |

---

### 8️⃣ **SD_ENTREGAS** — Registro de Entregas/Despachos

**Descripción:**  
Información de entregas de pedidos. Complementa `SD_VENTAS` con datos logísticos.

**Columnas Clave:**

| Columna | Tipo | Descripción |
|---------|------|-------------|
| `VC_entrega_numero` | VARCHAR | PK: Número de entrega |
| `VC_entrega_posicion` | VARCHAR | PK: Posición en entrega |
| `VC_entrega_fecha` | VARCHAR | Fecha de entrega |
| `VC_material_codigo` | VARCHAR | Código del material |
| `DE_cantidad` | DECIMAL | Cantidad entregada |
| `VC_estado` | VARCHAR | Estado (PENDIENTE, ENTREGADO, etc.) |
| `VC_solicitante_codigo` | VARCHAR | Cliente |
| `VC_grupo_material` | VARCHAR | Grupo de material |

---

## 💾 QUERIES DE EJEMPLO

### Query 1: Total de Ventas por Mes (para T1: get_sales_summary)

```sql
-- Total ventas por mes y año
SELECT 
    IN_anio as Año,
    IN_mes as Mes,
    VC_mes as NombreMes,
    COUNT(DISTINCT VC_documento_pago_numero) as NumOrdenes,
    COUNT(DISTINCT VC_solicitante_codigo) as NumClientes,
    SUM(DE_bruto) as VentaBruto,
    SUM(DE_neto) as VentaNeto,
    SUM(DE_igv) as IGV,
    ROUND(AVG(DE_neto), 2) as PromedioOrden
FROM SD_VENTAS
WHERE IN_anio = 2026
    AND IN_mes = 8  -- Agosto
GROUP BY IN_anio, IN_mes, VC_mes
ORDER BY IN_anio DESC, IN_mes DESC;
```

---

### Query 2: Ventas por Vendedor (para T5: get_sales_performance)

```sql
-- Top vendedores por total ventas
SELECT 
    VC_vendedor_codigo,
    VC_vendedor_nombre,
    IN_mes,
    IN_anio,
    COUNT(*) as NumTransacciones,
    COUNT(DISTINCT VC_solicitante_codigo) as ClientesUnicos,
    SUM(DE_neto) as TotalVentas,
    SUM(DE_igv) as TotalIGV,
    SUM(DE_costo_real) as CostoReal,
    SUM(DE_neto) - SUM(DE_costo_real) as Utilidad,
    ROUND(100.0 * (SUM(DE_neto) - SUM(DE_costo_real)) / SUM(DE_neto), 2) as MargenPorcentaje
FROM SD_VENTAS
WHERE IN_anio = 2026
    AND IN_mes = 8
GROUP BY VC_vendedor_codigo, VC_vendedor_nombre, IN_mes, IN_anio
ORDER BY TotalVentas DESC;
```

---

### Query 3: Análisis de Cliente (para T4: get_customer_insights)

```sql
-- Histórico de cliente
SELECT 
    c.VC_Código_Ciente,
    c.VC_Nombre,
    c.VC_RUC,
    COUNT(DISTINCT sv.VC_documento_pago_numero) as NumTransacciones,
    MAX(sv.DT_documento_pago_fecha) as UltimaCompra,
    SUM(sv.DE_neto) as TotalGastado,
    ROUND(AVG(sv.DE_neto), 2) as PromedioPorTransaccion,
    DATEDIFF(DAY, MAX(sv.DT_documento_pago_fecha), GETDATE()) as DiasDesdeUltimaCompra
FROM TBL_CLIENTE c
LEFT JOIN SD_VENTAS sv ON c.VC_Código_Ciente = sv.VC_solicitante_codigo
WHERE sv.IN_anio >= 2025  -- Últimos datos
GROUP BY c.VC_Código_Ciente, c.VC_Nombre, c.VC_RUC
ORDER BY TotalGastado DESC;
```

---

### Query 4: Forecast vs Histórico (para T3: get_sales_forecast)

```sql
-- Ventas reales vs forecast por período
SELECT 
    Anio,
    MesNumero,
    MesNombre,
    COUNT(*) as Registros,
    SUM(ImporteSoles) as VentasReales,
    SUM(Cantidad) as QuantityVendida,
    AVG(MargenRealPorcentaje) as MargenPromedio
FROM WEB_FORECAST_VENTAS_REPORTE_ACTIVIDAD
WHERE Anio = 2026
    AND MesNumero IN (6, 7, 8)  -- Jun, Jul, Ago
GROUP BY Anio, MesNumero, MesNombre
ORDER BY Anio, MesNumero;
```

---

### Query 5: Ventas por Región (para T1: get_sales_summary)

```sql
-- Desglose por región
SELECT 
    VC_zona_ventas as Región,
    IN_mes,
    IN_anio,
    COUNT(DISTINCT VC_documento_pago_numero) as Ordenes,
    SUM(DE_neto) as VentaNeto,
    SUM(DE_igv) as IGV,
    ROUND(SUM(DE_neto) / COUNT(DISTINCT VC_documento_pago_numero), 2) as PromedioPorOrden
FROM SD_VENTAS
WHERE IN_anio = 2026
GROUP BY VC_zona_ventas, IN_mes, IN_anio
ORDER BY IN_mes DESC, VentaNeto DESC;
```

---

## 🔗 RELACIONES ENTRE TABLAS

```
TBL_CLIENTE
    ↓ (VC_Código_Ciente = VC_solicitante_codigo)
SD_VENTAS
    ↓ (VC_material_codigo)
TB_MARA → TB_MAKT (catálogo de materiales)
    ↓
TB_PRECIO (precios por cliente-material)

TB_EMPLEADO
    ↓ (VC_Codigo = VC_vendedor_codigo)
SD_VENTAS

WEB_FORECAST_VENTAS_REPORTE_ACTIVIDAD
    ↓ (consolidación de SD_VENTAS + SD_ENTREGAS + datos calculados)
```

---

## ⚠️ NOTAS IMPORTANTES

### 1. **Columnas de Fecha**
- `SD_VENTAS` tiene:
  - `DT_documento_pago_fecha` (SMALLDATETIME) ← **USAR ESTA**
  - `VC_fecha_creacion` (VARCHAR) ← Texto, no recomendado
- `WEB_FORECAST_VENTAS_REPORTE_ACTIVIDAD` tiene:
  - `Fecha` (VARCHAR) ← Texto
  - `FechaDate` (DATE) ← **USAR ESTA**

### 2. **Moneda**
- Todas las transacciones pueden estar en PEN (soles) o USD
- Verificar `VC_moneda` en `SD_VENTAS`
- Hay campo `DE_tipo_cambio` para conversiones

### 3. **Presupuesto/Metas**
- ⚠️ **No encontrada tabla de metas/presupuesto**
- Se asume que están en BD local `SIG` (no explorada aún)
- Requerido para herramienta T2: `get_sales_targets`

### 4. **Inventario/Stock**
- ⚠️ **No encontrada tabla clara de inventario**
- `SD_ENTREGAS` tiene información de entregas, no stock actual
- Posible: tabla de almacén/warehouse en SAP (no explorada)
- Requerido para herramienta T6: `get_inventory_by_sales`

### 5. **Satisfacción/NPS**
- ⚠️ **No encontrada tabla de encuestas**
- Posible: `TBL_NPS` (visto en lista de tablas pero no explorada)
- Requerido para `get_customer_insights` completo

### 6. **Rendimiento de Queries**
- `SD_VENTAS` tiene **121 columnas** y potencialmente **millones de filas**
- **SIEMPRE usar FILTER por fecha** (mes/año) para optimizar
- Considerar usar `WEB_FORECAST_VENTAS_REPORTE_ACTIVIDAD` para reportes (pre-agregada)

---

## 📌 PRÓXIMOS PASOS

### ✅ Completado:
- [x] Estructura de tablas críticas
- [x] Ejemplos de queries
- [x] Relaciones entre tablas

### ⏳ Pendiente:
- [ ] Explorar tabla de **Presupuesto/Metas** (en BD local SIG)
- [ ] Explorar tabla de **Inventario/Stock** (en SAP)
- [ ] Explorar tabla de **NPS/Encuestas**
- [ ] Validar permisos de lectura en todas las tablas
- [ ] Optimizar índices si es necesario
- [ ] Crear vistas para pre-agregación

---

## 📞 CONTACTOS

| Rol | Persona | Email |
|-----|---------|-------|
| **Especialista IA** | Oscar Núñez | oscar.nunez@mtind.com |
| **Jefe TI** | Manuel Calderón | manuel.calderon@mtind.com |
| **Jefe Ventas** | Martin Castro | martin.castro@mtind.com |

---

**Documento Data Dictionary completado. Usar como referencia para desarrollo de herramientas.**

*Última actualización: 20 de agosto de 2026*
