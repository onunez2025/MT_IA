# backend/tools/local_tools.py
"""
Herramientas que consultan la BD PUNTO_VENTA (192.168.1.160).

Fase 0.5 — primeras 4 tools (ya en producción):
  get_stock_by_product, get_pending_orders, get_returns_summary, get_customer_contact

Fase 0.6 — 8 quick wins nuevas:
  get_open_receivables, get_customer_credit, get_customer_price, get_clients_by_store,
  get_service_orders, get_delivery_status, get_inventory_value, get_nps_summary

Todas son estrictamente read-only (punto_venta_sql.query_readonly).
"""
import logging
from datetime import datetime
from typing import Dict, Any, Optional

from connectors.sql_connector import punto_venta_sql, azure_sql

logger = logging.getLogger(__name__)


# ─────────────────────────────────────────────────────────────────────────────
# 1. get_stock_by_product — Stock en tiempo real
# ─────────────────────────────────────────────────────────────────────────────
async def get_stock_by_product(
    product_name: Optional[str] = None,
    product_code: Optional[str] = None,
    center: Optional[str] = None,
    top_n: int = 20,
) -> Dict[str, Any]:
    """
    Consulta el stock disponible (libre, bloqueado, en tránsito) por material.

    Usa SAP_MM_MARD_DATOS_ALMACEN_MATERIAL + SAP_MM_MAKT_DESCRIPCION_MATERIAL.
    Filtra por nombre/código de material y opcionalmente por centro (almacén).

    Args:
        product_name: Nombre o fragmento del material. Ej: 'TERMA SOLE', 'COBRE'.
        product_code: Código SAP exacto del material. Ej: '3121SOLEGAS10M2CT'.
        center:       Centro/almacén SAP. Ej: 'M310', 'G411'. Sin valor = todos.
        top_n:        Máximo de materiales a devolver. Default: 20.
    """
    top_n = max(1, min(int(top_n), 50))

    # Construir filtros
    where_parts = ["m.DE_stock_libre_utilizacion > 0 OR m.DE_stock_bloqueado > 0"]

    if product_code:
        safe = product_code.replace("'", "''").upper()
        where_parts.append(f"m.VC_codigo_material = '{safe}'")
    elif product_name:
        safe = product_name.replace("'", "''").upper()
        where_parts.append(f"d.VC_denominacion_material_1 LIKE '%{safe}%'")

    if center:
        safe_c = center.replace("'", "''").upper()
        where_parts.append(f"m.VC_codigo_centro = '{safe_c}'")

    where_clause = "WHERE " + " AND ".join(where_parts)

    rows = await punto_venta_sql.query_readonly(f"""
        SELECT TOP {top_n}
            m.VC_codigo_material                        AS codigo,
            MAX(d.VC_denominacion_material_1)           AS descripcion,
            m.VC_codigo_centro                          AS centro,
            m.VC_codigo_almacen                         AS almacen,
            SUM(ISNULL(m.DE_stock_libre_utilizacion,0)) AS stock_libre,
            SUM(ISNULL(m.DE_stock_bloqueado,0))         AS stock_bloqueado,
            SUM(ISNULL(m.DE_stock_traslado,0))          AS stock_en_transito,
            SUM(ISNULL(m.DE_stock_control_calidad,0))   AS stock_calidad,
            SUM(ISNULL(m.DE_stock_devoluciones,0))      AS stock_devoluciones
        FROM dbo.SAP_MM_MARD_DATOS_ALMACEN_MATERIAL m
        LEFT JOIN dbo.SAP_MM_MAKT_DESCRIPCION_MATERIAL d
            ON d.VC_codigo_material = m.VC_codigo_material
        {where_clause}
        GROUP BY m.VC_codigo_material, m.VC_codigo_centro, m.VC_codigo_almacen
        ORDER BY stock_libre DESC
    """)

    return {
        "filtro_nombre": product_name,
        "filtro_codigo": product_code,
        "filtro_centro": center,
        "total_registros": len(rows),
        "materiales": [
            {
                "codigo": r.get("codigo"),
                "descripcion": r.get("descripcion"),
                "centro": r.get("centro"),
                "almacen": r.get("almacen"),
                "stock_libre": round(float(r.get("stock_libre") or 0), 3),
                "stock_bloqueado": round(float(r.get("stock_bloqueado") or 0), 3),
                "stock_en_transito": round(float(r.get("stock_en_transito") or 0), 3),
                "stock_calidad": round(float(r.get("stock_calidad") or 0), 3),
                "stock_devoluciones": round(float(r.get("stock_devoluciones") or 0), 3),
            }
            for r in rows
        ],
        "timestamp": datetime.utcnow().isoformat(),
    }


# ─────────────────────────────────────────────────────────────────────────────
# 2. get_pending_orders — Entregas pendientes (sin movimiento de mercancía)
# ─────────────────────────────────────────────────────────────────────────────
async def get_pending_orders(
    period: Optional[str] = None,
    store_code: Optional[str] = None,
    top_n: int = 30,
) -> Dict[str, Any]:
    """
    Lista entregas pendientes de SAP: sin movimiento de mercancía registrado
    (VC_fecha_mov_mercancia_real = '00000000' o VC_estado = '0').

    Usa SAP.SD_ENTREGAS en Azure SQL. Fechas en formato YYYYMMDD (varchar).

    Args:
        period:     Período YYYY-MM o YYYY. Sin valor = mes actual.
        store_code: Código de organización de venta. Ej: '1301', '1302'.
        top_n:      Máximo de entregas a listar. Default: 30.
    """
    top_n = max(1, min(int(top_n), 100))
    now   = datetime.now()

    # Calcular rango de fechas en formato YYYYMMDD
    if not period:
        fecha_desde = now.strftime("%Y%m01")
        fecha_hasta = now.strftime("%Y%m%d")
        label       = now.strftime("%B %Y")
    elif "-" in str(period):
        y, m = str(period).split("-")
        fecha_desde = f"{y}{int(m):02d}01"
        fecha_hasta = f"{y}{int(m):02d}31"
        label       = f"{m}/{y}"
    else:
        fecha_desde = f"{period}0101"
        fecha_hasta = f"{period}1231"
        label       = str(period)

    where_parts = [
        f"VC_fecha_creacion >= '{fecha_desde}'",
        f"VC_fecha_creacion <= '{fecha_hasta}'",
        "VC_estado = '0'",        # sin movimiento de mercancía
    ]

    if store_code:
        safe_s = store_code.replace("'", "''")
        where_parts.append(f"VC_organizacion_venta = '{safe_s}'")

    where_clause = "WHERE " + " AND ".join(f"({p})" for p in where_parts)

    # Resumen agregado
    summary = await azure_sql.query_readonly(f"""
        SELECT
            COUNT(DISTINCT VC_entrega_numero)  AS total_entregas,
            COUNT(*)                           AS total_posiciones,
            SUM(DE_cantidad)                   AS total_unidades
        FROM SAP.SD_ENTREGAS
        {where_clause}
    """)

    # Detalle de entregas (agrupado por numero)
    rows = await azure_sql.query_readonly(f"""
        SELECT TOP {top_n}
            VC_entrega_numero           AS entrega,
            MAX(VC_fecha_creacion)      AS fecha_creacion,
            MAX(VC_entrega_fecha)       AS fecha_entrega_prog,
            MAX(VC_organizacion_venta)  AS org_venta,
            MAX(VC_oficina_venta)       AS oficina_venta,
            COUNT(*)                    AS posiciones,
            SUM(DE_cantidad)            AS unidades
        FROM SAP.SD_ENTREGAS
        {where_clause}
        GROUP BY VC_entrega_numero
        ORDER BY MAX(VC_fecha_creacion) DESC
    """)

    s = summary[0] if summary else {}
    total_e  = int(s.get("total_entregas") or 0)
    total_p  = int(s.get("total_posiciones") or 0)
    total_u  = float(s.get("total_unidades") or 0)

    return {
        "periodo": label,
        "filtro_organizacion": store_code,
        "total_entregas_pendientes": total_e,
        "total_posiciones": total_p,
        "total_unidades": round(total_u, 2),
        "entregas": [
            {
                "entrega": r.get("entrega"),
                "fecha_creacion": str(r.get("fecha_creacion") or ""),
                "fecha_entrega_programada": str(r.get("fecha_entrega_prog") or ""),
                "org_venta": r.get("org_venta"),
                "oficina_venta": r.get("oficina_venta"),
                "posiciones": int(r.get("posiciones") or 0),
                "unidades": round(float(r.get("unidades") or 0), 2),
            }
            for r in rows
        ],
        "timestamp": datetime.utcnow().isoformat(),
    }


# ─────────────────────────────────────────────────────────────────────────────
# 3. get_returns_summary — Análisis de devoluciones
# ─────────────────────────────────────────────────────────────────────────────
async def get_returns_summary(
    period: Optional[str] = None,
    top_n: int = 15,
) -> Dict[str, Any]:
    """
    Resumen de devoluciones: monto total, productos más devueltos, conteo.

    Usa PV_DEVOLUCION_SOLICITUD (cabecera) + PV_DEVOLUCION_SOLICITUD_DETALLE (líneas).

    Args:
        period: Período YYYY-MM o YYYY. Sin valor = año actual.
        top_n:  Número de productos a mostrar en el ranking. Default: 15.
    """
    top_n = max(1, min(int(top_n), 50))
    now   = datetime.now()

    if not period:
        year_filter  = f"AND YEAR(s.DT_fecha_ins) = {now.year}"
        month_filter = ""
    elif "-" in str(period):
        y, m = str(period).split("-")
        year_filter  = f"AND YEAR(s.DT_fecha_ins) = {int(y)}"
        month_filter = f"AND MONTH(s.DT_fecha_ins) = {int(m)}"
    else:
        year_filter  = f"AND YEAR(s.DT_fecha_ins) = {int(period)}"
        month_filter = ""

    # Resumen general
    summary = await punto_venta_sql.query_readonly(f"""
        SELECT
            COUNT(DISTINCT s.IN_solicitud_id)   AS total_solicitudes,
            SUM(d.DE_producto_cantidad_devuelta) AS total_unidades,
            SUM(d.DE_producto_precio * d.DE_producto_cantidad_devuelta) AS monto_total
        FROM dbo.PV_DEVOLUCION_SOLICITUD s
        JOIN dbo.PV_DEVOLUCION_SOLICITUD_DETALLE d
            ON d.IN_solicitud_id = s.IN_solicitud_id
        WHERE s.IN_estado_id NOT IN (5,6)   -- excluir rechazadas/canceladas
          {year_filter} {month_filter}
    """)

    # Top productos devueltos
    top_prods = await punto_venta_sql.query_readonly(f"""
        SELECT TOP {top_n}
            d.VC_producto_codigo        AS codigo,
            MAX(d.VC_producto_descripcion) AS descripcion,
            COUNT(DISTINCT s.IN_solicitud_id) AS solicitudes,
            SUM(d.DE_producto_cantidad_devuelta) AS unidades_devueltas,
            SUM(d.DE_producto_precio * d.DE_producto_cantidad_devuelta) AS monto_devuelto
        FROM dbo.PV_DEVOLUCION_SOLICITUD s
        JOIN dbo.PV_DEVOLUCION_SOLICITUD_DETALLE d
            ON d.IN_solicitud_id = s.IN_solicitud_id
        WHERE d.VC_producto_codigo IS NOT NULL
          AND s.IN_estado_id NOT IN (5,6)
          {year_filter} {month_filter}
        GROUP BY d.VC_producto_codigo
        ORDER BY monto_devuelto DESC
    """)

    s = summary[0] if summary else {}
    return {
        "periodo": period or f"{now.year} (YTD)",
        "resumen": {
            "total_solicitudes": int(s.get("total_solicitudes") or 0),
            "total_unidades_devueltas": round(float(s.get("total_unidades") or 0), 2),
            "monto_total_devuelto": round(float(s.get("monto_total") or 0), 2),
        },
        "top_productos_devueltos": [
            {
                "codigo": r.get("codigo"),
                "descripcion": r.get("descripcion"),
                "solicitudes": int(r.get("solicitudes") or 0),
                "unidades_devueltas": round(float(r.get("unidades_devueltas") or 0), 2),
                "monto_devuelto": round(float(r.get("monto_devuelto") or 0), 2),
            }
            for r in top_prods
        ],
        "timestamp": datetime.utcnow().isoformat(),
    }


# ─────────────────────────────────────────────────────────────────────────────
# 4. get_customer_contact — Datos de contacto de un cliente
# ─────────────────────────────────────────────────────────────────────────────
async def get_customer_contact(
    customer_id: str,
) -> Dict[str, Any]:
    """
    Datos de contacto enriquecidos de un cliente: nombre, RUC/DNI,
    teléfono, email, dirección. Combina SAP_SD_KNA1_CLIENTE con ANALYTICS_VENTAS.

    Args:
        customer_id: Código SAP del cliente (obtenido con search_customer_by_name).
    """
    safe_id = customer_id.strip().replace("'", "''")

    # Maestro SAP
    kna1 = await punto_venta_sql.query_readonly(f"""
        SELECT TOP 1
            VC_codigo_cliente               AS codigo,
            LTRIM(RTRIM(VC_nombre_1))       AS nombre_1,
            LTRIM(RTRIM(VC_nombre_2))       AS nombre_2,
            VC_numero_identificacion_fiscal AS ruc_dni,
            VC_telefono                     AS telefono_sap,
            VC_tipo_nif                     AS tipo_doc,
            DT_fecha_creacion               AS fecha_creacion,
            VC_codigo_grupo_cuenta          AS grupo_cuenta
        FROM dbo.SAP_SD_KNA1_CLIENTE
        WHERE VC_codigo_cliente = '{safe_id}'
           OR LTRIM('0' + VC_codigo_cliente) = '{safe_id}'
    """)

    # Email y teléfono desde ventas (ANALYTICS_VENTAS, más actualizado)
    av = await punto_venta_sql.query_readonly(f"""
        SELECT TOP 1
            MAX(VC_correo_cliente)    AS correo,
            MAX(VC_telefono_cliente)  AS telefono,
            MAX(VC_nombre_completo)   AS nombre_completo,
            MAX(VC_nombre_via)        AS via,
            MAX(VC_numero_puerta)     AS numero,
            MAX(VC_nombre_zona)       AS zona,
            MAX(VC_ubigeo)            AS ubigeo
        FROM dbo.ANALYTICS_VENTAS
        WHERE VC_solicitante_codigo = '{safe_id}'
          AND VC_correo_cliente IS NOT NULL
          AND VC_correo_cliente NOT LIKE '%mt_fe@%'
          AND VC_correo_cliente NOT LIKE '%sole.com%'
    """)

    if not kna1:
        return {
            "customer_id": customer_id,
            "error": f"No se encontró el cliente con código '{customer_id}'.",
        }

    k = kna1[0]
    a = av[0] if av else {}

    nombre = (k.get("nombre_1") or "") + (" " + k.get("nombre_2") if k.get("nombre_2") else "")
    if a.get("nombre_completo"):
        nombre = a["nombre_completo"]

    return {
        "customer_id": safe_id,
        "nombre": nombre.strip(),
        "ruc_dni": k.get("ruc_dni"),
        "tipo_documento": k.get("tipo_doc"),   # '06'=RUC, '01'=DNI, etc.
        "telefono": a.get("telefono") or k.get("telefono_sap") or None,
        "correo": a.get("correo"),
        "direccion": {
            "via": a.get("via"),
            "numero": a.get("numero"),
            "zona": a.get("zona"),
            "ubigeo": a.get("ubigeo"),
        },
        "fecha_alta_sap": str(k.get("fecha_creacion") or ""),
        "grupo_cuenta": k.get("grupo_cuenta"),
        "timestamp": datetime.utcnow().isoformat(),
    }


# ═══════════════════════════════════════════════════════════════════════════════
# FASE 0.6 — 8 Quick Wins
# ═══════════════════════════════════════════════════════════════════════════════

# ─────────────────────────────────────────────────────────────────────────────
# 5. get_open_receivables — Cuentas por cobrar abiertas
# ─────────────────────────────────────────────────────────────────────────────
async def get_open_receivables(
    customer_id: Optional[str] = None,
    days_overdue: Optional[int] = None,
    top_n: int = 30,
) -> Dict[str, Any]:
    """
    Lista de facturas pendientes de cobro (cuentas por cobrar abiertas).

    Usa dbo.TB_BAPI_AR_ACC_GETOPENITEMS + dbo.SAP_SD_KNA1_CLIENTE.

    Args:
        customer_id:  Código SAP del cliente (opcional). Sin valor = todos los clientes.
        days_overdue: Mostrar solo documentos con N días o más sin pagar (opcional).
        top_n:        Máximo de documentos a devolver. Default: 30.
    """
    top_n = max(1, min(int(top_n), 100))

    where_parts = [
        "CLEAR_DATE = '0000-00-00'",   # solo no compensados (abiertos)
        "DB_CR_IND = 'S'",             # solo débitos (facturas por cobrar)
        "LC_AMOUNT > 0",
    ]

    if customer_id:
        safe_c = customer_id.strip().replace("'", "''")
        where_parts.append(f"CUSTOMER = '{safe_c}'")

    if days_overdue is not None:
        where_parts.append(
            f"DATEDIFF(DAY, TRY_CAST(BLINE_DATE AS DATE), GETDATE()) >= {int(days_overdue)}"
        )

    where_clause = "WHERE " + " AND ".join(f"({p})" for p in where_parts)

    rows = await punto_venta_sql.query_readonly(f"""
        SELECT TOP {top_n}
            ar.CUSTOMER                                              AS cliente_codigo,
            k.VC_nombre_1                                           AS cliente_nombre,
            ar.DOC_NO                                               AS documento,
            ar.REF_DOC_NO                                           AS referencia,
            ar.DOC_TYPE                                             AS tipo_doc,
            ar.PSTNG_DATE                                           AS fecha_contabilizacion,
            ar.BLINE_DATE                                           AS fecha_base_pago,
            ar.PMNTTRMS                                             AS condicion_pago,
            ar.LC_AMOUNT                                            AS monto_soles,
            DATEDIFF(DAY, TRY_CAST(ar.BLINE_DATE AS DATE), GETDATE()) AS dias_antiguedad,
            ar.CURRENCY                                             AS moneda
        FROM dbo.TB_BAPI_AR_ACC_GETOPENITEMS ar
        LEFT JOIN dbo.SAP_SD_KNA1_CLIENTE k
            ON k.VC_codigo_cliente = ar.CUSTOMER
        {where_clause}
        ORDER BY dias_antiguedad DESC
    """)

    total_monto = sum(float(r.get("monto_soles") or 0) for r in rows)
    vencidos = [r for r in rows
                if (r.get("dias_antiguedad") or 0) > 0]

    return {
        "filtro_cliente": customer_id,
        "filtro_dias_vencido": days_overdue,
        "total_documentos_abiertos": len(rows),
        "monto_total_soles": round(total_monto, 2),
        "documentos_vencidos": len(vencidos),
        "monto_vencido_soles": round(sum(float(r.get("monto_soles") or 0)
                                         for r in vencidos), 2),
        "documentos": [
            {
                "cliente_codigo": r.get("cliente_codigo"),
                "cliente_nombre": (r.get("cliente_nombre") or "").strip() or None,
                "documento": r.get("documento"),
                "referencia": r.get("referencia"),
                "tipo_doc": r.get("tipo_doc"),
                "fecha_emision": str(r.get("fecha_contabilizacion") or ""),
                "fecha_base_pago": str(r.get("fecha_base_pago") or ""),
                "condicion_pago": r.get("condicion_pago"),
                "monto_soles": round(float(r.get("monto_soles") or 0), 2),
                "dias_antiguedad": int(r.get("dias_antiguedad") or 0),
            }
            for r in rows
        ],
        "timestamp": datetime.utcnow().isoformat(),
    }


# ─────────────────────────────────────────────────────────────────────────────
# 6. get_customer_credit — Límite y saldo de crédito SAP
# ─────────────────────────────────────────────────────────────────────────────
async def get_customer_credit(
    customer_id: str,
) -> Dict[str, Any]:
    """
    Límite de crédito total, crédito utilizado y disponible de un cliente.

    Combina SAP_SD_KNKA_GESTION_CREDITOS_CLIENTE_DATOS_CENTRALES (límite total)
    y SAP_SD_KNKK_GESTION_CREDITOS_CLIENTE (exposición actual).

    Args:
        customer_id: Código SAP del cliente.
    """
    safe_id = customer_id.strip().replace("'", "''")
    # Pad a 10 dígitos si el cliente viene sin ceros
    padded = safe_id.zfill(10)

    knka = await punto_venta_sql.query_readonly(f"""
        SELECT TOP 1
            VC_codigo_cliente   AS codigo,
            DE_limite_total     AS limite_total,
            DE_limite_individual AS limite_individual,
            VC_codigo_moneda    AS moneda
        FROM dbo.SAP_SD_KNKA_GESTION_CREDITOS_CLIENTE_DATOS_CENTRALES
        WHERE VC_codigo_cliente IN ('{safe_id}', '{padded}')
    """)

    knkk = await punto_venta_sql.query_readonly(f"""
        SELECT TOP 1
            DE_limite_credito       AS limite_credito,
            DE_valor_comercial      AS valor_comercial,
            DE_valor_credito        AS valor_credito,
            DE_comprometido_especial AS comprometido_especial,
            DT_fecha_ultimo_pago    AS ultimo_pago,
            DE_importe_ultimo_pago  AS importe_ultimo_pago,
            VC_clase_riesgo         AS clase_riesgo,
            CH_bloqueado_gestion_credito AS bloqueado
        FROM dbo.SAP_SD_KNKK_GESTION_CREDITOS_CLIENTE
        WHERE VC_codigo_cliente IN ('{safe_id}', '{padded}')
    """)

    if not knka and not knkk:
        return {
            "customer_id": customer_id,
            "sin_datos": True,
            "mensaje": (
                f"El cliente '{customer_id}' no tiene línea de crédito registrada en SAP. "
                "Puede ser un cliente de contado, un cliente nuevo sin límite asignado, "
                "o el código SAP no existe en las tablas de crédito (KNKA/KNKK)."
            ),
        }

    a = knka[0] if knka else {}
    b = knkk[0] if knkk else {}

    limite = float(b.get("limite_credito") or a.get("limite_total") or 0)
    utilizado = float(b.get("valor_comercial") or 0)
    disponible = max(0.0, limite - utilizado)
    bloqueado_raw = (b.get("bloqueado") or "").strip()

    return {
        "customer_id": customer_id,
        "limite_credito_soles": round(limite, 2),
        "limite_total_soles": round(float(a.get("limite_total") or 0), 2),
        "credito_utilizado_soles": round(utilizado, 2),
        "credito_disponible_soles": round(disponible, 2),
        "pct_utilizado": round(utilizado / limite * 100, 1) if limite > 0 else None,
        "credito_comprometido_soles": round(float(b.get("comprometido_especial") or 0), 2),
        "clase_riesgo": b.get("clase_riesgo"),
        "bloqueado": bool(bloqueado_raw),
        "ultimo_pago_fecha": str(b.get("ultimo_pago") or ""),
        "ultimo_pago_monto": round(float(b.get("importe_ultimo_pago") or 0), 2),
        "moneda": a.get("moneda") or "PEN",
        "timestamp": datetime.utcnow().isoformat(),
    }


# ─────────────────────────────────────────────────────────────────────────────
# 7. get_customer_price — Precio especial cliente-material
# ─────────────────────────────────────────────────────────────────────────────
async def get_customer_price(
    customer_id: str,
    product_name: Optional[str] = None,
    product_code: Optional[str] = None,
    top_n: int = 20,
) -> Dict[str, Any]:
    """
    Lista de precios especiales negociados para un cliente en el POS.

    Usa dbo.PV_MATERIAL_PRECIO_CLIENTE (precios por simulación SAP en PUNTO_VENTA).

    Args:
        customer_id:  Código SAP del cliente.
        product_name: Filtrar por nombre/fragmento del material (opcional).
        product_code: Filtrar por código exacto del material (opcional).
        top_n:        Máximo de materiales. Default: 20.
    """
    top_n = max(1, min(int(top_n), 50))
    safe_id = customer_id.strip().replace("'", "''")

    where_parts = [
        f"VC_codigo_cliente = '{safe_id}'",
        "DE_precio_neto > 0",
        "(VC_mensaje_error IS NULL OR LTRIM(RTRIM(VC_mensaje_error)) = '')",
    ]

    if product_code:
        safe_p = product_code.strip().replace("'", "''").upper()
        where_parts.append(f"VC_codigo_material = '{safe_p}'")
    elif product_name:
        safe_p = product_name.strip().replace("'", "''").upper()
        where_parts.append(f"VC_denominacion_material LIKE '%{safe_p}%'")

    where_clause = "WHERE " + " AND ".join(f"({p})" for p in where_parts)

    rows = await punto_venta_sql.query_readonly(f"""
        SELECT TOP {top_n}
            VC_codigo_material      AS codigo,
            VC_denominacion_material AS descripcion,
            DE_precio_neto          AS precio_neto,
            DE_precio_igv           AS igv,
            DE_precio_neto + DE_precio_igv AS precio_total,
            DE_cantidad             AS cantidad_base
        FROM dbo.PV_MATERIAL_PRECIO_CLIENTE
        {where_clause}
        ORDER BY DE_precio_neto DESC
    """)

    return {
        "customer_id": customer_id,
        "filtro_producto": product_name or product_code,
        "total_productos": len(rows),
        "nota": "Precios simulados desde SAP para este cliente. Pueden variar según canal y condiciones.",
        "precios": [
            {
                "codigo": r.get("codigo"),
                "descripcion": r.get("descripcion"),
                "precio_neto": round(float(r.get("precio_neto") or 0), 4),
                "igv": round(float(r.get("igv") or 0), 4),
                "precio_total_con_igv": round(float(r.get("precio_total") or 0), 4),
                "cantidad_base": round(float(r.get("cantidad_base") or 1), 2),
            }
            for r in rows
        ],
        "timestamp": datetime.utcnow().isoformat(),
    }


# ─────────────────────────────────────────────────────────────────────────────
# 8. get_clients_by_store — Cartera de clientes por oficina de venta
# ─────────────────────────────────────────────────────────────────────────────
async def get_clients_by_store(
    store_code: Optional[str] = None,
    zone: Optional[str] = None,
    top_n: int = 50,
) -> Dict[str, Any]:
    """
    Lista de clientes asignados a una oficina de venta o zona comercial.

    Usa dbo.CLIENTES_ZONA_VENTAS_MT + SAP_SD_KNA1_CLIENTE.

    Args:
        store_code: Código de la oficina de venta. Ej: 'ME10', 'SH01'.
        zone:       Código de zona de ventas (opcional). Ej: '15', '22'.
        top_n:      Máximo de clientes. Default: 50.
    """
    top_n = max(1, min(int(top_n), 200))
    where_parts: list = []

    if store_code:
        safe_s = store_code.strip().replace("'", "''").upper()
        where_parts.append(f"c.[Oficina de ventas] = '{safe_s}'")

    if zone:
        safe_z = zone.strip().replace("'", "''")
        where_parts.append(f"c.zona_ventas = '{safe_z}'")

    where_clause = ("WHERE " + " AND ".join(where_parts)) if where_parts else ""

    rows = await punto_venta_sql.query_readonly(f"""
        SELECT TOP {top_n}
            c.cliente                   AS codigo,
            k.VC_nombre_1               AS nombre,
            k.VC_numero_identificacion_fiscal AS ruc_dni,
            c.zona_ventas               AS zona,
            c.[Oficina de ventas]       AS oficina_venta,
            c.[Grupo de vendedores]     AS grupo_vendedores,
            c.[Condiciones de pago]     AS condicion_pago,
            c.canal                     AS canal,
            c.sector                    AS sector
        FROM dbo.CLIENTES_ZONA_VENTAS_MT c
        LEFT JOIN dbo.SAP_SD_KNA1_CLIENTE k
            ON k.VC_codigo_cliente = c.cliente
        {where_clause}
        ORDER BY c.cliente
    """)

    return {
        "filtro_tienda": store_code,
        "filtro_zona": zone,
        "total_clientes": len(rows),
        "clientes": [
            {
                "codigo": r.get("codigo"),
                "nombre": (r.get("nombre") or "").strip() or None,
                "ruc_dni": r.get("ruc_dni"),
                "zona": r.get("zona"),
                "oficina_venta": r.get("oficina_venta"),
                "canal": r.get("canal"),
                "condicion_pago": r.get("condicion_pago"),
            }
            for r in rows
        ],
        "timestamp": datetime.utcnow().isoformat(),
    }


# ─────────────────────────────────────────────────────────────────────────────
# 9. get_service_orders — Órdenes de servicio técnico
# ─────────────────────────────────────────────────────────────────────────────
async def get_service_orders(
    customer_doc: Optional[str] = None,
    product_name: Optional[str] = None,
    state: Optional[str] = None,
    days: int = 90,
    top_n: int = 20,
) -> Dict[str, Any]:
    """
    Historial de órdenes de servicio técnico (instalación, reparación, mantenimiento).

    Usa CAC.OS (2.5M filas). Información de cliente, producto, técnico,
    tipo de falla y resultado del servicio.

    Args:
        customer_doc: DNI, RUC o carnet del cliente (opcional).
        product_name: Nombre o fragmento del producto (opcional). Ej: 'TERMA'.
        state:        Estado del servicio: 'COMPLETADA', 'PENDIENTE', 'ANULADA', etc.
                      Sin valor = todos los estados.
        days:         Número de días hacia atrás. Default: 90.
        top_n:        Máximo de órdenes. Default: 20.
    """
    top_n = max(1, min(int(top_n), 100))
    days = max(1, min(int(days), 730))

    where_parts = [
        f"INSERTADO_FECHA >= DATEADD(DAY, -{days}, GETDATE())"
    ]

    if customer_doc:
        safe_doc = customer_doc.strip().replace("'", "''")
        where_parts.append(f"LTRIM(RTRIM(NRO_DOCUMENTO)) = '{safe_doc}'")

    if product_name:
        safe_p = product_name.strip().replace("'", "''").upper()
        where_parts.append(f"UPPER(PRODUCTO_NOMBRE) LIKE '%{safe_p}%'")

    if state:
        safe_st = state.strip().replace("'", "''").upper()
        where_parts.append(f"UPPER(ESTADO) = '{safe_st}'")

    where_clause = "WHERE " + " AND ".join(f"({p})" for p in where_parts)

    rows = await punto_venta_sql.query_readonly(f"""
        SELECT TOP {top_n}
            OS                      AS orden_servicio,
            FECHA_REGISTRO          AS fecha_registro,
            FECHA_VISITA            AS fecha_visita,
            CLIENTE_NOMBRE + ' ' + CLIENTE_APELLIDO AS cliente,
            NRO_DOCUMENTO           AS doc_cliente,
            DISTRITO                AS distrito,
            PRODUCTO_NOMBRE         AS producto,
            PROD_SKU                AS sku,
            TECNICO_ASIGNADO        AS tecnico,
            ESTADO                  AS estado,
            SERVICIO_DESCRIPCION    AS tipo_servicio,
            CODIGO_FALLA            AS cod_falla,
            DESCRIPCION_FALLA       AS falla,
            OBSERVACIONES_TECNICO   AS observacion,
            COSTO_SERVICIO          AS costo,
            GARANTIA                AS garantia
        FROM CAC.OS
        {where_clause}
        ORDER BY INSERTADO_FECHA DESC
    """)

    # Resumen por estado
    estados_count: Dict[str, int] = {}
    for r in rows:
        est = r.get("estado") or "DESCONOCIDO"
        estados_count[est] = estados_count.get(est, 0) + 1

    return {
        "filtro_doc_cliente": customer_doc,
        "filtro_producto": product_name,
        "filtro_estado": state,
        "periodo_dias": days,
        "total_ordenes": len(rows),
        "resumen_por_estado": estados_count,
        "ordenes": [
            {
                "orden": r.get("orden_servicio"),
                "fecha_registro": str(r.get("fecha_registro") or ""),
                "fecha_visita": str(r.get("fecha_visita") or ""),
                "cliente": (r.get("cliente") or "").strip(),
                "doc_cliente": (r.get("doc_cliente") or "").strip(),
                "distrito": r.get("distrito"),
                "producto": r.get("producto"),
                "sku": r.get("sku"),
                "tecnico": r.get("tecnico"),
                "estado": r.get("estado"),
                "tipo_servicio": r.get("tipo_servicio"),
                "falla": r.get("falla") or None,
                "observacion": r.get("observacion") or None,
                "costo": r.get("costo"),
                "garantia": r.get("garantia"),
            }
            for r in rows
        ],
        "timestamp": datetime.utcnow().isoformat(),
    }


# ─────────────────────────────────────────────────────────────────────────────
# 10. get_delivery_status — Estado de entregas Beetrack
# ─────────────────────────────────────────────────────────────────────────────

# Mapa de status Beetrack (basado en BEETRACK.ESTADOS observado)
_BEETRACK_STATUS = {
    1: "Pendiente",
    2: "En ruta / Asignado",
    3: "Entregado",
    4: "Fallido",
    5: "Anulado",
    6: "Reprogramado",
}


async def get_delivery_status(
    order_number: Optional[str] = None,
    guide_number: Optional[str] = None,
    customer_name: Optional[str] = None,
    days: int = 30,
    top_n: int = 20,
) -> Dict[str, Any]:
    """
    Estado actual de entregas/despachos en el sistema Beetrack.

    Usa BEETRACK.DESPACHOS. Permite rastrear envíos por número de pedido,
    guía o nombre del cliente.

    Args:
        order_number:  Número de pedido SAP. Ej: '7501653027'.
        guide_number:  Número de guía de remisión. Ej: '09-00006-0621325'.
        customer_name: Nombre o fragmento del destinatario.
        days:          Días hacia atrás a consultar. Default: 30.
        top_n:         Máximo de despachos. Default: 20.
    """
    top_n = max(1, min(int(top_n), 100))
    days = max(1, min(int(days), 365))

    where_parts = [
        f"insert_fecha >= DATEADD(DAY, -{days}, GETDATE())",
        "flag_eliminado = 0",
    ]

    if order_number:
        safe_o = order_number.strip().replace("'", "''")
        where_parts.append(f"(pedido = '{safe_o}' OR identifier = '{safe_o}')")

    if guide_number:
        safe_g = guide_number.strip().replace("'", "''")
        where_parts.append(f"(numero_guia = '{safe_g}' OR identifier = '{safe_g}')")

    if customer_name:
        safe_n = customer_name.strip().replace("'", "''").upper()
        where_parts.append(f"UPPER(contact_name) LIKE '%{safe_n}%'")

    where_clause = "WHERE " + " AND ".join(f"({p})" for p in where_parts)

    rows = await punto_venta_sql.query_readonly(f"""
        SELECT TOP {top_n}
            id_despacho             AS id_despacho,
            pedido                  AS pedido_sap,
            identifier              AS guia_identifier,
            numero_guia             AS numero_guia,
            contact_name            AS destinatario,
            contact_address         AS direccion,
            contact_phone           AS telefono,
            fecha_despacho          AS fecha_despacho,
            min_delivery_time       AS ventana_inicio,
            max_delivery_time       AS ventana_fin,
            status                  AS status_codigo,
            substatus_code          AS substatus_codigo,
            resp_status             AS estado_actual,
            resp_substatus          AS subestado_actual,
            resp_arrived_at         AS hora_llegada,
            truck_identifier        AS vehiculo,
            flag_completo           AS completado,
            insert_fecha            AS fecha_registro
        FROM BEETRACK.DESPACHOS
        {where_clause}
        ORDER BY insert_fecha DESC
    """)

    return {
        "filtro_pedido": order_number,
        "filtro_guia": guide_number,
        "filtro_cliente": customer_name,
        "periodo_dias": days,
        "total_despachos": len(rows),
        "despachos": [
            {
                "id": r.get("id_despacho"),
                "pedido_sap": r.get("pedido_sap"),
                "guia": r.get("numero_guia") or r.get("guia_identifier"),
                "destinatario": r.get("destinatario"),
                "direccion": r.get("direccion"),
                "telefono": r.get("telefono"),
                "fecha_despacho": str(r.get("fecha_despacho") or ""),
                "ventana_entrega": (
                    f"{r.get('ventana_inicio')} → {r.get('ventana_fin')}"
                    if r.get("ventana_inicio") else None
                ),
                "status": _BEETRACK_STATUS.get(
                    int(r.get("status_codigo") or 0), f"Status {r.get('status_codigo')}"
                ),
                "estado_detallado": r.get("estado_actual") or None,
                "subestado": r.get("subestado_actual") or None,
                "hora_llegada": str(r.get("hora_llegada") or ""),
                "vehiculo": r.get("vehiculo"),
                "completado": bool(r.get("completado")),
            }
            for r in rows
        ],
        "timestamp": datetime.utcnow().isoformat(),
    }


# ─────────────────────────────────────────────────────────────────────────────
# 11. get_inventory_value — Valor del inventario en soles
# ─────────────────────────────────────────────────────────────────────────────
async def get_inventory_value(
    center: Optional[str] = None,
    product_name: Optional[str] = None,
    top_n: int = 20,
) -> Dict[str, Any]:
    """
    Valor económico del inventario en soles: precio estándar × stock.

    Usa SAP_MM_MBEW_VALORACION_MATERIAL + SAP_MM_MAKT_DESCRIPCION_MATERIAL.

    Args:
        center:       Ámbito/centro de valoración. Ej: 'M310', 'G411'. Sin valor = todos.
        product_name: Nombre o fragmento del material.
        top_n:        Materiales con mayor valor. Default: 20.
    """
    top_n = max(1, min(int(top_n), 50))

    where_parts = [
        "m.DE_stock_total > 0",
        "m.DE_valor_total > 0",
    ]

    if center:
        safe_c = center.strip().replace("'", "''").upper()
        where_parts.append(f"m.VC_ambito_valoracion = '{safe_c}'")

    if product_name:
        safe_p = product_name.strip().replace("'", "''").upper()
        where_parts.append(f"d.VC_denominacion_material_1 LIKE '%{safe_p}%'")

    where_clause = "WHERE " + " AND ".join(f"({p})" for p in where_parts)

    rows = await punto_venta_sql.query_readonly(f"""
        SELECT TOP {top_n}
            m.VC_codigo_material            AS codigo,
            MAX(d.VC_denominacion_material_1) AS descripcion,
            m.VC_ambito_valoracion          AS centro_valoracion,
            SUM(m.DE_stock_total)           AS stock_total,
            SUM(m.DE_valor_total)           AS valor_total_soles,
            AVG(m.DE_precio_estandar)       AS precio_estandar,
            AVG(m.DE_precio_medio_variable) AS precio_promedio
        FROM dbo.SAP_MM_MBEW_VALORACION_MATERIAL m
        LEFT JOIN dbo.SAP_MM_MAKT_DESCRIPCION_MATERIAL d
            ON d.VC_codigo_material = m.VC_codigo_material
        {where_clause}
        GROUP BY m.VC_codigo_material, m.VC_ambito_valoracion
        ORDER BY valor_total_soles DESC
    """)

    # Resumen total
    summary = await punto_venta_sql.query_readonly(f"""
        SELECT
            COUNT(DISTINCT m.VC_codigo_material) AS materiales_con_stock,
            SUM(m.DE_valor_total)                AS valor_inventario_total
        FROM dbo.SAP_MM_MBEW_VALORACION_MATERIAL m
        LEFT JOIN dbo.SAP_MM_MAKT_DESCRIPCION_MATERIAL d
            ON d.VC_codigo_material = m.VC_codigo_material
        {where_clause}
    """)

    s = summary[0] if summary else {}

    return {
        "filtro_centro": center,
        "filtro_producto": product_name,
        "resumen": {
            "materiales_con_stock": int(s.get("materiales_con_stock") or 0),
            "valor_inventario_total_soles": round(float(s.get("valor_inventario_total") or 0), 2),
        },
        "top_por_valor": [
            {
                "codigo": r.get("codigo"),
                "descripcion": r.get("descripcion"),
                "centro_valoracion": r.get("centro_valoracion"),
                "stock_total": round(float(r.get("stock_total") or 0), 3),
                "valor_total_soles": round(float(r.get("valor_total_soles") or 0), 2),
                "precio_estandar": round(float(r.get("precio_estandar") or 0), 4),
                "precio_promedio": round(float(r.get("precio_promedio") or 0), 4),
            }
            for r in rows
        ],
        "timestamp": datetime.utcnow().isoformat(),
    }


# ─────────────────────────────────────────────────────────────────────────────
# 12. get_nps_summary — Resumen NPS / satisfacción del cliente
# ─────────────────────────────────────────────────────────────────────────────
async def get_nps_summary(
    period: Optional[str] = None,
    top_n: int = 10,
) -> Dict[str, Any]:
    """
    Resumen del Net Promoter Score (NPS) de servicio técnico.

    Score 0-6 = Detractor | 7-8 = Pasivo | 9-10 = Promotor.
    Usa dbo.CRM_OPORTUNIDAD_NPS.

    Args:
        period: Período YYYY-MM o YYYY. Sin valor = año actual.
        top_n:  Comentarios más recientes a incluir. Default: 10.
    """
    top_n = max(1, min(int(top_n), 50))
    now = datetime.now()

    if not period:
        date_filter = f"AND YEAR(DT_sole_fechaencuesta) = {now.year}"
    elif "-" in str(period):
        y, m = str(period).split("-")
        date_filter = (
            f"AND YEAR(DT_sole_fechaencuesta) = {int(y)}"
            f" AND MONTH(DT_sole_fechaencuesta) = {int(m)}"
        )
    else:
        date_filter = f"AND YEAR(DT_sole_fechaencuesta) = {int(period)}"

    # Resumen NPS
    agg = await punto_venta_sql.query_readonly(f"""
        SELECT
            COUNT(*) AS total_encuestas,
            AVG(CAST(VC_sole_puntuacion AS FLOAT)) AS promedio,
            SUM(CASE WHEN VC_sole_puntuacion >= 9 THEN 1 ELSE 0 END) AS promotores,
            SUM(CASE WHEN VC_sole_puntuacion BETWEEN 7 AND 8 THEN 1 ELSE 0 END) AS pasivos,
            SUM(CASE WHEN VC_sole_puntuacion <= 6 THEN 1 ELSE 0 END) AS detractores
        FROM dbo.CRM_OPORTUNIDAD_NPS
        WHERE DT_sole_fechaencuesta IS NOT NULL
          {date_filter}
    """)

    # Comentarios recientes (con texto)
    comments = await punto_venta_sql.query_readonly(f"""
        SELECT TOP {top_n}
            VC_sole_puntuacion          AS puntuacion,
            VC_sole_comentarios         AS comentario,
            DT_sole_fechaencuesta       AS fecha,
            VC_sole_tipodocumento       AS tipo_doc,
            VC_sole_numerodocumento     AS num_doc,
            VC_sole_ordenservicio       AS orden_servicio
        FROM dbo.CRM_OPORTUNIDAD_NPS
        WHERE VC_sole_comentarios IS NOT NULL
          AND LTRIM(RTRIM(VC_sole_comentarios)) != ''
          {date_filter}
        ORDER BY DT_sole_fechaencuesta DESC
    """)

    s = agg[0] if agg else {}
    total = int(s.get("total_encuestas") or 0)
    promotores = int(s.get("promotores") or 0)
    detractores = int(s.get("detractores") or 0)
    nps_score = round(
        ((promotores - detractores) / total * 100) if total > 0 else 0, 1
    )

    return {
        "periodo": period or f"{now.year} (YTD)",
        "nps_score": nps_score,   # -100 a +100 (industria: >50 = excelente)
        "total_encuestas": total,
        "promedio_puntuacion": round(float(s.get("promedio") or 0), 2),
        "distribucion": {
            "promotores_9_10": promotores,
            "pasivos_7_8": int(s.get("pasivos") or 0),
            "detractores_0_6": detractores,
            "pct_promotores": round(promotores / total * 100, 1) if total > 0 else 0,
            "pct_detractores": round(detractores / total * 100, 1) if total > 0 else 0,
        },
        "comentarios_recientes": [
            {
                "puntuacion": int(r.get("puntuacion") or 0),
                "categoria": (
                    "Promotor" if int(r.get("puntuacion") or 0) >= 9
                    else "Pasivo" if int(r.get("puntuacion") or 0) >= 7
                    else "Detractor"
                ),
                "comentario": (r.get("comentario") or "")[:300],  # truncar largo
                "fecha": str(r.get("fecha") or ""),
                "orden_servicio": r.get("orden_servicio"),
            }
            for r in comments
        ],
        "timestamp": datetime.utcnow().isoformat(),
    }
