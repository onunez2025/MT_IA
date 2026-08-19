# backend/tools/customer_tools.py
import logging
from typing import Dict, Any, Optional
from datetime import datetime

from connectors.sql_connector import azure_sql
from connectors.c4c_connector import c4c
from tools.schemas import CustomerInsightsParams
from tools.utils import query_cache

logger = logging.getLogger(__name__)


async def search_customer_by_name(name: str, limit: int = 10) -> Dict[str, Any]:
    """
    Busca clientes por nombre/razón social O por número de documento
    (DNI, RUC, carnet de extranjería).

    Detecta automáticamente si el input es un número (→ busca por documento)
    o texto (→ busca por razón social).

    Args:
        name:  Nombre, fragmento de nombre, DNI, RUC o CE. Ej: 'VALVOSANITARIA', '70333796'.
        limit: Máximo de resultados. Default 10.
    """
    safe_input = name.strip().replace("'", "''")
    limit = max(1, min(int(limit), 30))

    # ¿Es numérico? → buscar por VC_solicitante_identificacion_numero
    if safe_input.isdigit():
        where_clause = f"VC_solicitante_identificacion_numero = '{safe_input}'"
    else:
        where_clause = f"VC_solicitante_razon_social LIKE '%{safe_input.upper()}%'"

    rows = await azure_sql.query_readonly(f"""
        SELECT TOP {limit}
            VC_solicitante_codigo                       AS codigo,
            MAX(VC_solicitante_razon_social)            AS razon_social,
            MAX(VC_solicitante_identificacion_numero)   AS doc_identidad,
            SUM(DE_neto)                                AS total_compras,
            COUNT(DISTINCT VC_documento_pago_numero)    AS pedidos,
            MAX(DT_documento_pago_fecha)                AS ultima_compra
        FROM SAP.SD_VENTAS
        WHERE {where_clause}
          AND VC_solicitante_codigo IS NOT NULL
        GROUP BY VC_solicitante_codigo
        ORDER BY total_compras DESC
    """)

    return {
        "query": name,
        "busqueda_por": "documento" if safe_input.isdigit() else "nombre",
        "total_encontrados": len(rows),
        "clientes": [
            {
                "codigo_sap": r.get("codigo"),
                "razon_social": r.get("razon_social"),
                "doc_identidad": r.get("doc_identidad"),
                "total_compras": round(float(r.get("total_compras") or 0), 2),
                "pedidos": int(r.get("pedidos") or 0),
                "ultima_compra": str(r.get("ultima_compra") or ""),
            }
            for r in rows
        ],
    }


async def get_customer_insights(customer_id: str) -> Dict[str, Any]:
    """
    Get customer profile and purchase history.

    Combines:
    - SAP C4C: name, email, phone (if available)
    - SQL SD_VENTAS: transaction history aggregated

    Args:
        customer_id: Customer code (VC_solicitante_codigo)

    Returns:
        Aggregated customer dict — never raw rows.
    """
    params_model = CustomerInsightsParams(customer_id=customer_id)
    safe_id = customer_id.strip()

    cache_key = f"customer_insights:{safe_id}"
    cached = query_cache.get(cache_key)
    if cached:
        logger.info(f"Cache hit: {cache_key}")
        return cached

    # SQL: aggregated purchase history
    sql_safe_id = safe_id.replace("'", "''")
    history_query = f"""
    SELECT
        MAX(VC_solicitante_razon_social)         AS razon_social,
        COUNT(DISTINCT VC_documento_pago_numero) AS num_transactions,
        SUM(DE_neto)                             AS total_spent,
        MAX(DT_documento_pago_fecha)             AS last_purchase_date,
        AVG(DE_neto)                             AS avg_transaction_value,
        MIN(DT_documento_pago_fecha)             AS first_purchase_date
    FROM SAP.SD_VENTAS
    WHERE VC_solicitante_codigo = '{sql_safe_id}'
    """
    rows = await azure_sql.query_readonly(history_query)
    history = rows[0] if rows else {}

    # C4C: profile (graceful fallback if unavailable)
    customer_name = None
    customer_email = None
    customer_phone = None
    try:
        c4c_customers = await c4c.get_customer_list({"$filter": f"ObjectID eq '{sql_safe_id}'"})
        if c4c_customers:
            customer_name = c4c_customers[0].get("Name")
            customer_email = c4c_customers[0].get("Email")
            customer_phone = c4c_customers[0].get("Phone")
    except Exception as e:
        logger.warning(f"C4C lookup failed for {safe_id}: {e}")

    # Preferir razón social de SAP SD_VENTAS; C4C como fallback
    razon_social_sap = history.get("razon_social")
    resolved_name = customer_name or razon_social_sap

    result = {
        "customer_id": safe_id,
        "name": resolved_name,
        "razon_social": razon_social_sap,
        "email": customer_email,
        "phone": customer_phone,
        "num_transactions": int(history.get("num_transactions") or 0),
        "total_spent": round(float(history.get("total_spent") or 0), 2),
        "avg_transaction_value": round(float(history.get("avg_transaction_value") or 0), 2),
        "last_purchase_date": str(history.get("last_purchase_date") or ""),
        "first_purchase_date": str(history.get("first_purchase_date") or ""),
        "timestamp": datetime.utcnow().isoformat(),
    }

    query_cache.set(cache_key, result)
    logger.info(f"get_customer_insights({safe_id}) => {result['num_transactions']} transactions")
    return result
