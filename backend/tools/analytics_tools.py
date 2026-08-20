# backend/tools/analytics_tools.py
"""
Herramientas analíticas avanzadas para el área de ventas.
Todas son read-only — ninguna modifica la BD.
"""
import logging
from typing import Dict, Any, Optional, List
from datetime import datetime, date

from connectors.sql_connector import azure_sql
from tools.utils import query_cache, NETO_SQL, AVG_NETO_SQL
from tools.material_utils import build_material_exclusion_clause

logger = logging.getLogger(__name__)


# ─────────────────────────────────────────────────────────────────────────────
# 1. get_gap_to_target — ¿Cuánto falta para llegar a la meta?
# ─────────────────────────────────────────────────────────────────────────────
async def get_gap_to_target(vendor_id: Optional[str] = None,
                             year: int = 2026,
                             month: Optional[int] = None) -> Dict[str, Any]:
    """
    Calcula la brecha entre la meta mensual y las ventas reales a la fecha.
    Incluye ritmo diario necesario para cerrar la brecha.

    Fuentes: SAP.WEB_FORECAST_VENTAS_REPORTE_ACTIVIDAD (meta) + SAP.SD_VENTAS
    """
    now = datetime.now()
    if month is None:
        month = now.month
    period_ym  = f"{year}{month:02d}"
    period_str = f"{year}-{month:02d}"

    # Meta de tienda — fuente: WEB_FORECAST escenario Base
    # (TB_FOLLOWUP_METAS devuelve montos ~56× menores a las ventas reales)
    store_id = "SH22"
    if vendor_id:
        safe_vid  = vendor_id.replace("'", "''")
        store_rows = await azure_sql.query_readonly(
            f"SELECT TOP 1 store_id FROM MT.TB_FOLLOWUP_VENDEDORES WHERE seller_id = '{safe_vid}'"
        )
        store_id = store_rows[0].get("store_id", "SH22") if store_rows else "SH22"

    forecast_rows = await azure_sql.query_readonly(f"""
        SELECT SUM(ImporteSoles) AS meta
        FROM SAP.WEB_FORECAST_VENTAS_REPORTE_ACTIVIDAD
        WHERE Anio = {year} AND MesNumero = {month}
    """)
    meta = float(forecast_rows[0].get("meta") or 0) if forecast_rows else 0.0

    # Ventas reales del período
    vendor_filter = ""
    if vendor_id:
        safe_vid = vendor_id.replace("'", "''")
        vendor_filter = f"AND VC_vendedor_codigo = '{safe_vid}'"
    else:
        v_rows = await azure_sql.query_readonly(
            f"SELECT seller_id FROM MT.TB_FOLLOWUP_VENDEDORES "
            f"WHERE store_id = '{safe_store}' AND seller_id IS NOT NULL"
        )
        if v_rows:
            ids = "','".join(r["seller_id"] for r in v_rows if r.get("seller_id"))
            vendor_filter = f"AND VC_vendedor_codigo IN ('{ids}')"

    actual_rows = await azure_sql.query_readonly(f"""
        SELECT SUM({NETO_SQL}) AS actual
        FROM SAP.SD_VENTAS
        WHERE IN_anio = {year} AND IN_mes = {month} {vendor_filter}
    """)
    actual = float(actual_rows[0].get("actual") or 0) if actual_rows else 0.0

    gap      = meta - actual
    pct      = round(actual / meta * 100, 1) if meta > 0 else 0.0

    # Días del mes y días restantes
    import calendar
    total_days    = calendar.monthrange(year, month)[1]
    today         = now.day if (year == now.year and month == now.month) else total_days
    days_left     = max(total_days - today, 0)
    daily_needed  = round(gap / days_left, 2) if days_left > 0 and gap > 0 else 0.0
    daily_current = round(actual / today, 2) if today > 0 else 0.0

    return {
        "period": period_str,
        "vendor_id": vendor_id or "ALL",
        "store_id": store_id,
        "meta": round(meta, 2),
        "actual": round(actual, 2),
        "gap": round(gap, 2),
        "pct_achievement": pct,
        "days_elapsed": today,
        "days_remaining": days_left,
        "daily_run_rate": daily_current,
        "daily_needed_to_close": daily_needed,
        "on_track": daily_current >= daily_needed if daily_needed > 0 else True,
        "timestamp": datetime.utcnow().isoformat(),
    }


# ─────────────────────────────────────────────────────────────────────────────
# 2. get_inactive_customers — Clientes sin compra reciente
# ─────────────────────────────────────────────────────────────────────────────
async def get_inactive_customers(days: int = 60,
                                  vendor_id: Optional[str] = None,
                                  region: Optional[str] = None,
                                  top_n: int = 20) -> Dict[str, Any]:
    """
    Lista clientes que no han comprado en los últimos N días.
    Útil para acciones de reactivación comercial.

    Fuente: SAP.SD_VENTAS
    """
    days = max(1, min(days, 365))

    where_parts = [f"VC_solicitante_codigo IS NOT NULL",
                   f"VC_solicitante_codigo != ''"]
    if vendor_id:
        safe_vid = vendor_id.replace("'", "''")
        where_parts.append(f"VC_vendedor_codigo = '{safe_vid}'")
    if region:
        safe_r = region.replace("'", "''")
        where_parts.append(f"VC_zona_ventas = '{safe_r}'")

    where_clause = "WHERE " + " AND ".join(where_parts)

    rows = await azure_sql.query_readonly(f"""
        SELECT TOP {top_n}
            VC_solicitante_codigo                               AS cliente_codigo,
            MAX(VC_solicitante_razon_social)                    AS cliente_nombre,
            MAX(DT_documento_pago_fecha)                        AS ultima_compra,
            DATEDIFF(day, MAX(DT_documento_pago_fecha), GETDATE()) AS dias_inactivo,
            COUNT(DISTINCT VC_documento_pago_numero)            AS total_pedidos_historicos,
            SUM({NETO_SQL})                                     AS total_historico
        FROM SAP.SD_VENTAS
        {where_clause}
        GROUP BY VC_solicitante_codigo
        HAVING DATEDIFF(day, MAX(DT_documento_pago_fecha), GETDATE()) >= {days}
        ORDER BY total_historico DESC
    """)

    return {
        "days_threshold": days,
        "vendor_filter": vendor_id,
        "region_filter": region,
        "total_inactive": len(rows),
        "customers": [
            {
                "codigo": r.get("cliente_codigo"),
                "nombre": r.get("cliente_nombre"),
                "ultima_compra": str(r.get("ultima_compra") or ""),
                "dias_inactivo": int(r.get("dias_inactivo") or 0),
                "pedidos_historicos": int(r.get("total_pedidos_historicos") or 0),
                "total_historico": round(float(r.get("total_historico") or 0), 2),
            }
            for r in rows
        ],
        "timestamp": datetime.utcnow().isoformat(),
    }


# ─────────────────────────────────────────────────────────────────────────────
# 3. get_sales_by_channel — Ventas por canal
# ─────────────────────────────────────────────────────────────────────────────
async def get_sales_by_channel(period: str,
                                region: Optional[str] = None) -> Dict[str, Any]:
    """
    Ventas agrupadas por canal de venta para un período dado.
    Usa WEB_FORECAST que tiene nombres de canal descriptivos.

    Fuente: SAP.WEB_FORECAST_VENTAS_REPORTE_ACTIVIDAD
    """
    # Parse period
    if "-" in period:
        year_s, month_s = period.split("-")
        where_period = f"Anio = {int(year_s)} AND MesNumero = {int(month_s)}"
    else:
        where_period = f"Anio = {int(period)}"

    where_region = ""
    if region:
        safe_r = region.replace("'", "''")
        where_region = f"AND REGION = '{safe_r}'"

    rows = await azure_sql.query_readonly(f"""
        SELECT
            Canal                                   AS canal,
            Codigo_Canal                            AS codigo_canal,
            SUM(ImporteSoles)                       AS ventas,
            SUM(UtilidadSoles)                      AS utilidad,
            COUNT(DISTINCT Documento)               AS documentos,
            COUNT(DISTINCT SolicitanteCodigo)       AS clientes,
            SUM(Cantidad)                           AS unidades
        FROM SAP.WEB_FORECAST_VENTAS_REPORTE_ACTIVIDAD
        WHERE {where_period} {where_region}
        GROUP BY Canal, Codigo_Canal
        ORDER BY ventas DESC
    """)

    total_ventas = sum(float(r.get("ventas") or 0) for r in rows)

    return {
        "period": period,
        "region": region or "Global",
        "total_ventas": round(total_ventas, 2),
        "canales": [
            {
                "canal": r.get("canal"),
                "codigo": r.get("codigo_canal"),
                "ventas": round(float(r.get("ventas") or 0), 2),
                "utilidad": round(float(r.get("utilidad") or 0), 2),
                "margen_pct": round(float(r.get("utilidad") or 0) /
                               float(r.get("ventas") or 1) * 100, 1),
                "participacion_pct": round(float(r.get("ventas") or 0) /
                                     total_ventas * 100, 1) if total_ventas else 0,
                "documentos": int(r.get("documentos") or 0),
                "clientes": int(r.get("clientes") or 0),
                "unidades": round(float(r.get("unidades") or 0), 0),
            }
            for r in rows
        ],
        "timestamp": datetime.utcnow().isoformat(),
    }


# ─────────────────────────────────────────────────────────────────────────────
# 4. get_monthly_trend — Tendencia de ventas (últimos N meses)
# ─────────────────────────────────────────────────────────────────────────────
async def get_monthly_trend(months: int = 6,
                             region: Optional[str] = None) -> Dict[str, Any]:
    """
    Tendencia mensual de ventas para los últimos N meses.
    Calcula crecimiento MoM y tendencia general.

    Fuente: SAP.WEB_FORECAST_VENTAS_REPORTE_ACTIVIDAD
    """
    months = max(2, min(months, 24))

    where_region = ""
    if region:
        safe_r = region.replace("'", "''")
        where_region = f"AND REGION = '{safe_r}'"

    # Excluir el mes en curso si estamos antes del día 25 (datos incompletos)
    now = datetime.now()
    if now.day < 25:
        exclude_current = (
            f"AND NOT (Anio = {now.year} AND MesNumero = {now.month})"
        )
    else:
        exclude_current = ""

    rows = await azure_sql.query_readonly(f"""
        SELECT TOP {months}
            Anio, MesNumero, MesNombre,
            SUM(ImporteSoles)           AS ventas,
            SUM(UtilidadSoles)          AS utilidad,
            COUNT(DISTINCT Documento)   AS documentos,
            COUNT(DISTINCT SolicitanteCodigo) AS clientes
        FROM SAP.WEB_FORECAST_VENTAS_REPORTE_ACTIVIDAD
        WHERE 1=1 {where_region} {exclude_current}
        GROUP BY Anio, MesNumero, MesNombre
        ORDER BY Anio DESC, MesNumero DESC
    """)

    # Reverse to chronological order
    rows = list(reversed(rows))

    periodos = []
    for i, r in enumerate(rows):
        ventas = float(r.get("ventas") or 0)
        mom_pct = None
        if i > 0:
            prev = float(rows[i-1].get("ventas") or 0)
            mom_pct = round((ventas - prev) / prev * 100, 1) if prev else None
        periodos.append({
            "periodo": f"{r['Anio']}-{int(r['MesNumero']):02d}",
            "mes_nombre": str(r.get("MesNombre", "")).capitalize(),
            "ventas": round(ventas, 2),
            "utilidad": round(float(r.get("utilidad") or 0), 2),
            "mom_pct": mom_pct,
            "documentos": int(r.get("documentos") or 0),
            "clientes": int(r.get("clientes") or 0),
        })

    # Tendencia general: comparar primer y último mes
    if len(periodos) >= 2:
        v_ini = periodos[0]["ventas"]
        v_fin = periodos[-1]["ventas"]
        tendencia = "↑ Creciente" if v_fin > v_ini * 1.02 else \
                    "↓ Decreciente" if v_fin < v_ini * 0.98 else \
                    "→ Estable"
        crecimiento_total = round((v_fin - v_ini) / v_ini * 100, 1) if v_ini else 0
    else:
        tendencia = "Sin datos suficientes"
        crecimiento_total = 0.0

    return {
        "months_analyzed": months,
        "region": region or "Global",
        "tendencia": tendencia,
        "crecimiento_pct": crecimiento_total,
        "promedio_mensual": round(
            sum(p["ventas"] for p in periodos) / len(periodos), 2
        ) if periodos else 0,
        "periodos": periodos,
        "timestamp": datetime.utcnow().isoformat(),
    }


# ─────────────────────────────────────────────────────────────────────────────
# 5. get_new_customers — Clientes nuevos en un período
# ─────────────────────────────────────────────────────────────────────────────
async def get_new_customers(period: str,
                             vendor_id: Optional[str] = None,
                             region: Optional[str] = None) -> Dict[str, Any]:
    """
    Clientes cuya primera compra histórica ocurrió en el período indicado.

    Fuente: SAP.SD_VENTAS
    """
    if "-" in period:
        year_s, month_s = period.split("-")
        where_period = f"IN_anio = {int(year_s)} AND IN_mes = {int(month_s)}"
    else:
        where_period = f"IN_anio = {int(period)}"

    vendor_filter = ""
    if vendor_id:
        safe_vid = vendor_id.replace("'", "''")
        vendor_filter = f"AND VC_vendedor_codigo = '{safe_vid}'"

    region_filter = ""
    if region:
        safe_r = region.replace("'", "''")
        region_filter = f"AND VC_zona_ventas = '{safe_r}'"

    rows = await azure_sql.query_readonly(f"""
        SELECT
            v.VC_solicitante_codigo          AS codigo,
            MAX(v.VC_solicitante_razon_social) AS nombre,
            MIN(v.DT_documento_pago_fecha)   AS primera_compra,
            SUM(CASE
                WHEN v.VC_documento_pago_clase IN ('ZPEF','ZPEB','ZNDV','ZEXP') THEN  v.DE_neto
                WHEN v.VC_documento_pago_clase IN ('ZNCV','ZNCD','S1','S2')     THEN -v.DE_neto
                ELSE 0 END)                  AS compra_inicial,
            COUNT(DISTINCT v.VC_documento_pago_numero) AS pedidos
        FROM SAP.SD_VENTAS v
        INNER JOIN (
            SELECT VC_solicitante_codigo,
                   MIN(DT_documento_pago_fecha) AS primera_fecha
            FROM SAP.SD_VENTAS
            WHERE VC_solicitante_codigo IS NOT NULL
            GROUP BY VC_solicitante_codigo
        ) primera ON v.VC_solicitante_codigo = primera.VC_solicitante_codigo
        WHERE {where_period}
          AND primera.primera_fecha >= (
              SELECT DATEFROMPARTS({period.split('-')[0] if '-' in period else period},
                                   {period.split('-')[1] if '-' in period else '1'}, 1)
          )
          {vendor_filter} {region_filter}
        GROUP BY v.VC_solicitante_codigo
        ORDER BY compra_inicial DESC
    """)

    return {
        "period": period,
        "vendor_filter": vendor_id,
        "region_filter": region,
        "total_new_customers": len(rows),
        "customers": [
            {
                "codigo": r.get("codigo"),
                "nombre": r.get("nombre"),
                "primera_compra": str(r.get("primera_compra") or ""),
                "compra_inicial": round(float(r.get("compra_inicial") or 0), 2),
                "pedidos": int(r.get("pedidos") or 0),
            }
            for r in rows
        ],
        "timestamp": datetime.utcnow().isoformat(),
    }


# ─────────────────────────────────────────────────────────────────────────────
# 6b. get_product_sales_ranking — Productos más o menos vendidos por período
# ─────────────────────────────────────────────────────────────────────────────
async def get_product_sales_ranking(
    period: Optional[str] = None,
    top_n: int = 10,
    sort_order: str = "DESC",          # "DESC" = más vendidos, "ASC" = menos vendidos
    category: Optional[str] = None,
    store_code: Optional[str] = None,  # Filtrar por tienda: 'SH01', 'ME10', etc.
) -> Dict[str, Any]:
    """
    Ranking de productos por ventas en soles para un período.

    - sort_order="DESC" → los más vendidos (mayor importe).
    - sort_order="ASC"  → los menos vendidos (menor importe en el período).

    Fuente: SAP.WEB_FORECAST_VENTAS_REPORTE_ACTIVIDAD
    """
    safe_order = "DESC" if sort_order.upper() != "ASC" else "ASC"
    top_n = max(1, min(int(top_n), 100))

    where_parts = ["ImporteSoles IS NOT NULL", "MaterialCodigo IS NOT NULL", "MaterialCodigo != ''"]

    if period:
        if "-" in period:
            year_s, month_s = period.split("-")
            where_parts.append(f"Anio = {int(year_s)} AND MesNumero = {int(month_s)}")
        else:
            where_parts.append(f"Anio = {int(period)}")

    if category:
        safe_cat = category.replace("'", "''")
        where_parts.append(f"GrupoMaterialDirectorio = '{safe_cat}'")

    if store_code:
        safe_store = store_code.replace("'", "''").upper()
        where_parts.append(f"Codigo_OficinaVta = '{safe_store}'")

    # Excluir materiales de tipo servicio si PUNTO_VENTA está disponible
    excl_clause = await build_material_exclusion_clause(material_col="MaterialCodigo")
    if excl_clause:
        where_parts.append(excl_clause.lstrip("AND "))

    where_clause = "WHERE " + " AND ".join(where_parts)

    # Para menos vendido: sin filtro mínimo de documentos para capturar
    # productos que solo se vendieron una vez en el período.
    rows = await azure_sql.query_readonly(f"""
        SELECT TOP {top_n}
            MaterialCodigo                          AS codigo,
            MaterialNombre                          AS nombre,
            GrupoMaterialDirectorio                 AS categoria,
            SUM(ImporteSoles)                       AS ventas,
            SUM(Cantidad)                           AS unidades,
            SUM(UtilidadSoles)                      AS utilidad,
            COUNT(DISTINCT Documento)               AS documentos,
            COUNT(DISTINCT SolicitanteCodigo)       AS clientes
        FROM SAP.WEB_FORECAST_VENTAS_REPORTE_ACTIVIDAD
        {where_clause}
        GROUP BY MaterialCodigo, MaterialNombre, GrupoMaterialDirectorio
        ORDER BY ventas {safe_order}
    """)

    label = "menos vendidos" if safe_order == "ASC" else "más vendidos"

    return {
        "period": period or "YTD",
        "sort_order": safe_order,
        "label": label,
        "top_n": top_n,
        "category_filter": category,
        "store_filter": store_code,
        "products": [
            {
                "rank": i + 1,
                "codigo": r.get("codigo"),
                "nombre": r.get("nombre"),
                "categoria": r.get("categoria"),
                "ventas": round(float(r.get("ventas") or 0), 2),
                "unidades": round(float(r.get("unidades") or 0), 0),
                "utilidad": round(float(r.get("utilidad") or 0), 2),
                "margen_pct": round(
                    float(r.get("utilidad") or 0) / float(r.get("ventas") or 1) * 100, 1
                ),
                "documentos": int(r.get("documentos") or 0),
                "clientes": int(r.get("clientes") or 0),
            }
            for i, r in enumerate(rows)
        ],
        "timestamp": datetime.utcnow().isoformat(),
    }


# ─────────────────────────────────────────────────────────────────────────────
# 6. get_top_margin_products — Productos con mejor margen
# ─────────────────────────────────────────────────────────────────────────────
async def get_top_margin_products(period: Optional[str] = None,
                                   top_n: int = 10,
                                   category: Optional[str] = None,
                                   store_code: Optional[str] = None) -> Dict[str, Any]:
    """
    Top productos por margen de utilidad real.
    Mínimo 5 documentos para filtrar outliers.

    Fuente: SAP.WEB_FORECAST_VENTAS_REPORTE_ACTIVIDAD
    """
    where_parts = ["MargenRealPorcentaje IS NOT NULL", "ImporteSoles > 0"]

    if period:
        if "-" in period:
            year_s, month_s = period.split("-")
            where_parts.append(f"Anio = {int(year_s)} AND MesNumero = {int(month_s)}")
        else:
            where_parts.append(f"Anio = {int(period)}")

    if category:
        safe_cat = category.replace("'", "''")
        where_parts.append(f"GrupoMaterialDirectorio = '{safe_cat}'")

    if store_code:
        safe_store = store_code.replace("'", "''").upper()
        where_parts.append(f"Codigo_OficinaVta = '{safe_store}'")

    # Excluir servicios si PUNTO_VENTA disponible
    excl_clause = await build_material_exclusion_clause(material_col="MaterialCodigo")
    if excl_clause:
        where_parts.append(excl_clause.lstrip("AND "))

    where_clause = "WHERE " + " AND ".join(where_parts)

    rows = await azure_sql.query_readonly(f"""
        SELECT TOP {top_n}
            MaterialCodigo                          AS codigo,
            MaterialNombre                          AS nombre,
            GrupoMaterialDirectorio                 AS categoria,
            SUM(ImporteSoles)                       AS ventas,
            SUM(UtilidadSoles)                      AS utilidad,
            AVG(MargenRealPorcentaje)               AS margen_promedio,
            SUM(Cantidad)                           AS unidades,
            COUNT(DISTINCT Documento)               AS documentos
        FROM SAP.WEB_FORECAST_VENTAS_REPORTE_ACTIVIDAD
        {where_clause}
        GROUP BY MaterialCodigo, MaterialNombre, GrupoMaterialDirectorio
        HAVING COUNT(DISTINCT Documento) >= 5
        ORDER BY margen_promedio DESC
    """)

    return {
        "period": period or "YTD",
        "category_filter": category,
        "products": [
            {
                "codigo": r.get("codigo"),
                "nombre": r.get("nombre"),
                "categoria": r.get("categoria"),
                "ventas": round(float(r.get("ventas") or 0), 2),
                "utilidad": round(float(r.get("utilidad") or 0), 2),
                "margen_pct": round(float(r.get("margen_promedio") or 0), 1),
                "unidades": round(float(r.get("unidades") or 0), 0),
                "documentos": int(r.get("documentos") or 0),
            }
            for r in rows
        ],
        "timestamp": datetime.utcnow().isoformat(),
    }


# ─────────────────────────────────────────────────────────────────────────────
# 8. get_vendor_performance_vs_target — Cumplimiento por vendedor
# ─────────────────────────────────────────────────────────────────────────────
async def get_vendor_performance_vs_target(
    year: int = 2026,
    month: Optional[int] = None,
    store_id: Optional[str] = None,
    top_n: int = 20,
) -> Dict[str, Any]:
    """
    Cumplimiento de ventas por vendedor: ventas reales vs meta estimada.

    ⚠️ Las metas individuales no existen en el sistema — se estiman distribuyendo
    la meta de tienda proporcionalmente al share histórico de cada vendedor
    (ventas del mes anterior). Si no hay datos del mes anterior, se distribuye
    en partes iguales entre todos los vendedores activos del período.

    Fuentes:
      - SAP.WEB_FORECAST_VENTAS_REPORTE_ACTIVIDAD (meta total de tienda, escenario base)
      - SAP.SD_VENTAS (ventas reales + share histórico mes anterior)

    Args:
        year:     Año. Default: 2026.
        month:    Mes (1-12). Default: mes actual.
        store_id: Código de tienda (ej: 'SH22'). Default: SH22.
        top_n:    Número máximo de vendedores. Default: 20.
    """
    from calendar import monthrange

    now = datetime.now()
    if month is None:
        month = now.month

    top_n = max(1, min(int(top_n), 50))
    period_ym  = f"{year}{month:02d}"
    period_str = f"{year}-{month:02d}"

    # Mes anterior (share histórico para distribuir la meta)
    prev_month = month - 1 if month > 1 else 12
    prev_year  = year if month > 1 else year - 1

    # ── 1. Meta total del período (fuente: WEB_FORECAST escenario Base) ───────
    #
    # TB_FOLLOWUP_METAS NO contiene las metas de ventas en soles — devuelve
    # montos ~56× menores a las ventas reales (probablemente otra métrica).
    # La fuente correcta es WEB_FORECAST_VENTAS_REPORTE_ACTIVIDAD, cuyo
    # escenario "Base" (promedio de los 3 últimos meses) sí corresponde al
    # nivel de ventas real del negocio (~S/ 28-33M para ago 2026).

    forecast_rows = await azure_sql.query_readonly(f"""
        SELECT SUM(ImporteSoles) AS meta_base
        FROM SAP.WEB_FORECAST_VENTAS_REPORTE_ACTIVIDAD
        WHERE Anio = {year} AND MesNumero = {month}
    """)
    meta_forecast = float(forecast_rows[0].get("meta_base") or 0) if forecast_rows else 0.0

    # Fallback a TB_FOLLOWUP_METAS si el forecast no tiene datos
    meta_tienda = meta_forecast
    fuente_meta = "WEB_FORECAST_VENTAS (escenario base)"
    if meta_tienda <= 0:
        sid = (store_id or "SH22").replace("'", "''")
        meta_rows = await azure_sql.query_readonly(f"""
            SELECT MAX(amount) AS meta
            FROM MT.TB_FOLLOWUP_METAS
            WHERE store_id = '{sid}' AND LEFT(date, 6) = '{period_ym}'
        """)
        meta_tienda = float(meta_rows[0].get("meta") or 0) if meta_rows else 0.0
        fuente_meta = f"TB_FOLLOWUP_METAS (tienda {store_id or 'SH22'})"

    # ── 2. Ventas reales del período ─────────────────────────────────────────
    actual_rows = await azure_sql.query_readonly(f"""
        SELECT TOP {top_n}
            VC_vendedor_codigo   AS codigo,
            MAX(VC_vendedor_nombre) AS nombre,
            SUM({NETO_SQL})      AS ventas,
            COUNT(DISTINCT VC_documento_pago_numero) AS pedidos,
            COUNT(DISTINCT VC_solicitante_codigo)    AS clientes
        FROM SAP.SD_VENTAS
        WHERE IN_anio = {year} AND IN_mes = {month}
          AND VC_vendedor_codigo IS NOT NULL
        GROUP BY VC_vendedor_codigo
        ORDER BY ventas DESC
    """)

    total_actual = sum(float(r.get("ventas") or 0) for r in actual_rows)

    # ── 3. Share histórico del mes anterior para distribuir la meta ──────────
    prev_rows = await azure_sql.query_readonly(f"""
        SELECT VC_vendedor_codigo AS codigo, SUM({NETO_SQL}) AS ventas_prev
        FROM SAP.SD_VENTAS
        WHERE IN_anio = {prev_year} AND IN_mes = {prev_month}
          AND VC_vendedor_codigo IS NOT NULL
        GROUP BY VC_vendedor_codigo
    """)
    prev_map   = {r["codigo"]: float(r.get("ventas_prev") or 0) for r in prev_rows}
    total_prev = sum(prev_map.values()) or 0
    n_activos  = max(len(actual_rows), 1)

    def _meta_estimada(codigo: str) -> float:
        if meta_tienda <= 0:
            return 0.0
        share = (prev_map.get(codigo, 0) / total_prev) if total_prev > 0 else (1.0 / n_activos)
        return meta_tienda * share

    # ── 4. Armar resultado por vendedor ──────────────────────────────────────
    vendedores = []
    for r in actual_rows:
        codigo = r.get("codigo") or ""
        ventas = float(r.get("ventas") or 0)
        meta_v = _meta_estimada(codigo)
        cumpl  = round(ventas / meta_v * 100, 1) if meta_v > 0 else None
        gap    = round(meta_v - ventas, 2) if meta_v > 0 else None

        vendedores.append({
            "vendedor_codigo":  codigo,
            "vendedor_nombre":  (r.get("nombre") or "").strip(),
            "ventas_actuales":  round(ventas, 2),
            "meta_estimada":    round(meta_v, 2),
            "cumplimiento_pct": cumpl,
            "gap_soles":        gap,
            "en_meta":          (cumpl or 0) >= 100,
            "pedidos":          int(r.get("pedidos") or 0),
            "clientes":         int(r.get("clientes") or 0),
        })

    # ── 5. Proyección de cierre del mes ──────────────────────────────────────
    dias_mes       = monthrange(year, month)[1]
    dias_hoy       = now.day if (year == now.year and month == now.month) else dias_mes
    dias_restantes = max(0, dias_mes - dias_hoy)
    ritmo_diario   = total_actual / max(dias_hoy, 1)
    proyeccion     = total_actual + ritmo_diario * dias_restantes

    return {
        "period":                  period_str,
        "meta_total":              round(meta_tienda, 2),
        "fuente_meta":             fuente_meta,
        "ventas_reales_total":     round(total_actual, 2),
        "cumplimiento_total_pct":  round(total_actual / meta_tienda * 100, 1) if meta_tienda > 0 else None,
        "proyeccion_cierre_mes":   round(proyeccion, 2),
        "dias_restantes":          dias_restantes,
        "share_base":              f"{prev_year}-{prev_month:02d}",
        "nota_metodologia": (
            f"⚠️ Meta total obtenida de: {fuente_meta}. "
            "Metas individuales ESTIMADAS: se distribuyó proporcionalmente según "
            f"el share de ventas de {prev_year}-{prev_month:02d}. "
            "No son cuotas oficiales. Para cuotas reales, cargarlas en el sistema."
        ),
        "vendedores": vendedores,
        "timestamp":  datetime.utcnow().isoformat(),
    }


# ─────────────────────────────────────────────────────────────────────────────
# 9. get_discount_analysis — Descuentos otorgados por vendedor o cliente
# ─────────────────────────────────────────────────────────────────────────────
async def get_discount_analysis(
    period: Optional[str] = None,
    vendor_id: Optional[str] = None,
    customer_id: Optional[str] = None,
    top_n: int = 20,
    group_by: str = "vendedor",   # "vendedor" | "cliente"
) -> Dict[str, Any]:
    """
    Analiza descuentos comerciales otorgados en ventas reales.

    Fórmula: descuento_pct = SUM(DE_descuento) / SUM(DE_bruto) * 100
    Solo documentos ZPEF/ZPEB/ZNDV/ZEXP (ventas reales, sin notas de crédito).

    Fuente: SAP.SD_VENTAS (DE_bruto, DE_descuento, DE_neto)
    """
    top_n  = max(1, min(int(top_n), 100))
    now    = datetime.now()

    where_parts = [
        "VC_documento_pago_clase IN ('ZPEF','ZPEB','ZNDV','ZEXP')",
        "DE_bruto IS NOT NULL",
        "DE_bruto > 0",
    ]

    if period:
        if "-" in period:
            y, m = period.split("-")
            where_parts.append(f"IN_anio = {int(y)} AND IN_mes = {int(m)}")
        else:
            where_parts.append(f"IN_anio = {int(period)}")
    else:
        where_parts.append(f"IN_anio = {now.year} AND IN_mes = {now.month}")

    if vendor_id:
        sv = vendor_id.replace("'", "''")
        where_parts.append(f"VC_vendedor_codigo = '{sv}'")

    if customer_id:
        sc = customer_id.replace("'", "''")
        where_parts.append(f"VC_solicitante_codigo = '{sc}'")

    safe_group = "cliente" if group_by.lower() == "cliente" else "vendedor"
    group_col  = "VC_solicitante_codigo" if safe_group == "cliente" else "VC_vendedor_codigo"
    name_col   = ("MAX(VC_solicitante_razon_social)" if safe_group == "cliente"
                  else "MAX(VC_vendedor_nombre)")

    where_clause = "WHERE " + " AND ".join(where_parts) + f" AND {group_col} IS NOT NULL"

    rows = await azure_sql.query_readonly(f"""
        SELECT TOP {top_n}
            {group_col}                                              AS codigo,
            {name_col}                                               AS nombre,
            SUM(DE_bruto)                                            AS bruto_total,
            SUM(DE_descuento)                                        AS descuento_total,
            SUM(DE_neto)                                             AS neto_total,
            SUM(DE_descuento) / NULLIF(SUM(DE_bruto), 0) * 100      AS descuento_pct,
            COUNT(DISTINCT VC_documento_pago_numero)                 AS documentos
        FROM SAP.SD_VENTAS
        {where_clause}
        GROUP BY {group_col}
        HAVING SUM(DE_bruto) > 0
        ORDER BY descuento_pct DESC
    """)

    total_bruto     = sum(float(r.get("bruto_total")     or 0) for r in rows)
    total_descuento = sum(float(r.get("descuento_total") or 0) for r in rows)

    return {
        "period":            period or f"{now.year}-{now.month:02d}",
        "group_by":          safe_group,
        "vendor_filter":     vendor_id,
        "customer_filter":   customer_id,
        "total_bruto":       round(total_bruto, 2),
        "total_descuento":   round(total_descuento, 2),
        "descuento_pct_global": round(total_descuento / total_bruto * 100, 2) if total_bruto else 0.0,
        "items": [
            {
                "codigo":           r.get("codigo"),
                "nombre":           (r.get("nombre") or "").strip(),
                "bruto_soles":      round(float(r.get("bruto_total")     or 0), 2),
                "descuento_soles":  round(float(r.get("descuento_total") or 0), 2),
                "neto_soles":       round(float(r.get("neto_total")      or 0), 2),
                "descuento_pct":    round(float(r.get("descuento_pct")   or 0), 2),
                "documentos":       int(r.get("documentos") or 0),
            }
            for r in rows
        ],
        "timestamp": datetime.utcnow().isoformat(),
    }


# ─────────────────────────────────────────────────────────────────────────────
# 10. get_real_margin — Margen real (DE_costo_real) por vendedor/categoría/producto
# ─────────────────────────────────────────────────────────────────────────────
async def get_real_margin(
    period: Optional[str] = None,
    vendor_id: Optional[str] = None,
    category: Optional[str] = None,
    top_n: int = 20,
    group_by: str = "vendedor",   # "vendedor" | "categoria" | "producto"
) -> Dict[str, Any]:
    """
    Margen real de contribución usando el costo real de SAP (DE_costo_real).
    Más preciso que WEB_FORECAST porque opera a nivel de línea de factura.

    Solo líneas con DE_costo_real > 0 y clases de venta real (ZPEF/ZPEB/ZNDV/ZEXP).
    Fuente: SAP.SD_VENTAS
    """
    top_n = max(1, min(int(top_n), 100))
    now   = datetime.now()

    where_parts = [
        "VC_documento_pago_clase IN ('ZPEF','ZPEB','ZNDV','ZEXP')",
        "DE_costo_real IS NOT NULL",
        "DE_costo_real > 0",
        "DE_neto > 0",
    ]

    if period:
        if "-" in period:
            y, m = period.split("-")
            where_parts.append(f"IN_anio = {int(y)} AND IN_mes = {int(m)}")
        else:
            where_parts.append(f"IN_anio = {int(period)}")
    else:
        where_parts.append(f"IN_anio = {now.year} AND IN_mes = {now.month}")

    if vendor_id:
        sv = vendor_id.replace("'", "''")
        where_parts.append(f"VC_vendedor_codigo = '{sv}'")

    if category:
        sc = category.replace("'", "''")
        where_parts.append(f"VC_grupo_material_directorio_vainsa_1 = '{sc}'")

    safe_group = group_by.lower()
    if safe_group not in ("vendedor", "categoria", "producto"):
        safe_group = "vendedor"

    _COL = {
        "vendedor":  ("VC_vendedor_codigo",                   "MAX(VC_vendedor_nombre)"),
        "categoria": ("VC_grupo_material_directorio_vainsa_1","MAX(VC_grupo_material_directorio_vainsa_1)"),
        "producto":  ("VC_material_codigo",                   "MAX(VC_material_descripcion)"),
    }
    group_col, name_col = _COL[safe_group]

    where_clause = "WHERE " + " AND ".join(where_parts) + f" AND {group_col} IS NOT NULL"

    rows = await azure_sql.query_readonly(f"""
        SELECT TOP {top_n}
            {group_col}                                                      AS codigo,
            {name_col}                                                       AS nombre,
            SUM(DE_neto)                                                     AS ventas_netas,
            SUM(DE_costo_real)                                               AS costo_total,
            SUM(DE_neto - DE_costo_real)                                     AS margen_soles,
            SUM(DE_neto - DE_costo_real) / NULLIF(SUM(DE_neto), 0) * 100    AS margen_pct,
            SUM(DE_cantidad)                                                 AS unidades,
            COUNT(DISTINCT VC_documento_pago_numero)                         AS documentos
        FROM SAP.SD_VENTAS
        {where_clause}
        GROUP BY {group_col}
        ORDER BY margen_pct DESC
    """)

    total_v = sum(float(r.get("ventas_netas") or 0) for r in rows)
    total_c = sum(float(r.get("costo_total")  or 0) for r in rows)
    total_m = sum(float(r.get("margen_soles") or 0) for r in rows)

    return {
        "period":              period or f"{now.year}-{now.month:02d}",
        "group_by":            safe_group,
        "vendor_filter":       vendor_id,
        "category_filter":     category,
        "total_ventas_netas":  round(total_v, 2),
        "total_costo":         round(total_c, 2),
        "total_margen_soles":  round(total_m, 2),
        "margen_pct_global":   round(total_m / total_v * 100, 2) if total_v else 0.0,
        "nota": (
            "Solo líneas con costo real registrado y clase de venta real. "
            "Líneas sin DE_costo_real quedan excluidas del cálculo."
        ),
        "items": [
            {
                "codigo":        r.get("codigo"),
                "nombre":        (r.get("nombre") or "").strip(),
                "ventas_netas":  round(float(r.get("ventas_netas") or 0), 2),
                "costo_total":   round(float(r.get("costo_total")  or 0), 2),
                "margen_soles":  round(float(r.get("margen_soles") or 0), 2),
                "margen_pct":    round(float(r.get("margen_pct")   or 0), 2),
                "unidades":      round(float(r.get("unidades")     or 0), 0),
                "documentos":    int(r.get("documentos") or 0),
            }
            for r in rows
        ],
        "timestamp": datetime.utcnow().isoformat(),
    }


# ─────────────────────────────────────────────────────────────────────────────
# 11. get_sales_by_geography — Ventas por departamento/provincia/distrito
# ─────────────────────────────────────────────────────────────────────────────
async def get_sales_by_geography(
    period: Optional[str] = None,
    level: str = "departamento",  # "departamento" | "provincia" | "distrito"
    top_n: int = 20,
) -> Dict[str, Any]:
    """
    Distribución de ventas netas por ubicación geográfica del cliente.
    Usa la dirección registrada en SAP para el solicitante.

    Fuente: SAP.SD_VENTAS (VC_solicitante_departamento/provincia/distrito)
    """
    top_n      = max(1, min(int(top_n), 100))
    now        = datetime.now()
    safe_level = level.lower()
    if safe_level not in ("departamento", "provincia", "distrito"):
        safe_level = "departamento"

    level_col = {
        "departamento": "VC_solicitante_departamento",
        "provincia":    "VC_solicitante_provincia",
        "distrito":     "VC_solicitante_distrito",
    }[safe_level]

    where_parts = [f"{level_col} IS NOT NULL", f"{level_col} != ''"]

    if period:
        if "-" in period:
            y, m = period.split("-")
            where_parts.append(f"IN_anio = {int(y)} AND IN_mes = {int(m)}")
        else:
            where_parts.append(f"IN_anio = {int(period)}")
    else:
        where_parts.append(f"IN_anio = {now.year} AND IN_mes = {now.month}")

    where_clause = "WHERE " + " AND ".join(where_parts)

    rows = await azure_sql.query_readonly(f"""
        SELECT TOP {top_n}
            {level_col}                              AS region,
            SUM({NETO_SQL})                          AS ventas_netas,
            COUNT(DISTINCT VC_solicitante_codigo)    AS clientes,
            COUNT(DISTINCT VC_documento_pago_numero) AS documentos,
            SUM(DE_cantidad)                         AS unidades
        FROM SAP.SD_VENTAS
        {where_clause}
        GROUP BY {level_col}
        HAVING SUM({NETO_SQL}) > 0
        ORDER BY ventas_netas DESC
    """)

    total = sum(float(r.get("ventas_netas") or 0) for r in rows)

    return {
        "period":        period or f"{now.year}-{now.month:02d}",
        "level":         safe_level,
        "total_ventas":  round(total, 2),
        "regiones": [
            {
                "region":            (r.get("region") or "(Sin dato)").strip(),
                "ventas_netas":      round(float(r.get("ventas_netas") or 0), 2),
                "participacion_pct": round(float(r.get("ventas_netas") or 0) / total * 100, 1) if total else 0,
                "clientes":          int(r.get("clientes")   or 0),
                "documentos":        int(r.get("documentos") or 0),
                "unidades":          round(float(r.get("unidades") or 0), 0),
            }
            for r in rows
        ],
        "timestamp": datetime.utcnow().isoformat(),
    }


# ─────────────────────────────────────────────────────────────────────────────
# 12. get_customer_pareto — Análisis Pareto 80/20 de clientes
# ─────────────────────────────────────────────────────────────────────────────
async def get_customer_pareto(
    period: Optional[str] = None,
    top_n: int = 50,
    vendor_id: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Identifica qué porcentaje de clientes genera el 80% de las ventas (Pareto).

    Clasifica en:
      Clase A — clientes que acumulan hasta el 80% del total (los vitales)
      Clase B — del 80% al 95% acumulado
      Clase C — del 95% al 100% (los triviales)

    Fuente: SAP.SD_VENTAS
    """
    top_n = max(10, min(int(top_n), 200))
    now   = datetime.now()

    where_parts = ["VC_solicitante_codigo IS NOT NULL"]

    if period:
        if "-" in period:
            y, m = period.split("-")
            where_parts.append(f"IN_anio = {int(y)} AND IN_mes = {int(m)}")
        else:
            where_parts.append(f"IN_anio = {int(period)}")
    else:
        where_parts.append(f"IN_anio = {now.year} AND IN_mes = {now.month}")

    if vendor_id:
        sv = vendor_id.replace("'", "''")
        where_parts.append(f"VC_vendedor_codigo = '{sv}'")

    where_clause = "WHERE " + " AND ".join(where_parts)

    # Total del universo
    total_rows = await azure_sql.query_readonly(f"""
        SELECT SUM({NETO_SQL})                        AS total_ventas,
               COUNT(DISTINCT VC_solicitante_codigo)  AS total_clientes
        FROM SAP.SD_VENTAS
        {where_clause}
    """)
    total_v   = float(total_rows[0].get("total_ventas")   or 0) if total_rows else 0.0
    total_cli = int(total_rows[0].get("total_clientes")   or 0) if total_rows else 0

    # Ranking de clientes (top_n más grandes)
    rows = await azure_sql.query_readonly(f"""
        SELECT TOP {top_n}
            VC_solicitante_codigo                    AS codigo,
            MAX(VC_solicitante_razon_social)         AS nombre,
            SUM({NETO_SQL})                          AS ventas_netas,
            COUNT(DISTINCT VC_documento_pago_numero) AS pedidos,
            MAX(DT_documento_pago_fecha)             AS ultima_compra
        FROM SAP.SD_VENTAS
        {where_clause}
        GROUP BY VC_solicitante_codigo
        HAVING SUM({NETO_SQL}) > 0
        ORDER BY ventas_netas DESC
    """)

    # Calcular % acumulado y clasificar
    clientes = []
    cumsum   = 0.0
    for i, r in enumerate(rows, 1):
        v       = float(r.get("ventas_netas") or 0)
        cumsum += v
        cum_pct  = round(cumsum / total_v * 100, 1) if total_v else 0.0
        part_pct = round(v / total_v * 100, 2) if total_v else 0.0
        clase    = "A" if cum_pct <= 80 else ("B" if cum_pct <= 95 else "C")

        clientes.append({
            "rank":             i,
            "codigo":           r.get("codigo"),
            "nombre":           (r.get("nombre") or "").strip(),
            "ventas_netas":     round(v, 2),
            "participacion_pct": part_pct,
            "acumulado_pct":    cum_pct,
            "clase_pareto":     clase,
            "pedidos":          int(r.get("pedidos") or 0),
            "ultima_compra":    str(r.get("ultima_compra") or ""),
        })

    por_clase = {
        cls: [c for c in clientes if c["clase_pareto"] == cls]
        for cls in ("A", "B", "C")
    }

    return {
        "period":                  period or f"{now.year}-{now.month:02d}",
        "vendor_filter":           vendor_id,
        "total_ventas":            round(total_v, 2),
        "total_clientes_universo": total_cli,
        "top_n_analizado":         len(clientes),
        "concentracion": {
            cls: {
                "descripcion": {
                    "A": "Clientes que generan el primer 80% de ventas",
                    "B": "Clientes que generan del 80% al 95% acumulado",
                    "C": "Clientes del 95% al 100% (long tail)",
                }[cls],
                "cantidad_en_top": len(por_clase[cls]),
                "pct_del_total_clientes": (
                    round(len(por_clase[cls]) / total_cli * 100, 1) if total_cli else 0
                ),
            }
            for cls in ("A", "B", "C")
        },
        "clientes": clientes,
        "timestamp": datetime.utcnow().isoformat(),
    }
