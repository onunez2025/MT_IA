# backend/layers/llm_router.py
"""
LLM-based intent router using DeepSeek API (OpenAI-compatible).

Replaces keyword heuristics with semantic understanding:
  user question → DeepSeek → {tool, params} → execute tool → DB → response

Falls back to keyword matching (_select_tool) if:
  - DEEPSEEK_API_KEY not set
  - API timeout (8s) or error
  - Response is not valid JSON
"""

import json
import logging
from datetime import datetime
from typing import Optional, Dict, Any

from openai import AsyncOpenAI
from config import settings

logger = logging.getLogger(__name__)

# ── Lazy client ───────────────────────────────────────────────────────────────
_client: Optional[AsyncOpenAI] = None


def _get_client() -> Optional[AsyncOpenAI]:
    global _client
    if not settings.deepseek_api_key:
        return None
    if _client is None:
        _client = AsyncOpenAI(
            api_key=settings.deepseek_api_key,
            base_url=settings.deepseek_base_url,   # https://api.deepseek.com/v1
            timeout=8.0,
        )
    return _client


# ── Tool catalogue (fed to the LLM) ──────────────────────────────────────────
TOOL_CATALOGUE = [
    {
        "name": "get_sales_summary",
        "cuándo usarlo": "El usuario pregunta cuánto se vendió, facturación total, ingresos, número de pedidos o clientes activos en un período.",
        "params": {
            "period": "YYYY-MM para un mes (ej: '2026-07') o YYYY para un año. Predeterminado: mes actual."
        },
    },
    {
        "name": "get_gap_to_target",
        "cuándo usarlo": "El usuario pregunta cuánto falta para la meta, si se va a llegar al objetivo, brecha con la cuota, cumplimiento de la meta.",
        "params": {
            "year":  "año entero. Predeterminado: año actual.",
            "month": "mes entero 1-12. Predeterminado: mes actual.",
        },
    },
    {
        "name": "get_sales_targets",
        "cuándo usarlo": "El usuario pregunta cuál es la meta, el presupuesto o el objetivo de ventas del mes (sin interesarle la brecha).",
        "params": {
            "year":  "año entero.",
            "month": "mes entero 1-12.",
        },
    },
    {
        "name": "get_sales_performance",
        "cuándo usarlo": "El usuario pregunta por el ranking, top o rendimiento de los vendedores: quién vendió más, los mejores vendedores, quién llegó a su meta.",
        "params": {
            "period": "YYYY-MM. Predeterminado: mes actual.",
            "top_n":  "número de vendedores a mostrar (opcional, entero). Predeterminado: todos.",
        },
    },
    {
        "name": "get_sales_forecast",
        "cuándo usarlo": "El usuario pregunta por el forecast, proyección o pronóstico de ventas futuras.",
        "params": {
            "start_period": "YYYY-MM inicio del rango.",
            "end_period":   "YYYY-MM fin del rango.",
        },
    },
    {
        "name": "get_inactive_customers",
        "cuándo usarlo": "El usuario pregunta por clientes que no han comprado recientemente, clientes perdidos, inactivos, que hay que reactivar o recuperar.",
        "params": {
            "days": "días sin compra (entero). Predeterminado: 60. Si dice '3 meses' usar 90, '6 meses' usar 180.",
        },
    },
    {
        "name": "get_new_customers",
        "cuándo usarlo": "El usuario pregunta cuántos clientes nuevos hubo, captación, primera compra, clientes que compraron por primera vez.",
        "params": {
            "period": "YYYY-MM. Predeterminado: mes actual.",
        },
    },
    {
        "name": "get_customer_insights",
        "cuándo usarlo": "El usuario pide historial o información de UN cliente específico e incluye su código numérico SAP (7-10 dígitos).",
        "params": {
            "customer_id": "código numérico SAP del cliente (7-10 dígitos).",
        },
    },
    {
        "name": "get_sales_by_channel",
        "cuándo usarlo": "El usuario pregunta cómo se distribuyen las ventas por canal (Canal Moderno, Mostrador, Institucional, Tradicional, ecommerce).",
        "params": {
            "period": "YYYY-MM. Predeterminado: mes actual.",
        },
    },
    {
        "name": "get_monthly_trend",
        "cuándo usarlo": "El usuario pregunta por la tendencia, evolución o historial de ventas mes a mes en los últimos meses.",
        "params": {
            "months": "número de meses a analizar (entero). Predeterminado: 6.",
        },
    },
    {
        "name": "get_top_margin_products",
        "cuándo usarlo": "El usuario pregunta por los productos más rentables, con mejor margen, mayor utilidad, más ganancia.",
        "params": {
            "period": "YYYY-MM o YYYY (opcional).",
            "top_n":  "cuántos productos mostrar (entero, opcional). Predeterminado: 10.",
        },
    },
    {
        "name": "get_inventory_by_sales",
        "cuándo usarlo": "El usuario pregunta por inventario, stock, rotación de materiales o productos más vendidos.",
        "params": {},
    },
    {
        "name": "generate_forecast_report",
        "cuándo usarlo": "El usuario pide generar o descargar un reporte Excel de forecast.",
        "params": {
            "year":  "año del reporte (entero).",
            "month": "mes del reporte (entero).",
        },
    },
]

_SYSTEM_PROMPT = (
    "Eres un clasificador de intención para SOLE AI, sistema de ventas de MT Industrial (Perú).\n"
    "Tu ÚNICA función: leer la pregunta del usuario y devolver el JSON que indica qué herramienta usar.\n"
    "Responde SOLO con JSON válido. Cero texto adicional fuera del JSON."
)


def _build_prompt(question: str) -> str:
    now = datetime.now()
    cur = f"{now.year}-{now.month:02d}"
    prev_month = now.month - 1 or 12
    prev_year  = now.year if now.month > 1 else now.year - 1
    prev = f"{prev_year}-{prev_month:02d}"

    catalogue_txt = json.dumps(TOOL_CATALOGUE, ensure_ascii=False, indent=2)

    return f"""Fecha hoy: {now.strftime('%Y-%m-%d')}
Mes actual: {cur} | Mes pasado: {prev} | Año actual: {now.year}

Herramientas disponibles:
{catalogue_txt}

Pregunta del usuario: "{question}"

Instrucciones:
1. Elige la herramienta más apropiada según "cuándo usarlo".
2. Extrae los parámetros de la pregunta (fechas, períodos, números).
3. "este mes" → period="{cur}", "mes pasado" → period="{prev}", "este año" → period="{now.year}".
4. Si dice "top 5", "mejores 3", "los 10 primeros" → incluir top_n como entero.
5. Si el cliente no menciona su código SAP de 7-10 dígitos → tool="__help_customer__".
6. Si es saludo, chiste, pregunta fuera de ventas → tool=null.

Formato de respuesta (JSON únicamente):
{{"tool": "nombre_herramienta_o_null", "params": {{...}}}}"""


# ── Public function ───────────────────────────────────────────────────────────

async def llm_select_tool(question: str) -> Optional[Dict[str, Any]]:
    """
    Call DeepSeek to classify user intent.
    Returns {"tool": str, "params": dict} or None on failure.
    None means: fall back to keyword matching.
    """
    client = _get_client()
    if not client:
        logger.debug("LLM routing skipped — DEEPSEEK_API_KEY not set.")
        return None

    try:
        response = await client.chat.completions.create(
            model="deepseek-chat",
            messages=[
                {"role": "system", "content": _SYSTEM_PROMPT},
                {"role": "user",   "content": _build_prompt(question)},
            ],
            temperature=0,
            max_tokens=250,
            response_format={"type": "json_object"},
        )

        raw  = response.choices[0].message.content.strip()
        data = json.loads(raw)

        tool_name = data.get("tool")      # None = not a business question
        params    = data.get("params", {})

        # Sanitize numeric params
        for key in ("top_n", "months", "days", "year", "month"):
            if key in params and params[key] is not None:
                try:
                    params[key] = int(params[key])
                except (ValueError, TypeError):
                    params.pop(key, None)

        logger.info(f"LLM routing: '{question[:60]}' → tool={tool_name} params={params}")
        return {"tool": tool_name, "params": params}

    except Exception as exc:
        logger.warning(f"LLM routing failed ({type(exc).__name__}: {exc}). Falling back to keywords.")
        return None
