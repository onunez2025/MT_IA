# backend/layers/orchestrator.py
import logging
import re
import time
from datetime import datetime
from typing import Dict, Any, Optional, List

from models.query import QueryResponse
from models.user import User
from tools.sales_tools import (
    get_sales_summary,
    get_sales_targets,
    get_sales_forecast,
    get_sales_performance,
)
from tools.customer_tools import get_customer_insights
from tools.inventory_tools import get_inventory_by_sales
from tools.analytics_tools import (
    get_gap_to_target,
    get_inactive_customers,
    get_sales_by_channel,
    get_monthly_trend,
    get_new_customers,
    get_top_margin_products,
)
from tools.report_tools import generate_forecast_report
from guards.rbac import validate_rbac
from guards.audit import log_audit_entry
from guards.sanitization import sanitize_user_input, validate_tool_name

logger = logging.getLogger(__name__)

# Maps tool name -> callable
TOOL_REGISTRY: Dict[str, Any] = {
    # Fase 0 originales
    "get_sales_summary":      get_sales_summary,
    "get_sales_targets":      get_sales_targets,
    "get_sales_forecast":     get_sales_forecast,
    "get_customer_insights":  get_customer_insights,
    "get_sales_performance":  get_sales_performance,
    "get_inventory_by_sales": get_inventory_by_sales,
    # Fase 0+ nuevas
    "get_gap_to_target":        get_gap_to_target,
    "get_inactive_customers":   get_inactive_customers,
    "get_sales_by_channel":     get_sales_by_channel,
    "get_monthly_trend":        get_monthly_trend,
    "get_new_customers":        get_new_customers,
    "get_top_margin_products":  get_top_margin_products,
    "generate_forecast_report": generate_forecast_report,
}

# Keyword heuristics for tool selection (Fase 0: no LLM routing)
# Order matters: more specific tools first to avoid shadowing by generic ones.
TOOL_KEYWORDS: List[Dict[str, Any]] = [
    # ── Fase 0+ nuevas (más específicas → van primero) ──────────────────────
    {
        "tool": "generate_forecast_report",
        "keywords": ["armar archivo", "generar archivo", "genera el excel", "arma el excel",
                     "reporte excel", "excel forecast", "descarga", "generar reporte"],
        "default_params": {"year": 2026, "month": 9},
    },
    {
        "tool": "get_gap_to_target",
        "keywords": ["falta", "cuánto falta", "cuanto falta", "brecha", "gap",
                     "le falta", "me falta", "diferencia con la meta",
                     "alcanzar la meta", "llegar a la meta"],
        "default_params": {},
    },
    {
        "tool": "get_inactive_customers",
        "keywords": ["inactivo", "inactivos", "sin compra", "no compran",
                     "no han comprado", "no compró", "no compro",
                     "clientes que no han comprado", "reactivar", "reactivación",
                     "no han vuelto", "dejaron de comprar", "perdidos"],
        "default_params": {"days": 60},
    },
    {
        "tool": "get_new_customers",
        "keywords": ["nuevos clientes", "clientes nuevos", "clientes que compraron por primera vez",
                     "primera compra", "primer pedido", "captación"],
        "default_params": {"period": "2026-08"},
    },
    {
        "tool": "get_top_margin_products",
        "keywords": ["margen", "mejor margen", "productos rentables", "rentabilidad",
                     "utilidad por producto", "producto más rentable"],
        "default_params": {"top_n": 10},
    },
    {
        "tool": "get_sales_by_channel",
        "keywords": ["canal", "canales", "por canal", "ecommerce", "institucional",
                     "distribución por canal", "ventas por canal"],
        "default_params": {"period": "2026-08"},
    },
    {
        "tool": "get_monthly_trend",
        "keywords": ["tendencia", "trend", "evolución mensual", "cómo ha ido",
                     "como ha ido", "últimos meses", "ultimos meses", "histórico mensual"],
        "default_params": {"months": 6},
    },
    # ── Fase 0 originales ───────────────────────────────────────────────────
    {
        "tool": "get_sales_forecast",
        "keywords": ["forecast", "pronóstico", "pronostico", "proyección", "proyeccion"],
        "default_params": {"start_period": "2026-01", "end_period": "2026-08"},
    },
    {
        "tool": "get_sales_targets",
        "keywords": ["meta", "metas", "target", "objetivo", "presupuesto", "cuota"],
        "default_params": {"year": 2026, "month": 8},
    },
    {
        "tool": "get_sales_performance",
        "keywords": ["rendimiento", "performance", "ranking", "top vendedor", "mejor vendedor"],
        "default_params": {"period": "2026-08"},
    },
    {
        "tool": "get_customer_insights",
        "keywords": ["cliente", "customer", "historial", "compras del cliente"],
        "default_params": {"customer_id": "unknown"},
    },
    {
        "tool": "get_inventory_by_sales",
        "keywords": ["inventario", "inventory", "material", "producto", "stock"],
        "default_params": {},
    },
    {
        "tool": "get_sales_summary",
        "keywords": ["venta", "ventas", "resumen", "total ventas", "ingreso", "revenue",
                     "cuanto vendimos", "cuánto vendimos", "cuanto se vendio",
                     "cuánto se vendió", "facturacion", "facturación"],
        "default_params": {"period": "2026-08"},
    },
]


_MONTH_MAP = {
    "enero": 1, "febrero": 2, "marzo": 3, "abril": 4, "mayo": 5, "junio": 6,
    "julio": 7, "agosto": 8, "septiembre": 9, "octubre": 10, "noviembre": 11, "diciembre": 12,
    "january": 1, "february": 2, "march": 3, "april": 4, "june": 6,
    "july": 7, "august": 8, "september": 9, "october": 10, "november": 11, "december": 12,
}


def _extract_period(question: str) -> Optional[str]:
    """Extract period string YYYY-MM or YYYY from question text."""
    q = question.lower()
    now = datetime.now()

    # Explicit YYYY-MM
    m = re.search(r'\b(20\d\d)[/-](\d{1,2})\b', q)
    if m:
        return f"{m.group(1)}-{int(m.group(2)):02d}"

    # Month name + year: "julio 2026" / "2026 julio"
    for name, num in _MONTH_MAP.items():
        if name in q:
            yr_m = re.search(r'\b(20\d\d)\b', q)
            year = int(yr_m.group(1)) if yr_m else now.year
            return f"{year}-{num:02d}"

    # "este mes" / "del mes" / "mes actual"
    if any(k in q for k in ["este mes", "del mes", "mes actual", "mes pasado"]):
        month = now.month - 1 if "pasado" in q else now.month
        year  = now.year if month > 0 else now.year - 1
        month = month or 12
        return f"{year}-{month:02d}"

    # Solo año
    yr_m = re.search(r'\b(20\d\d)\b', q)
    if yr_m:
        return yr_m.group(1)

    return None


def _select_tool(question: str) -> Optional[Dict[str, Any]]:
    """
    Select tool based on keyword heuristics and extract params from question text.
    Returns dict with 'tool' and 'params', or None if no match.
    """
    q = question.lower()
    now = datetime.now()

    for entry in TOOL_KEYWORDS:
        if not any(kw in q for kw in entry["keywords"]):
            continue

        params = dict(entry["default_params"])
        tool   = entry["tool"]

        # Enrich params from question text
        if tool in ("get_sales_summary", "get_sales_performance"):
            period = _extract_period(question)
            if period:
                params["period"] = period

        elif tool == "get_sales_targets":
            period = _extract_period(question)
            if period and "-" in period:
                yr, mo = period.split("-")
                params["year"]  = int(yr)
                params["month"] = int(mo)
            elif period:
                params["year"] = int(period)
                params.pop("month", None)

        elif tool == "get_sales_forecast":
            # Look for two periods or a year range
            yr_m = re.search(r'\b(20\d\d)\b', q)
            if yr_m:
                yr = yr_m.group(1)
                params["start_period"] = f"{yr}-01"
                params["end_period"]   = f"{yr}-{now.month:02d}" if int(yr) == now.year else f"{yr}-12"

        elif tool == "get_customer_insights":
            # Extract numeric customer code (7–10 digits)
            code_m = re.search(r'\b(\d{7,10})\b', question)
            if code_m:
                params["customer_id"] = code_m.group(1)
            else:
                # Sin código de cliente identificable → devolver ayuda en lugar de buscar "unknown"
                return {
                    "tool": "__help_customer__",
                    "params": {},
                }

        elif tool == "get_gap_to_target":
            period = _extract_period(question)
            if period and "-" in period:
                yr, mo = period.split("-")
                params["year"]  = int(yr)
                params["month"] = int(mo)
            elif period:
                params["year"] = int(period)

        elif tool in ("get_inactive_customers",):
            # Extract day threshold: "60 días", "90 días"
            day_m = re.search(r'\b(\d{2,3})\s*d[ií]as?\b', q)
            if day_m:
                params["days"] = int(day_m.group(1))

        elif tool in ("get_sales_by_channel",):
            period = _extract_period(question)
            if period:
                params["period"] = period

        elif tool == "get_monthly_trend":
            # "últimos 3 meses" / "últimos 12 meses"
            m_m = re.search(r'\b(\d{1,2})\s*meses?\b', q)
            if m_m:
                params["months"] = int(m_m.group(1))

        elif tool in ("get_new_customers",):
            period = _extract_period(question)
            if period:
                params["period"] = period

        elif tool == "get_top_margin_products":
            period = _extract_period(question)
            if period:
                params["period"] = period
            top_m = re.search(r'\btop\s*(\d{1,2})\b', q)
            if top_m:
                params["top_n"] = int(top_m.group(1))

        elif tool == "generate_forecast_report":
            period = _extract_period(question)
            if period and "-" in period:
                yr, mo = period.split("-")
                params["year"]  = int(yr)
                params["month"] = int(mo)
            elif period:
                params["year"] = int(period)

        return {"tool": tool, "params": params}

    return None


def _format_response(tool_name: str, result: Dict[str, Any]) -> str:
    """Format tool result as a readable Spanish string."""
    if tool_name == "get_sales_summary":
        return (
            f"En el período {result.get('period')} ({result.get('region')}): "
            f"ventas totales S/ {result.get('total_sales', 0):,.2f}, "
            f"{result.get('num_orders', 0)} pedidos, "
            f"{result.get('num_customers', 0)} clientes."
        )
    elif tool_name == "get_sales_targets":
        target = result.get("target", 0)
        actual = result.get("actual", 0)
        pct    = result.get("pct_achievement", 0)
        note   = result.get("note", "")
        store  = result.get("store_id", "")
        vendor = result.get("vendor_id", "todos")
        base = (
            f"Meta {result.get('period')} — Tienda {store} "
            f"({'Vendedor: ' + vendor if vendor != 'ALL' else 'todos los vendedores'}): "
            f"Meta S/ {target:,.2f} | Real S/ {actual:,.2f} | Cumplimiento {pct:.1f}%."
        )
        return base + (f" {note}" if note else "")
    elif tool_name == "get_sales_forecast":
        periods = result.get("periods", [])
        if not periods:
            return "No se encontraron datos de forecast para el período solicitado."
        total = sum(p.get("forecast_sales", 0) for p in periods)
        return (
            f"Forecast de ventas ({result.get('start_period')} a {result.get('end_period')}): "
            f"proyección total S/ {total:,.2f} en {len(periods)} meses."
        )
    elif tool_name == "get_sales_performance":
        vendors = result.get("vendors", [])
        if not vendors:
            return "No se encontraron datos de rendimiento para el período solicitado."
        top = vendors[0]
        return (
            f"Top vendedor en {result.get('period')}: {top.get('vendor_name')} "
            f"con S/ {top.get('total_sales', 0):,.2f} en ventas "
            f"({top.get('num_orders', 0)} pedidos)."
        )
    elif tool_name == "get_customer_insights":
        return (
            f"Cliente {result.get('customer_id')}: "
            f"{result.get('num_transactions', 0)} transacciones, "
            f"total gastado S/ {result.get('total_spent', 0):,.2f}, "
            f"última compra: {result.get('last_purchase_date', 'N/D')}."
        )
    elif tool_name == "get_inventory_by_sales":
        materials = result.get("materials", [])
        if not materials:
            return "No se encontraron materiales para los filtros indicados."
        return (
            f"Se encontraron {len(materials)} materiales. "
            f"El más vendido: {materials[0].get('description')} "
            f"({materials[0].get('quantity_delivered', 0):,.0f} unidades entregadas)."
        )
    # ── Fase 0+ nuevas ──────────────────────────────────────────────────────
    elif tool_name == "get_gap_to_target":
        meta   = result.get("meta", 0)
        actual = result.get("actual", 0)
        gap    = result.get("gap", 0)
        pct    = result.get("pct_achievement", 0)
        d_left = result.get("days_remaining", 0)
        needed = result.get("daily_needed_to_close", 0)
        on_track = result.get("on_track", False)
        icon   = "✅" if on_track else "⚠️"
        return (
            f"{icon} Brecha a la meta — {result.get('period')} (Tienda {result.get('store_id')}): "
            f"Meta S/ {meta:,.2f} | Real S/ {actual:,.2f} | "
            f"Cumplimiento {pct:.1f}% | Falta S/ {gap:,.2f}. "
            f"Quedan {d_left} días. Ritmo diario necesario: S/ {needed:,.2f}/día."
        )
    elif tool_name == "get_inactive_customers":
        total = result.get("total_inactive", 0)
        days  = result.get("days_threshold", 60)
        custs = result.get("customers", [])
        top3  = ", ".join(c.get("nombre", "") for c in custs[:3])
        return (
            f"Clientes inactivos (sin compra en {days}+ días): {total} clientes. "
            f"Top 3 por valor histórico: {top3}."
        )
    elif tool_name == "get_sales_by_channel":
        canales = result.get("canales", [])
        total   = result.get("total_ventas", 0)
        if not canales:
            return "No se encontraron ventas por canal para el período indicado."
        lines = [
            f"Ventas por canal — {result.get('period')} (Total: S/ {total:,.2f}):"
        ]
        for c in canales:
            lines.append(
                f"  • {c['canal']}: S/ {c['ventas']:,.2f} ({c['participacion_pct']}%)"
            )
        lines.append(
            "\n⚠️ Nota: estos totales corresponden a ventas con canal registrado en el sistema "
            "(puede ser menor al total general de ventas del período)."
        )
        return "\n".join(lines)
    elif tool_name == "get_monthly_trend":
        periodos = result.get("periodos", [])
        if not periodos:
            return "No se encontraron datos de tendencia para el período solicitado."
        tendencia = result.get("tendencia", "")
        crecimiento = result.get("crecimiento_pct", 0)
        prom = result.get("promedio_mensual", 0)
        last = periodos[-1]
        return (
            f"Tendencia {result.get('months_analyzed')} meses: {tendencia} "
            f"({crecimiento:+.1f}% vs primer mes). "
            f"Promedio mensual S/ {prom:,.2f}. "
            f"Último mes ({last['periodo']}): S/ {last['ventas']:,.2f} "
            f"(MoM: {last['mom_pct']:+.1f}%)" if last.get("mom_pct") is not None else ""
        )
    elif tool_name == "get_new_customers":
        total = result.get("total_new_customers", 0)
        custs = result.get("customers", [])
        top3  = ", ".join(c.get("nombre", "") for c in custs[:3])
        return (
            f"Clientes nuevos en {result.get('period')}: {total}. "
            + (f"Principales: {top3}." if top3 else "")
        )
    elif tool_name == "get_top_margin_products":
        prods = result.get("products", [])
        if not prods:
            return "No se encontraron productos con datos de margen para el período."
        top = prods[0]
        return (
            f"Top {len(prods)} productos por margen — {result.get('period')}: "
            f"#1 {top['nombre']} con {top['margen_pct']}% de margen "
            f"(ventas S/ {top['ventas']:,.2f})."
        )
    elif tool_name == "generate_forecast_report":
        if "error" in result:
            return f"Error generando reporte: {result['error']}"
        return (
            f"✅ Reporte generado: {result.get('filename')} — "
            f"Forecast {result.get('target_month')} {result.get('period', '')[:4]}: "
            f"Conservador S/ {result.get('forecast_conservador', 0):,.2f} | "
            f"Base S/ {result.get('forecast_base', 0):,.2f} | "
            f"Optimista S/ {result.get('forecast_optimista', 0):,.2f}. "
            f"Guardado en: {result.get('file_path')}"
        )
    return str(result)


class Orchestrator:
    """
    Routes user questions to appropriate tools, enforces RBAC, and logs audit trail.
    Fase 0: keyword-based tool selection (no LLM routing).
    """

    async def process_question(
        self,
        user: User,
        question: str,
        ip_address: str = "unknown",
    ) -> QueryResponse:
        """
        Process a natural language question:
        1. Sanitize input
        2. Select tool via heuristics
        3. Validate RBAC
        4. Execute tool
        5. Log audit
        6. Return formatted response
        """
        start_time = time.monotonic()

        # 1. Sanitize
        clean_question = sanitize_user_input(question)
        if not clean_question:
            return QueryResponse(
                status="error",
                response="Por favor ingresa una pregunta válida.",
                sources=[],
                error_message="Empty question after sanitization",
            )

        # 1.5. Saludos y mensajes cortos sin intención de consulta
        _GREETINGS = {
            "hola", "hello", "hi", "buenas", "hey", "buen dia", "buen día",
            "buenos dias", "buenos días", "buenas tardes", "buenas noches",
            "gracias", "thanks", "ok", "okay", "listo", "perfecto",
        }
        q_lower = clean_question.lower().strip()
        if q_lower in _GREETINGS or (len(q_lower.split()) <= 3 and q_lower in _GREETINGS):
            return QueryResponse(
                status="success",
                response=(
                    "¡Hola! Soy SOLE, tu asistente de ventas MT Industrial 👋\n\n"
                    "Puedo ayudarte con:\n"
                    "• Ventas del mes o período\n"
                    "• Brecha vs meta\n"
                    "• Clientes inactivos o nuevos\n"
                    "• Forecast y tendencias\n"
                    "• Ventas por canal y margen de productos\n\n"
                    "¿Qué quieres consultar?"
                ),
                sources=[],
            )

        # 2. Select tool
        selected = _select_tool(clean_question)
        if not selected:
            log_audit_entry(
                user_id=user.user_id,
                user_roles=user.roles,
                tool_name="none",
                parameters={"question": clean_question[:100]},
                status="ERROR",
                response_time_ms=(time.monotonic() - start_time) * 1000,
                ip_address=ip_address,
            )
            return QueryResponse(
                status="error",
                response=(
                    "No entendí tu pregunta. Intenta algo como: "
                    "'¿cuáles fueron las ventas de agosto?' o '¿cuál es el forecast de Q4?'"
                ),
                sources=[],
                error_message="No matching tool found",
            )

        tool_name = selected["tool"]
        tool_params = selected["params"]

        # 2.5. Pseudo-tools: respuestas de ayuda sin llamar a BD
        if tool_name == "__help_customer__":
            return QueryResponse(
                status="success",
                response=(
                    "Para consultar el historial de un cliente específico necesito su código de cliente "
                    "(número de 7-10 dígitos en el sistema SAP).\n\n"
                    "Ejemplo: 'historial del cliente 1234567'\n\n"
                    "Si buscas clientes inactivos o nuevos, puedes preguntar:\n"
                    "• '¿Qué clientes no han comprado en 60 días?'\n"
                    "• '¿Cuántos clientes nuevos tuvimos en agosto?'"
                ),
                sources=[],
            )

        # 3. Validate RBAC
        if not validate_rbac(user.roles, tool_name):
            log_audit_entry(
                user_id=user.user_id,
                user_roles=user.roles,
                tool_name=tool_name,
                parameters=tool_params,
                status="BLOCKED",
                response_time_ms=(time.monotonic() - start_time) * 1000,
                ip_address=ip_address,
            )
            return QueryResponse(
                status="blocked",
                response="No tienes permiso para acceder a esta información.",
                sources=[],
                error_message="RBAC denied",
            )

        # 4. Execute tool
        try:
            # Look up from module globals so patches in tests work correctly
            import sys as _sys
            _module = _sys.modules[__name__]
            tool_fn = getattr(_module, tool_name, TOOL_REGISTRY.get(tool_name))
            result = await tool_fn(**tool_params)
            elapsed_ms = (time.monotonic() - start_time) * 1000

            # 5. Log audit (SUCCESS)
            row_count = len(result.get("materials", result.get("vendors", result.get("periods", [result]))))
            log_audit_entry(
                user_id=user.user_id,
                user_roles=user.roles,
                tool_name=tool_name,
                parameters=tool_params,
                status="SUCCESS",
                result_row_count=row_count,
                response_time_ms=elapsed_ms,
                ip_address=ip_address,
            )

            # 6. Format response
            response_text = _format_response(tool_name, result)
            return QueryResponse(
                status="success",
                response=response_text,
                sources=[{
                    "tool": tool_name,
                    "source": "SAP/SQL",
                    "params": tool_params,
                    "timestamp": result.get("timestamp", ""),
                }],
            )

        except Exception as e:
            elapsed_ms = (time.monotonic() - start_time) * 1000
            logger.error(f"Orchestrator error for tool={tool_name}: {e}")
            log_audit_entry(
                user_id=user.user_id,
                user_roles=user.roles,
                tool_name=tool_name,
                parameters=tool_params,
                status="ERROR",
                response_time_ms=elapsed_ms,
                ip_address=ip_address,
            )
            return QueryResponse(
                status="error",
                response="Ocurrió un error procesando tu consulta. Por favor intenta de nuevo.",
                sources=[],
                error_message=str(e),
            )
