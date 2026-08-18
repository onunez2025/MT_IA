# backend/tools/sales_tools.py
import logging
from typing import Dict, Any, Optional
from datetime import datetime

from connectors.sql_connector import azure_sql
from tools.schemas import SalesSummaryParams, SalesTargetParams, SalesForecastParams, SalesPerformanceParams
from tools.utils import query_cache

logger = logging.getLogger(__name__)


async def get_sales_summary(period: str, region: Optional[str] = None) -> Dict[str, Any]:
    """
    Get total sales, orders, and customers for a given period.

    Args:
        period: "2026-08" (month), "2026-Q3" (quarter), or "2026" (year)
        region: Optional VC_zona_ventas filter

    Returns:
        Aggregated dict — never raw rows.
    """
    # Validate input
    params_model = SalesSummaryParams(period=period, region=region)

    # Check cache
    cache_key = f"sales_summary:{period}:{region}"
    cached = query_cache.get(cache_key)
    if cached:
        logger.info(f"Cache hit: {cache_key}")
        return cached

    # Build WHERE clause
    where_parts = []
    if "-Q" in period:           # "2026-Q3"
        year, q = period.split("-Q")
        q_months = {"1": "(1,2,3)", "2": "(4,5,6)", "3": "(7,8,9)", "4": "(10,11,12)"}
        where_parts.append(f"IN_anio = {int(year)}")
        where_parts.append(f"IN_mes IN {q_months[q]}")
    elif "-" in period:          # "2026-08"
        year, month = period.split("-")
        where_parts.append(f"IN_anio = {int(year)}")
        where_parts.append(f"IN_mes = {int(month)}")
    else:                        # "2026"
        where_parts.append(f"IN_anio = {int(period)}")

    if region:
        safe_region = region.replace("'", "''")
        where_parts.append(f"VC_zona_ventas = '{safe_region}'")

    where_clause = "WHERE " + " AND ".join(where_parts) if where_parts else ""

    query = f"""
    SELECT
        COUNT(DISTINCT VC_documento_pago_numero) AS num_orders,
        COUNT(DISTINCT VC_solicitante_codigo)    AS num_customers,
        SUM(DE_neto)                             AS total_sales,
        AVG(DE_neto)                             AS avg_order_value
    FROM SAP.SD_VENTAS
    {where_clause}
    """

    rows = await azure_sql.query_readonly(query)
    row = rows[0] if rows else {}

    total_sales = float(row.get("total_sales") or 0)
    num_orders = int(row.get("num_orders") or 0)
    num_customers = int(row.get("num_customers") or 0)
    avg_order_value = float(row.get("avg_order_value") or 0)

    result = {
        "period": period,
        "region": region or "Global",
        "total_sales": round(total_sales, 2),
        "num_orders": num_orders,
        "num_customers": num_customers,
        "avg_order_value": round(avg_order_value, 2),
        "timestamp": datetime.utcnow().isoformat(),
    }

    query_cache.set(cache_key, result)
    logger.info(f"get_sales_summary({period}, {region}) => total_sales={total_sales:,.2f}")
    return result


async def get_sales_targets(vendor_id: Optional[str] = None, year: int = 2026, month: Optional[int] = None) -> Dict[str, Any]:
    """Get sales targets vs actual for vendors. Placeholder until SIG targets table is confirmed."""
    params_model = SalesTargetParams(vendor_id=vendor_id, year=year, month=month)
    period_str = f"{year}-{month:02d}" if month else str(year)
    return {
        "vendor_id": vendor_id or "ALL",
        "period": period_str,
        "target": 0,
        "actual": 0,
        "pct_achievement": 0.0,
        "note": "Targets table (SIG) pending connection verification",
        "timestamp": datetime.utcnow().isoformat(),
    }


async def get_sales_forecast(start_period: str, end_period: str, region: Optional[str] = None) -> Dict[str, Any]:
    """Get sales forecast from WEB_FORECAST_VENTAS_REPORTE_ACTIVIDAD."""
    params_model = SalesForecastParams(start_period=start_period, end_period=end_period, region=region)

    start_year, start_month = start_period.split("-")
    end_year, end_month = end_period.split("-")

    where_parts = [
        f"(Anio > {int(start_year)} OR (Anio = {int(start_year)} AND MesNumero >= {int(start_month)}))",
        f"(Anio < {int(end_year)} OR (Anio = {int(end_year)} AND MesNumero <= {int(end_month)}))",
    ]
    if region:
        safe_region = region.replace("'", "''")
        where_parts.append(f"REGION = '{safe_region}'")

    where_clause = "WHERE " + " AND ".join(where_parts)

    query = f"""
    SELECT
        Anio,
        MesNumero,
        SUM(ImporteSoles)   AS forecast_sales,
        SUM(UtilidadSoles)  AS forecast_profit,
        COUNT(*)            AS num_records
    FROM SAP.WEB_FORECAST_VENTAS_REPORTE_ACTIVIDAD
    {where_clause}
    GROUP BY Anio, MesNumero
    ORDER BY Anio, MesNumero
    """

    rows = await azure_sql.query_readonly(query)

    return {
        "start_period": start_period,
        "end_period": end_period,
        "region": region or "Global",
        "periods": [
            {
                "period": f"{r['Anio']}-{int(r['MesNumero']):02d}",
                "forecast_sales": float(r.get("forecast_sales") or 0),
                "forecast_profit": float(r.get("forecast_profit") or 0),
                "num_records": int(r.get("num_records") or 0),
            }
            for r in rows
        ],
        "timestamp": datetime.utcnow().isoformat(),
    }


async def get_sales_performance(period: str, region: Optional[str] = None) -> Dict[str, Any]:
    """Get top-10 vendor sales performance for a month."""
    params_model = SalesPerformanceParams(period=period, region=region)

    year, month = period.split("-")
    where_parts = [f"IN_anio = {int(year)}", f"IN_mes = {int(month)}"]
    if region:
        safe_region = region.replace("'", "''")
        where_parts.append(f"VC_zona_ventas = '{safe_region}'")
    where_clause = "WHERE " + " AND ".join(where_parts)

    query = f"""
    SELECT TOP 10
        VC_vendedor_codigo                                      AS vendor_code,
        VC_vendedor_nombre                                      AS vendor_name,
        COUNT(DISTINCT VC_documento_pago_numero)                AS num_orders,
        SUM(DE_neto)                                            AS total_sales,
        COUNT(DISTINCT VC_solicitante_codigo)                   AS num_customers
    FROM SAP.SD_VENTAS
    {where_clause}
    GROUP BY VC_vendedor_codigo, VC_vendedor_nombre
    ORDER BY total_sales DESC
    """

    rows = await azure_sql.query_readonly(query)

    return {
        "period": period,
        "region": region or "Global",
        "vendors": [
            {
                "vendor_code": r.get("vendor_code"),
                "vendor_name": r.get("vendor_name"),
                "num_orders": int(r.get("num_orders") or 0),
                "total_sales": round(float(r.get("total_sales") or 0), 2),
                "num_customers": int(r.get("num_customers") or 0),
            }
            for r in rows
        ],
        "timestamp": datetime.utcnow().isoformat(),
    }
