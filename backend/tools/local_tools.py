# backend/tools/local_tools.py
"""
Herramientas que consultan la BD PUNTO_VENTA (192.168.1.160).

Cuatro herramientas nuevas de Fase 0.5:
  1. get_stock_by_product   — stock disponible por material y almacén
  2. get_pending_orders     — pedidos con bloqueo de entrega o facturación
  3. get_returns_summary    — devoluciones por período y producto
  4. get_customer_contact   — datos de contacto enriquecidos de un cliente

Todas son estrictamente read-only (punto_venta_sql.query_readonly).
"""
import logging
from datetime import datetime
from typing import Dict, Any, Optional

from connectors.sql_connector import punto_venta_sql

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
# 2. get_pending_orders — Pedidos bloqueados
# ─────────────────────────────────────────────────────────────────────────────
async def get_pending_orders(
    days: int = 90,
    store_code: Optional[str] = None,
    block_type: Optional[str] = None,
    top_n: int = 30,
) -> Dict[str, Any]:
    """
    Lista pedidos con bloqueo de entrega o de facturación.

    Usa dbo.SD_PEDIDOS. La fecha de creación está en formato YYYYMMDD (varchar).

    Args:
        days:       Número de días hacia atrás a considerar. Default: 90.
        store_code: Código de oficina de venta. Ej: 'SH01', 'ME10'.
        block_type: 'entrega' = solo con bloqueo de entrega,
                    'factura' = solo con bloqueo de facturación,
                    None = ambos.
        top_n:      Máximo de pedidos. Default: 30.
    """
    top_n = max(1, min(int(top_n), 100))
    days  = max(1, min(int(days), 365))

    # Fecha límite en formato YYYYMMDD (como está almacenada la columna)
    from datetime import timedelta
    fecha_desde = (datetime.now() - timedelta(days=days)).strftime("%Y%m%d")

    where_parts = [f"VC_fecha_creacion >= '{fecha_desde}'"]

    # Filtro de bloqueo
    if block_type == "entrega":
        where_parts.append(
            "VC_entrega_bloqueo IS NOT NULL AND LTRIM(RTRIM(VC_entrega_bloqueo)) != ''"
        )
    elif block_type == "factura":
        where_parts.append(
            "VC_factura_bloqueo IS NOT NULL AND LTRIM(RTRIM(VC_factura_bloqueo)) != ''"
        )
    else:
        where_parts.append(
            "(VC_entrega_bloqueo IS NOT NULL AND LTRIM(RTRIM(VC_entrega_bloqueo)) != '') "
            "OR (VC_factura_bloqueo IS NOT NULL AND LTRIM(RTRIM(VC_factura_bloqueo)) != '')"
        )

    if store_code:
        safe_s = store_code.replace("'", "''").upper()
        where_parts.append(f"VC_oficina_venta = '{safe_s}'")

    where_clause = "WHERE " + " AND ".join(f"({p})" for p in where_parts)

    rows = await punto_venta_sql.query_readonly(f"""
        SELECT TOP {top_n}
            VC_pedido_numero        AS pedido,
            VC_fecha_creacion       AS fecha_creacion,
            VC_entrega_bloqueo      AS bloqueo_entrega,
            VC_factura_bloqueo      AS bloqueo_factura,
            DE_pedido_valor_neto    AS valor_neto,
            VC_moneda               AS moneda,
            VC_oficina_venta        AS oficina_venta,
            VC_documento_pago_clase AS tipo_doc,
            VC_pedido_motivo        AS motivo
        FROM dbo.SD_PEDIDOS
        {where_clause}
        ORDER BY VC_fecha_creacion DESC
    """)

    total_valor = sum(float(r.get("valor_neto") or 0) for r in rows)

    return {
        "periodo_dias": days,
        "filtro_tienda": store_code,
        "filtro_bloqueo": block_type or "ambos",
        "total_pedidos_bloqueados": len(rows),
        "valor_total_bloqueado": round(total_valor, 2),
        "pedidos": [
            {
                "pedido": r.get("pedido"),
                "fecha_creacion": str(r.get("fecha_creacion") or ""),
                "bloqueo_entrega": (r.get("bloqueo_entrega") or "").strip() or None,
                "bloqueo_factura": (r.get("bloqueo_factura") or "").strip() or None,
                "valor_neto": round(float(r.get("valor_neto") or 0), 2),
                "moneda": r.get("moneda"),
                "oficina_venta": r.get("oficina_venta"),
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
