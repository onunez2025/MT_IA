# backend/layers/orchestrator.py
"""
Orchestrator — SOLE AI Fase 0

Arquitectura agéntica (v2):
  pregunta → agente DeepSeek (function calling) → N tools → respuesta analítica en lenguaje natural

El LLM decide cuáles herramientas invocar, las ejecuta y redacta una respuesta como un analista.
Ya no se usan plantillas fijas de texto (_format_response fue reemplazado por el LLM).

Fallback: si DEEPSEEK_API_KEY no está configurada, se mantiene el sistema de keywords para
no dejar la plataforma sin funcionamiento durante rotación de claves.
"""
import logging
import re
import time
from datetime import datetime
from typing import Dict, Any, Optional, List

from models.query import QueryResponse
from models.user import User
from layers.agent import run_agent, AgentResult
from tools.sales_tools import (
    get_sales_summary,
    get_sales_targets,
    get_sales_forecast,
    get_sales_performance,
)
from tools.customer_tools import get_customer_insights, search_customer_by_name
from tools.inventory_tools import get_inventory_by_sales
from tools.analytics_tools import (
    get_gap_to_target,
    get_inactive_customers,
    get_sales_by_channel,
    get_monthly_trend,
    get_new_customers,
    get_top_margin_products,
    get_product_sales_ranking,
)
from tools.report_tools import generate_forecast_report
from tools.store_tools import get_sales_by_store, get_store_detail
from guards.rbac import validate_rbac
from guards.audit import log_audit_entry
from guards.sanitization import sanitize_user_input

logger = logging.getLogger(__name__)

# ── Registro de herramientas ──────────────────────────────────────────────────
#
# Diccionario central {nombre → callable async} usado tanto por el agente (para
# ejecutar tools) como por el sistema de keywords (fallback).

TOOL_REGISTRY: Dict[str, Any] = {
    # Fase 0 originales
    "get_sales_summary":      get_sales_summary,
    "get_sales_targets":      get_sales_targets,
    "get_sales_forecast":     get_sales_forecast,
    "get_customer_insights":  get_customer_insights,
    "search_customer_by_name": search_customer_by_name,
    "get_sales_performance":  get_sales_performance,
    "get_inventory_by_sales": get_inventory_by_sales,
    # Fase 0+ nuevas
    "get_gap_to_target":          get_gap_to_target,
    "get_inactive_customers":     get_inactive_customers,
    "get_sales_by_channel":       get_sales_by_channel,
    "get_monthly_trend":          get_monthly_trend,
    "get_new_customers":          get_new_customers,
    "get_top_margin_products":    get_top_margin_products,
    "get_product_sales_ranking":  get_product_sales_ranking,
    "generate_forecast_report":   generate_forecast_report,
    # Tiendas/Oficinas de venta
    "get_sales_by_store":         get_sales_by_store,
    "get_store_detail":           get_store_detail,
}

# ── Saludos y mensajes sin intención de consulta ──────────────────────────────

_GREETINGS = {
    "hola", "hello", "hi", "buenas", "hey", "buen dia", "buen día",
    "buenos dias", "buenos días", "buenas tardes", "buenas noches",
    "gracias", "thanks", "ok", "okay", "listo", "perfecto",
}

_GREETING_RESPONSE = (
    "¡Hola! Soy SOLE, tu asistente de ventas MT Industrial 👋\n\n"
    "Puedo ayudarte con análisis como:\n"
    "• ¿Cuánto vendimos en agosto y cómo vamos vs la meta?\n"
    "• ¿Cuáles son los mejores vendedores del mes?\n"
    "• ¿Qué clientes llevan más de 60 días sin comprar?\n"
    "• ¿Cuál fue la tendencia de ventas los últimos 6 meses?\n"
    "• ¿Qué productos tienen mejor margen?\n\n"
    "¿Qué quieres analizar hoy?"
)

# ── Fallback keyword (solo si no hay API key) ─────────────────────────────────
#
# Se mantiene para no quedar sin funcionamiento durante rotación de claves.
# Cuando el agente está activo, este código no se ejecuta.

_MONTH_MAP = {
    "enero": 1, "febrero": 2, "marzo": 3, "abril": 4, "mayo": 5, "junio": 6,
    "julio": 7, "agosto": 8, "septiembre": 9, "octubre": 10, "noviembre": 11, "diciembre": 12,
}

TOOL_KEYWORDS: List[Dict[str, Any]] = [
    {"tool": "get_gap_to_target",       "keywords": ["falta", "cuánto falta", "cuanto falta", "brecha", "gap", "llegar a la meta"], "default_params": {}},
    {"tool": "get_inactive_customers",  "keywords": ["inactivo", "inactivos", "no han comprado", "no compró", "reactivar", "perdidos", "dejaron de comprar"], "default_params": {"days": 60}},
    {"tool": "get_new_customers",       "keywords": ["nuevos clientes", "clientes nuevos", "primera compra", "captación"], "default_params": {"period": "2026-08"}},
    {"tool": "get_top_margin_products", "keywords": ["margen", "mejor margen", "productos rentables", "rentabilidad"], "default_params": {"top_n": 10}},
    {"tool": "get_sales_by_channel",    "keywords": ["canal", "canales", "por canal", "ecommerce", "institucional"], "default_params": {"period": "2026-08"}},
    {"tool": "get_monthly_trend",       "keywords": ["tendencia", "trend", "evolución mensual", "últimos meses", "histórico mensual"], "default_params": {"months": 6}},
    {"tool": "get_sales_forecast",      "keywords": ["forecast", "pronóstico", "proyección"], "default_params": {"start_period": "2026-01", "end_period": "2026-08"}},
    {"tool": "get_sales_targets",       "keywords": ["meta", "target", "objetivo", "presupuesto", "cuota"], "default_params": {"year": 2026, "month": 8}},
    {"tool": "get_sales_performance",   "keywords": ["rendimiento", "ranking", "mejor vendedor", "mejores vendedores", "top vendedores"], "default_params": {"period": "2026-08"}},
    {"tool": "get_customer_insights",   "keywords": ["cliente", "historial", "compras del cliente"], "default_params": {"customer_id": "unknown"}},
    {"tool": "get_inventory_by_sales",  "keywords": ["inventario", "material", "producto", "stock"], "default_params": {}},
    {"tool": "get_sales_summary",       "keywords": ["venta", "ventas", "resumen", "cuanto vendimos", "cuánto vendimos", "facturación"], "default_params": {"period": "2026-08"}},
]


def _extract_period(question: str) -> Optional[str]:
    q = question.lower()
    now = datetime.now()
    m = re.search(r'\b(20\d\d)[/-](\d{1,2})\b', q)
    if m:
        return f"{m.group(1)}-{int(m.group(2)):02d}"
    for name, num in _MONTH_MAP.items():
        if name in q:
            yr_m = re.search(r'\b(20\d\d)\b', q)
            year = int(yr_m.group(1)) if yr_m else now.year
            return f"{year}-{num:02d}"
    if any(k in q for k in ["este mes", "mes actual"]):
        return f"{now.year}-{now.month:02d}"
    if "mes pasado" in q:
        m2 = now.month - 1 or 12
        y2 = now.year if now.month > 1 else now.year - 1
        return f"{y2}-{m2:02d}"
    yr_m = re.search(r'\b(20\d\d)\b', q)
    return yr_m.group(1) if yr_m else None


def _keyword_select_tool(question: str) -> Optional[Dict[str, Any]]:
    """Selección de herramienta por keywords (fallback cuando no hay API key)."""
    q = question.lower()
    now = datetime.now()
    for entry in TOOL_KEYWORDS:
        if not any(kw in q for kw in entry["keywords"]):
            continue
        params = dict(entry["default_params"])
        tool = entry["tool"]
        period = _extract_period(question)
        if tool in ("get_sales_summary", "get_sales_performance", "get_sales_by_channel", "get_new_customers"):
            if period:
                params["period"] = period
        elif tool == "get_sales_targets":
            if period and "-" in period:
                yr, mo = period.split("-")
                params.update({"year": int(yr), "month": int(mo)})
        elif tool == "get_gap_to_target":
            if period and "-" in period:
                yr, mo = period.split("-")
                params.update({"year": int(yr), "month": int(mo)})
        elif tool == "get_customer_insights":
            code_m = re.search(r'\b(\d{7,10})\b', question)
            if code_m:
                params["customer_id"] = code_m.group(1)
            else:
                return {"tool": "__help_customer__", "params": {}}
        return {"tool": tool, "params": params}
    return None


def _keyword_format_response(tool_name: str, result: Dict[str, Any]) -> str:
    """Formato básico de respuesta para el modo fallback (sin agente)."""
    if tool_name == "get_sales_summary":
        return (
            f"Período {result.get('period')} — "
            f"Ventas: S/ {result.get('total_sales', 0):,.2f} | "
            f"Pedidos: {result.get('num_orders', 0)} | "
            f"Clientes: {result.get('num_customers', 0)}"
        )
    elif tool_name == "get_gap_to_target":
        pct = result.get("pct_achievement", 0)
        icon = "✅" if result.get("on_track") else "⚠️"
        return (
            f"{icon} Brecha a la meta {result.get('period')}: "
            f"Meta S/ {result.get('meta', 0):,.2f} | "
            f"Real S/ {result.get('actual', 0):,.2f} | "
            f"Cumplimiento {pct:.1f}% | Falta S/ {result.get('gap', 0):,.2f}"
        )
    elif tool_name == "get_sales_performance":
        vendors = result.get("vendors", [])
        if not vendors:
            return "No se encontraron datos de rendimiento."
        lines = [f"🏆 Ranking de vendedores — {result.get('period')}:"]
        for i, v in enumerate(vendors[:10], 1):
            lines.append(f"  {i}. {v.get('vendor_name')} — S/ {v.get('total_sales', 0):,.2f}")
        return "\n".join(lines)
    elif tool_name == "get_inactive_customers":
        return (
            f"Clientes inactivos ({result.get('days_threshold', 60)}+ días sin compra): "
            f"{result.get('total_inactive', 0)} clientes."
        )
    elif tool_name == "get_monthly_trend":
        periodos = result.get("periodos", [])
        if not periodos:
            return "Sin datos de tendencia."
        return (
            f"Tendencia {result.get('months_analyzed')} meses: {result.get('tendencia', 'N/D')} "
            f"({result.get('crecimiento_pct', 0):+.1f}%). "
            f"Promedio mensual S/ {result.get('promedio_mensual', 0):,.2f}."
        )
    return str(result)


# ── Orchestrator ──────────────────────────────────────────────────────────────

class Orchestrator:
    """
    Enruta preguntas al agente agéntico, valida RBAC y registra auditoría.

    Modo principal:  Agente DeepSeek con function calling (análisis + respuesta natural)
    Modo fallback:   Keywords + plantilla (si DEEPSEEK_API_KEY no está configurada)
    """

    async def process_question(
        self,
        user: User,
        question: str,
        ip_address: str = "unknown",
    ) -> QueryResponse:
        """
        Procesa una pregunta en lenguaje natural:
          1. Sanitizar entrada
          2. Detectar saludos (respuesta directa, sin BD)
          3. Calcular herramientas permitidas por RBAC
          4. Ejecutar agente agéntico (o fallback keywords)
          5. Registrar auditoría
          6. Devolver respuesta
        """
        start_time = time.monotonic()

        # ── 1. Sanitizar ──────────────────────────────────────────────────────
        clean_question = sanitize_user_input(question)
        if not clean_question:
            return QueryResponse(
                status="error",
                response="Por favor ingresa una pregunta válida.",
                sources=[],
                error_message="Empty question after sanitization",
            )

        # ── 2. Detectar saludos / mensajes sin intención ──────────────────────
        q_lower = clean_question.lower().strip()
        if q_lower in _GREETINGS:
            return QueryResponse(
                status="success",
                response=_GREETING_RESPONSE,
                sources=[],
            )

        # ── 3. Calcular herramientas permitidas por RBAC ──────────────────────
        allowed_tools = [
            tool_name
            for tool_name in TOOL_REGISTRY
            if validate_rbac(user.roles, tool_name)
        ]

        if not allowed_tools:
            log_audit_entry(
                user_id=user.user_id,
                user_roles=user.roles,
                tool_name="none",
                parameters={"question": clean_question[:100]},
                status="BLOCKED",
                response_time_ms=(time.monotonic() - start_time) * 1000,
                ip_address=ip_address,
            )
            return QueryResponse(
                status="blocked",
                response="No tienes permiso para acceder a información de ventas.",
                sources=[],
                error_message="No tools allowed for user roles",
            )

        # ── 4a. Agente agéntico (modo principal) ──────────────────────────────
        from config import settings as _settings
        use_agent = bool(_settings.deepseek_api_key)

        if use_agent:
            agent_result: AgentResult = await run_agent(
                question=clean_question,
                tool_registry=TOOL_REGISTRY,
                allowed_tools=allowed_tools,
            )

            elapsed_ms = (time.monotonic() - start_time) * 1000

            # Auditoría: registrar todas las herramientas que usó el agente
            tools_str = ", ".join(agent_result.tools_used) if agent_result.tools_used else "none"
            log_audit_entry(
                user_id=user.user_id,
                user_roles=user.roles,
                tool_name=tools_str,
                parameters={"question": clean_question[:200]},
                status="ERROR" if agent_result.error else "SUCCESS",
                result_row_count=len(agent_result.tools_used),
                response_time_ms=elapsed_ms,
                ip_address=ip_address,
            )

            if agent_result.error and not agent_result.response:
                return QueryResponse(
                    status="error",
                    response="Ocurrió un error procesando tu consulta. Por favor intenta de nuevo.",
                    sources=[],
                    error_message=agent_result.error,
                )

            # Construir sources (badges en el chat)
            sources = [
                {"tool": t, "source": "SAP/SQL", "params": {}, "timestamp": ""}
                for t in agent_result.tools_used
            ]

            return QueryResponse(
                status="success",
                response=agent_result.response,
                sources=sources,
            )

        # ── 4b. Fallback: keywords + plantilla (sin API key) ──────────────────
        logger.warning("DEEPSEEK_API_KEY not set — falling back to keyword routing")

        selected = _keyword_select_tool(clean_question)
        if not selected:
            return QueryResponse(
                status="error",
                response=(
                    "No entendí tu pregunta. Intenta algo como: "
                    "'¿cuánto vendimos en agosto?' o '¿quiénes son los mejores vendedores?'"
                ),
                sources=[],
                error_message="No matching tool found (keyword fallback)",
            )

        tool_name = selected["tool"]
        tool_params = selected["params"]

        # Pseudo-tools en fallback
        if tool_name == "__help_customer__":
            return QueryResponse(
                status="success",
                response=(
                    "Para consultar el historial de un cliente necesito su código SAP "
                    "(número de 7-10 dígitos).\n\n"
                    "Ejemplo: 'historial del cliente 1234567'"
                ),
                sources=[],
            )

        # RBAC en fallback
        if tool_name not in allowed_tools:
            log_audit_entry(
                user_id=user.user_id, user_roles=user.roles, tool_name=tool_name,
                parameters=tool_params, status="BLOCKED",
                response_time_ms=(time.monotonic() - start_time) * 1000,
                ip_address=ip_address,
            )
            return QueryResponse(
                status="blocked",
                response="No tienes permiso para acceder a esta información.",
                sources=[],
                error_message="RBAC denied",
            )

        try:
            tool_fn = TOOL_REGISTRY[tool_name]
            result = await tool_fn(**tool_params)
            elapsed_ms = (time.monotonic() - start_time) * 1000

            log_audit_entry(
                user_id=user.user_id, user_roles=user.roles, tool_name=tool_name,
                parameters=tool_params, status="SUCCESS",
                result_row_count=1, response_time_ms=elapsed_ms, ip_address=ip_address,
            )

            response_text = _keyword_format_response(tool_name, result)
            return QueryResponse(
                status="success",
                response=response_text,
                sources=[{"tool": tool_name, "source": "SAP/SQL", "params": tool_params, "timestamp": ""}],
            )

        except Exception as exc:
            elapsed_ms = (time.monotonic() - start_time) * 1000
            logger.error(f"Fallback tool error {tool_name}: {exc}")
            log_audit_entry(
                user_id=user.user_id, user_roles=user.roles, tool_name=tool_name,
                parameters=tool_params, status="ERROR",
                response_time_ms=elapsed_ms, ip_address=ip_address,
            )
            return QueryResponse(
                status="error",
                response="Ocurrió un error procesando tu consulta. Por favor intenta de nuevo.",
                sources=[],
                error_message=str(exc),
            )
