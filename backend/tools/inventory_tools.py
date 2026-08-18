# backend/tools/inventory_tools.py
import logging
from typing import Dict, Any, Optional
from datetime import datetime

from connectors.sql_connector import azure_sql
from tools.schemas import InventoryParams
from tools.utils import query_cache

logger = logging.getLogger(__name__)


async def get_inventory_by_sales(
    material_code: Optional[str] = None,
    region: Optional[str] = None
) -> Dict[str, Any]:
    """
    Get materials sold (delivery data from SD_ENTREGAS).

    Args:
        material_code: Optional VC_material_codigo filter
        region: Optional VC_zona_ventas filter

    Returns:
        Aggregated materials list — never raw rows.
    """
    params_model = InventoryParams(material_code=material_code, region=region)

    cache_key = f"inventory:{material_code}:{region}"
    cached = query_cache.get(cache_key)
    if cached:
        logger.info(f"Cache hit: {cache_key}")
        return cached

    where_parts = []
    if material_code:
        safe_mat = material_code.replace("'", "''")
        where_parts.append(f"VC_material_codigo = '{safe_mat}'")
    if region:
        safe_region = region.replace("'", "''")
        where_parts.append(f"VC_organizacion_venta = '{safe_region}'")

    where_clause = ("WHERE " + " AND ".join(where_parts)) if where_parts else ""

    query = f"""
    SELECT TOP 50
        VC_material_codigo                       AS material_code,
        VC_material_denominacion                 AS description,
        SUM(DE_cantidad)                         AS quantity_delivered,
        COUNT(DISTINCT VC_entrega_numero)        AS num_deliveries,
        COUNT(DISTINCT VC_organizacion_venta)     AS num_regions
    FROM SAP.SD_ENTREGAS
    {where_clause}
    GROUP BY VC_material_codigo, VC_material_denominacion
    ORDER BY quantity_delivered DESC
    """

    rows = await azure_sql.query_readonly(query)

    result = {
        "material_code_filter": material_code,
        "region_filter": region,
        "materials": [
            {
                "material_code": r.get("material_code"),
                "description": r.get("description"),
                "quantity_delivered": round(float(r.get("quantity_delivered") or 0), 2),
                "num_deliveries": int(r.get("num_deliveries") or 0),
                "num_regions": int(r.get("num_regions") or 0),
            }
            for r in rows
        ],
        "timestamp": datetime.utcnow().isoformat(),
    }

    query_cache.set(cache_key, result)
    logger.info(f"get_inventory_by_sales({material_code}, {region}) => {len(rows)} materials")
    return result
