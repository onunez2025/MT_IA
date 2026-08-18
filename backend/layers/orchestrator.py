# backend/layers/orchestrator.py
import logging
import time
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
from guards.rbac import validate_rbac
from guards.audit import log_audit_entry
from guards.sanitization import sanitize_user_input, validate_tool_name

logger = logging.getLogger(__name__)

# Maps tool name -> callable
TOOL_REGISTRY: Dict[str, Any] = {
    "get_sales_summary": get_sales_summary,
    "get_sales_targets": get_sales_targets,
    "get_sales_forecast": get_sales_forecast,
    "get_customer_insights": get_customer_insights,
    "get_sales_performance": get_sales_performance,
    "get_inventory_by_sales": get_inventory_by_sales,
}

# Keyword heuristics for tool selection (Fase 0: no LLM routing)
TOOL_KEYWORDS: List[Dict[str, Any]] = [
    {
        "tool": "get_sales_forecast",
        "keywords": ["forecast", "pronóstico", "pronostico", "proyección", "proyeccion"],
        "default_params": {"start_period": "2026-09", "end_period": "2026-12"},
    },
    {
        "tool": "get_sales_targets",
        "keywords": ["meta", "metas", "target", "objetivo", "presupuesto", "cuota"],
        "default_params": {"year": 2026},
    },
    {
        "tool": "get_sales_performance",
        "keywords": ["rendimiento", "performance", "ranking", "vendedor", "top", "mejor"],
        "default_params": {"period": "2026-08"},
    },
    {
        "tool": "get_customer_insights",
        "keywords": ["cliente", "customer", "historial", "compras"],
        "default_params": {"customer_id": "unknown"},
    },
    {
        "tool": "get_inventory_by_sales",
        "keywords": ["inventario", "inventory", "material", "producto", "stock"],
        "default_params": {},
    },
    {
        "tool": "get_sales_summary",
        "keywords": ["venta", "ventas", "resumen", "total", "ingreso", "revenue", "cuánto", "cuanto"],
        "default_params": {"period": "2026-08"},
    },
]


def _select_tool(question: str) -> Optional[Dict[str, Any]]:
    """
    Select tool based on keyword heuristics.
    Returns dict with 'tool' and 'params', or None if no match.
    """
    q = question.lower()
    for entry in TOOL_KEYWORDS:
        if any(kw in q for kw in entry["keywords"]):
            return {"tool": entry["tool"], "params": dict(entry["default_params"])}
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
        return (
            f"Meta de ventas para {result.get('vendor_id', 'todos')}: "
            f"objetivo {result.get('target', 0):,}, actual {result.get('actual', 0):,} "
            f"({result.get('pct_achievement', 0):.1f}% de cumplimiento). "
            f"{result.get('note', '')}"
        )
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
