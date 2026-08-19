# backend/tools/store_tools.py
"""
Herramientas de análisis por tienda/oficina de venta.

Las oficinas de venta en SOLE/MT Industrial se identifican por
Codigo_OficinaVta (ej: 'SH01', 'ME10') y el nombre OficinaVenta.

Fuente principal: SAP.WEB_FORECAST_VENTAS_REPORTE_ACTIVIDAD
"""
import logging
from typing import Dict, Any, Optional, List
from datetime import datetime

from connectors.sql_connector import azure_sql

logger = logging.getLogger(__name__)


# ─────────────────────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────────────────────

def _period_where(period: Optional[str]) -> str:
    """Convierte '2026-07' → WHERE clause Anio/MesNumero."""
    if not period:
        return ""
    if "-" in period:
        y, m = period.split("-")
        return f"AND Anio = {int(y)} AND MesNumero = {int(m)}"
    return f"AND Anio = {int(period)}"


def _store_where(store_code: Optional[str]) -> str:
    """Filtra por código de oficina de venta."""
    if not store_code:
        return ""
    safe = store_code.replace("'", "''").upper()
    return f"AND Codigo_OficinaVta = '{safe}'"


# ─────────────────────────────────────────────────────────────────────────────
# 1. get_sales_by_store — Ranking de tiendas por ventas
# ─────────────────────────────────────────────────────────────────────────────
async def get_sales_by_store(
    period: Optional[str] = None,
    top_n: int = 20,
) -> Dict[str, Any]:
    """
    Ranking de todas las tiendas/oficinas de venta ordenadas por ventas.
    Incluye ventas, utilidad, margen, documentos y clientes por tienda.

    Args:
        period:  Período a consultar (YYYY o YYYY-MM). Sin valor = acumulado anual.
        top_n:   Número máximo de tiendas a retornar.

    Fuente: SAP.WEB_FORECAST_VENTAS_REPORTE_ACTIVIDAD
    """
    top_n = max(1, min(int(top_n), 50))
    period_filter = _period_where(period)

    rows = await azure_sql.query_readonly(f"""
        SELECT TOP {top_n}
            Codigo_OficinaVta                       AS codigo,
            OficinaVenta                            AS nombre,
            SUM(ImporteSoles)                       AS ventas,
            SUM(UtilidadSoles)                      AS utilidad,
            AVG(MargenRealPorcentaje)               AS margen_pct,
            COUNT(DISTINCT Documento)               AS documentos,
            COUNT(DISTINCT SolicitanteCodigo)       AS clientes,
            SUM(Cantidad)                           AS unidades
        FROM SAP.WEB_FORECAST_VENTAS_REPORTE_ACTIVIDAD
        WHERE Codigo_OficinaVta IS NOT NULL
          AND ImporteSoles > 0
          {period_filter}
        GROUP BY Codigo_OficinaVta, OficinaVenta
        ORDER BY ventas DESC
    """)

    total_ventas = sum(float(r.get("ventas") or 0) for r in rows)

    return {
        "period": period or "YTD",
        "total_tiendas": len(rows),
        "total_ventas": round(total_ventas, 2),
        "tiendas": [
            {
                "rank": i + 1,
                "codigo": r.get("codigo"),
                "nombre": r.get("nombre"),
                "ventas": round(float(r.get("ventas") or 0), 2),
                "utilidad": round(float(r.get("utilidad") or 0), 2),
                "margen_pct": round(float(r.get("margen_pct") or 0), 1),
                "participacion_pct": round(
                    float(r.get("ventas") or 0) / total_ventas * 100, 1
                ) if total_ventas else 0,
                "documentos": int(r.get("documentos") or 0),
                "clientes": int(r.get("clientes") or 0),
                "unidades": round(float(r.get("unidades") or 0), 0),
            }
            for i, r in enumerate(rows)
        ],
        "timestamp": datetime.utcnow().isoformat(),
    }


# ─────────────────────────────────────────────────────────────────────────────
# 2. get_store_detail — Detalle de una tienda específica
# ─────────────────────────────────────────────────────────────────────────────
async def get_store_detail(
    store_code: str,
    period: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Análisis detallado de una tienda: ventas totales, top productos,
    top clientes y tendencia mensual.

    Args:
        store_code: Código de oficina de venta (ej: 'SH01', 'ME10', 'SH12').
        period:     Período YYYY o YYYY-MM. Sin valor = año actual.

    Fuente: SAP.WEB_FORECAST_VENTAS_REPORTE_ACTIVIDAD
    """
    safe_code = store_code.replace("'", "''").upper()
    now = datetime.now()
    period_filter = _period_where(period) if period else f"AND Anio = {now.year}"

    # Resumen general de la tienda
    summary_rows = await azure_sql.query_readonly(f"""
        SELECT
            Codigo_OficinaVta                       AS codigo,
            MAX(OficinaVenta)                       AS nombre,
            SUM(ImporteSoles)                       AS ventas,
            SUM(UtilidadSoles)                      AS utilidad,
            AVG(MargenRealPorcentaje)               AS margen_pct,
            COUNT(DISTINCT Documento)               AS documentos,
            COUNT(DISTINCT SolicitanteCodigo)       AS clientes,
            SUM(Cantidad)                           AS unidades
        FROM SAP.WEB_FORECAST_VENTAS_REPORTE_ACTIVIDAD
        WHERE Codigo_OficinaVta = '{safe_code}'
          AND ImporteSoles > 0
          {period_filter}
        GROUP BY Codigo_OficinaVta
    """)

    if not summary_rows:
        return {
            "store_code": store_code,
            "error": f"No se encontró la tienda '{store_code}' o no tiene ventas en el período.",
            "period": period or "YTD",
        }

    s = summary_rows[0]

    # Top 5 productos de la tienda
    top_products = await azure_sql.query_readonly(f"""
        SELECT TOP 5
            MaterialCodigo  AS codigo,
            MaterialNombre  AS nombre,
            SUM(ImporteSoles) AS ventas,
            SUM(Cantidad)   AS unidades
        FROM SAP.WEB_FORECAST_VENTAS_REPORTE_ACTIVIDAD
        WHERE Codigo_OficinaVta = '{safe_code}'
          AND ImporteSoles > 0
          AND MaterialCodigo IS NOT NULL
          {period_filter}
        GROUP BY MaterialCodigo, MaterialNombre
        ORDER BY ventas DESC
    """)

    # Top 5 clientes de la tienda
    top_clients = await azure_sql.query_readonly(f"""
        SELECT TOP 5
            SolicitanteCodigo   AS codigo,
            SolicitanteNombre   AS nombre,
            SUM(ImporteSoles)   AS ventas,
            COUNT(DISTINCT Documento) AS pedidos
        FROM SAP.WEB_FORECAST_VENTAS_REPORTE_ACTIVIDAD
        WHERE Codigo_OficinaVta = '{safe_code}'
          AND ImporteSoles > 0
          {period_filter}
        GROUP BY SolicitanteCodigo, SolicitanteNombre
        ORDER BY ventas DESC
    """)

    return {
        "store_code": safe_code,
        "store_name": s.get("nombre"),
        "period": period or "YTD",
        "resumen": {
            "ventas": round(float(s.get("ventas") or 0), 2),
            "utilidad": round(float(s.get("utilidad") or 0), 2),
            "margen_pct": round(float(s.get("margen_pct") or 0), 1),
            "documentos": int(s.get("documentos") or 0),
            "clientes": int(s.get("clientes") or 0),
            "unidades": round(float(s.get("unidades") or 0), 0),
        },
        "top_productos": [
            {
                "codigo": r.get("codigo"),
                "nombre": r.get("nombre"),
                "ventas": round(float(r.get("ventas") or 0), 2),
                "unidades": round(float(r.get("unidades") or 0), 0),
            }
            for r in top_products
        ],
        "top_clientes": [
            {
                "codigo": r.get("codigo"),
                "nombre": r.get("nombre"),
                "ventas": round(float(r.get("ventas") or 0), 2),
                "pedidos": int(r.get("pedidos") or 0),
            }
            for r in top_clients
        ],
        "timestamp": datetime.utcnow().isoformat(),
    }
