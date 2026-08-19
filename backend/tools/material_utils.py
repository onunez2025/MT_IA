# backend/tools/material_utils.py
"""
Utilidades para consultar el maestro de materiales (PUNTO_VENTA).

El maestro de materiales vive en el servidor local 192.168.1.160.
En producción (EasyPanel/cloud) este servidor NO es accesible por red.

Degradación graceful:
  - Si la conexión falla → devuelve None
  - Las tools que usan este módulo omiten el filtro silenciosamente
  - Los datos siguen correctos, solo sin filtrar por tipo de material

Para habilitar en producción: sincronizar SAP_MM_MARA_MAESTRA_MATERIAL
a la base de datos Azure SQL y configurar PV_SQL_SERVER en EasyPanel.
"""

import logging
import time
from typing import Optional, Set

from config import settings

logger = logging.getLogger(__name__)

# ── Tipos de material que son SERVICIOS (excluir de rankings de productos) ────
#
# Clasificación SAP:
#   SERV — Servicio (genérico)
#   DIEN — Dienstleistung / Service (nomenclatura alemana)
#   ZACT — Actividad interna (custom MT Industrial)
SERVICE_TYPES: Set[str] = {"SERV", "DIEN", "ZACT"}

# ── Caché en memoria ──────────────────────────────────────────────────────────
# TTL de 6 horas: la maestra de materiales no cambia frecuentemente.
_CACHE_TTL = 6 * 3600  # segundos

_cached_service_codes: Optional[Set[str]] = None
_cache_timestamp: float = 0.0
_cache_available: Optional[bool] = None  # None = nunca intentado


async def get_service_material_codes() -> Optional[Set[str]]:
    """
    Devuelve el conjunto de códigos de material que son SERVICIOS.

    Usa caché en memoria con TTL de 6 horas.
    Devuelve None si la conexión a PUNTO_VENTA no está disponible
    (el caller debe omitir el filtro en ese caso).
    """
    global _cached_service_codes, _cache_timestamp, _cache_available

    now = time.monotonic()

    # Caché válido
    if _cached_service_codes is not None and (now - _cache_timestamp) < _CACHE_TTL:
        logger.debug(f"[material_utils] Cache hit — {len(_cached_service_codes)} códigos de servicio")
        return _cached_service_codes

    # Sabemos que no está disponible y el TTL no pasó → no reintentar
    if _cache_available is False and (now - _cache_timestamp) < 300:  # 5 min cooldown
        return None

    # Intentar conectar
    server = settings.pv_sql_server or settings.sql_server
    if not server:
        logger.debug("[material_utils] PV SQL no configurado — filtro de material desactivado")
        _cache_available = False
        _cache_timestamp = now
        return None

    try:
        from connectors.sql_connector import punto_venta_sql

        rows = await punto_venta_sql.query_readonly(f"""
            SELECT VC_codigo_material
            FROM [dbo].[SAP_MM_MARA_MAESTRA_MATERIAL]
            WHERE VC_tipo_material IN ({",".join(f"'{t}'" for t in SERVICE_TYPES)})
        """)

        codes = {str(r["VC_codigo_material"]).strip() for r in rows if r.get("VC_codigo_material")}
        _cached_service_codes = codes
        _cache_timestamp = now
        _cache_available = True
        logger.info(f"[material_utils] Cargados {len(codes)} códigos de servicio desde PUNTO_VENTA")
        return codes

    except Exception as exc:
        logger.warning(f"[material_utils] No se pudo conectar a PUNTO_VENTA: {exc}")
        _cache_available = False
        _cache_timestamp = now
        return None


async def get_material_info(material_code: str) -> Optional[dict]:
    """
    Devuelve información del maestro de materiales para un código dado.
    Incluye tipo, grupo, descripción larga y texto básico.

    Returns None si PUNTO_VENTA no está disponible.
    """
    server = settings.pv_sql_server or settings.sql_server
    if not server:
        return None

    try:
        from connectors.sql_connector import punto_venta_sql
        safe_code = material_code.replace("'", "''")

        rows_mara = await punto_venta_sql.query_readonly(f"""
            SELECT VC_codigo_material, VC_tipo_material, VC_grupo_articulo,
                   VC_unidad_base, DE_peso_neto
            FROM [dbo].[SAP_MM_MARA_MAESTRA_MATERIAL]
            WHERE VC_codigo_material = '{safe_code}'
        """)
        if not rows_mara:
            return None

        rows_txt = await punto_venta_sql.query_readonly(f"""
            SELECT VC_texto
            FROM [dbo].[SAP_MM_MARA_TEXTO_BASICOS_MATERIAL]
            WHERE VC_codigo_material = '{safe_code}'
        """)

        r = rows_mara[0]
        return {
            "codigo": r.get("VC_codigo_material"),
            "tipo_material": r.get("VC_tipo_material"),
            "grupo_articulo": r.get("VC_grupo_articulo"),
            "unidad_base": r.get("VC_unidad_base"),
            "peso_neto": float(r.get("DE_peso_neto") or 0),
            "descripcion_completa": rows_txt[0].get("VC_texto", "").strip() if rows_txt else "",
            "es_servicio": r.get("VC_tipo_material") in SERVICE_TYPES,
        }
    except Exception as exc:
        logger.warning(f"[material_utils] get_material_info({material_code}): {exc}")
        return None


async def build_material_exclusion_clause(
    table_alias: str = "",
    material_col: str = "MaterialCodigo",
) -> str:
    """
    Genera la cláusula SQL para excluir materiales de tipo servicio.

    Args:
        table_alias:  Alias de tabla en la query (ej: "w."). Vacío = sin alias.
        material_col: Nombre de la columna de código de material.

    Returns:
        String SQL listo para concatenar en WHERE, ej:
          "AND w.MaterialCodigo NOT IN ('000001234', '000005678', ...)"
        O string vacío si PUNTO_VENTA no está disponible.
    """
    codes = await get_service_material_codes()
    if not codes:
        return ""

    col_ref = f"{table_alias}{material_col}"
    # Batches de 1000 para evitar límite de SQL Server
    code_list = list(codes)
    chunks = [code_list[i:i+999] for i in range(0, len(code_list), 999)]

    clauses = []
    for chunk in chunks:
        quoted = ",".join(f"'{c}'" for c in chunk)
        clauses.append(f"{col_ref} NOT IN ({quoted})")

    if len(clauses) == 1:
        return f"AND {clauses[0]}"
    else:
        # Para múltiples chunks usamos AND NOT (IN ... OR IN ...)
        return "AND (" + " AND ".join(clauses) + ")"
