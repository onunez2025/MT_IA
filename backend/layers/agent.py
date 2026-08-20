# backend/layers/agent.py
"""
SOLE AI — Agentic loop con DeepSeek function calling.

Arquitectura:
  pregunta del usuario
    → DeepSeek analiza y decide qué herramientas necesita
    → herramientas se ejecutan (1 a N llamadas)
    → DeepSeek sintetiza una respuesta en lenguaje natural

Diferencia vs arquitectura anterior:
  ANTES: pregunta → detectar 1 tool → ejecutar → plantilla de texto
  AHORA: pregunta → LLM decide N tools → ejecutar todas → LLM redacta respuesta analítica

Soporta hasta MAX_ROUNDS rondas de tool calls por request (guarda contra loops).
"""

import asyncio
import json
import logging
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, AsyncGenerator, Dict, List, Optional, Tuple

from openai import AsyncOpenAI

from config import settings
from tools.utils import SimpleCache

logger = logging.getLogger(__name__)

MAX_ROUNDS = 7          # Máximo de rondas de tool-calls por request
LLM_TIMEOUT = 45.0      # Segundos por llamada a DeepSeek (generosa: puede tener que sintetizar mucho)

# Caché de resultados de tools (15 min TTL).
# Evita re-ejecutar las mismas queries SQL cuando se repite la misma pregunta.
# Tools excluidas: generate_forecast_report (genera un archivo nuevo cada vez).
_TOOL_CACHE = SimpleCache(ttl_seconds=900)
_NO_CACHE_TOOLS = {"generate_forecast_report"}

# ── Lazy client ────────────────────────────────────────────────────────────────

_client: Optional[AsyncOpenAI] = None


def _get_client() -> Optional[AsyncOpenAI]:
    global _client
    if not settings.deepseek_api_key:
        return None
    if _client is None:
        _client = AsyncOpenAI(
            api_key=settings.deepseek_api_key,
            base_url=settings.deepseek_base_url,   # https://api.deepseek.com/v1
            timeout=LLM_TIMEOUT,
        )
    return _client


# ── Schemas de herramientas (formato OpenAI function calling) ──────────────────
#
# Cada schema describe una herramienta de BD para que DeepSeek sepa cuándo y cómo llamarla.
# DeepSeek elige cuáles invocar y con qué params basándose en la pregunta del usuario.

TOOL_SCHEMAS = [
    {
        "type": "function",
        "function": {
            "name": "get_sales_summary",
            "description": (
                "Resumen de ventas totales, número de pedidos y clientes activos en un período. "
                "Usar cuando el usuario pregunta cuánto se vendió, facturación total, ingresos o resumen del mes."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "period": {
                        "type": "string",
                        "description": "Período YYYY-MM (mes) o YYYY (año). Ej: '2026-07'. Default: mes actual."
                    }
                },
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_gap_to_target",
            "description": (
                "Calcula cuánto falta para llegar a la meta mensual de ventas. "
                "Muestra cumplimiento %, brecha en soles y ritmo diario necesario. "
                "Usar cuando pregunten si van a llegar a la meta, cuánto falta, brecha o gap."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "year": {"type": "integer", "description": "Año. Default: año actual."},
                    "month": {"type": "integer", "description": "Mes 1-12. Default: mes actual."},
                },
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_sales_targets",
            "description": (
                "Meta de ventas (presupuesto/cuota) por tienda y vendedor para un mes. "
                "Usar cuando pregunten cuál es la meta, el objetivo o el presupuesto del mes."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "year": {"type": "integer", "description": "Año."},
                    "month": {"type": "integer", "description": "Mes 1-12."},
                },
                "required": ["year", "month"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_sales_performance",
            "description": (
                "Ranking de vendedores por ventas en un período. "
                "Muestra nombre, total vendido, pedidos y clientes por vendedor. "
                "Usar para: top vendedores, quién vendió más, rendimiento del equipo de ventas."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "period": {
                        "type": "string",
                        "description": "Período YYYY-MM. Default: mes actual."
                    }
                },
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_sales_forecast",
            "description": (
                "Detalle mes a mes de ventas HISTÓRICAS (meses ya transcurridos) en un rango de fechas. "
                "Usar para ver cómo evolucionaron las ventas reales en períodos pasados. "
                "NO usar para meses futuros — para proyecciones usar generate_forecast_report."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "start_period": {
                        "type": "string",
                        "description": "Inicio del rango YYYY-MM (mes ya pasado). Ej: '2026-01'."
                    },
                    "end_period": {
                        "type": "string",
                        "description": "Fin del rango YYYY-MM (mes ya pasado). Ej: '2026-07'."
                    },
                },
                "required": ["start_period", "end_period"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "generate_forecast_report",
            "description": (
                "Calcula la proyección (forecast) de ventas para un mes FUTURO usando tendencia de los últimos meses. "
                "Devuelve tres escenarios: conservador, base y optimista en soles. "
                "Usar cuando pidan proyecciones para septiembre, octubre, noviembre, diciembre 2026 en adelante. "
                "Si el resultado incluye 'download_url', SIEMPRE mostrar el link al usuario como: "
                "'📥 [Descargar Excel](download_url)' para que pueda abrir el reporte completo."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "year": {"type": "integer", "description": "Año del reporte."},
                    "month": {"type": "integer", "description": "Mes objetivo 1-12."},
                },
                "required": ["year", "month"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_inactive_customers",
            "description": (
                "Lista de clientes que no han comprado en N días. "
                "Usar para: clientes inactivos, perdidos, que hay que reactivar, que dejaron de comprar."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "days": {
                        "type": "integer",
                        "description": (
                            "Días sin compra. Default: 60. "
                            "Si dicen '3 meses' usar 90, '6 meses' usar 180."
                        )
                    }
                },
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_new_customers",
            "description": (
                "Clientes que compraron por primera vez en un período (nuevos clientes captados). "
                "Usar para: clientes nuevos, captación, primera compra."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "period": {
                        "type": "string",
                        "description": "Período YYYY-MM. Default: mes actual."
                    }
                },
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "search_customer_by_name",
            "description": (
                "Busca clientes por nombre/razón social O por número de documento (DNI, RUC, carnet de extranjería). "
                "Detecta automáticamente si el input es número (→ busca por documento) o texto (→ busca por nombre). "
                "Devuelve lista de clientes con código SAP, razón social, doc de identidad, compras totales y última compra. "
                "SIEMPRE usar esta tool primero cuando el usuario mencione un nombre, DNI, RUC o CE — nunca pedir el código SAP al usuario."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "name": {
                        "type": "string",
                        "description": (
                            "Nombre, fragmento de nombre, DNI, RUC o carnet de extranjería. "
                            "Ej: 'VALVOSANITARIA', 'SODIMAC', '70333796', '20601234567'."
                        )
                    },
                    "limit": {
                        "type": "integer",
                        "description": "Máximo de resultados a devolver. Default: 10."
                    },
                },
                "required": ["name"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_customer_insights",
            "description": (
                "Historial completo de UN cliente específico: transacciones, gasto total, última compra, frecuencia. "
                "REQUIERE el código numérico SAP del cliente (7-10 dígitos). "
                "Si el usuario da un nombre (no un código), usar primero search_customer_by_name para obtener el código."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "customer_id": {
                        "type": "string",
                        "description": "Código numérico SAP del cliente (7-10 dígitos). Ej: '1234567'."
                    }
                },
                "required": ["customer_id"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_sales_by_channel",
            "description": (
                "Distribución de ventas por canal comercial: Canal Moderno, Mostrador, "
                "Institucional, Tradicional, ecommerce. "
                "Muestra ventas y participación % de cada canal."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "period": {
                        "type": "string",
                        "description": "Período YYYY-MM. Default: mes actual."
                    }
                },
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_monthly_trend",
            "description": (
                "Evolución de ventas mes a mes en los últimos N meses. "
                "Calcula tendencia (creciente/decreciente), variación MoM y promedio mensual. "
                "Usar para: tendencia, cómo ha ido, historial mensual, evolución."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "months": {
                        "type": "integer",
                        "description": "Número de meses a analizar. Default: 6."
                    }
                },
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_top_margin_products",
            "description": (
                "Productos con mayor margen de ganancia o rentabilidad. "
                "Usar para: productos rentables, mejor margen, utilidad por producto."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "period": {
                        "type": "string",
                        "description": "Período YYYY-MM o YYYY (opcional)."
                    },
                    "top_n": {
                        "type": "integer",
                        "description": "Cuántos productos mostrar. Default: 10."
                    },
                    "store_code": {
                        "type": "string",
                        "description": (
                            "Código de tienda/oficina de venta (opcional). "
                            "Ej: 'SH01', 'ME10', 'SH12'. "
                            "Usar cuando pidan margen por tienda específica."
                        )
                    },
                },
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_product_sales_ranking",
            "description": (
                "Ranking de productos por ventas en soles para un período. "
                "Puede mostrar los MÁS vendidos (sort_order='DESC') O los MENOS vendidos (sort_order='ASC'). "
                "Usar para: ¿qué producto se vendió menos? ¿cuál fue el producto menos vendido? "
                "¿cuáles son los productos que más se venden? ¿qué productos tienen menor salida? "
                "PREFERIR esta herramienta sobre get_inventory_by_sales cuando se pida por período específico."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "period": {
                        "type": "string",
                        "description": "Período YYYY-MM (mes) o YYYY (año). Ej: '2026-07'."
                    },
                    "top_n": {
                        "type": "integer",
                        "description": "Cuántos productos mostrar. Default: 10."
                    },
                    "sort_order": {
                        "type": "string",
                        "enum": ["DESC", "ASC"],
                        "description": (
                            "'DESC' para los más vendidos (mayor ventas primero). "
                            "'ASC' para los menos vendidos (menor ventas primero). "
                            "Usar 'ASC' cuando pregunten por 'menos vendido', 'menor rotación', 'menor salida'."
                        )
                    },
                    "category": {
                        "type": "string",
                        "description": "Filtrar por categoría/grupo de material (opcional)."
                    },
                    "store_code": {
                        "type": "string",
                        "description": (
                            "Código de tienda/oficina de venta (opcional). "
                            "Ej: 'SH01', 'ME10', 'SH04'. "
                            "Usar cuando pidan productos por tienda específica."
                        )
                    },
                },
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_inventory_by_sales",
            "description": (
                "Materiales con mayor cantidad entregada históricamente (sin filtro de período). "
                "Usar solo cuando no se especifique período. "
                "Para consultas por período específico, preferir get_product_sales_ranking."
            ),
            "parameters": {
                "type": "object",
                "properties": {},
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_sales_by_store",
            "description": (
                "Ranking de todas las tiendas/oficinas de venta ordenadas por ventas. "
                "Muestra ventas, utilidad, margen, participación %, documentos y clientes por tienda. "
                "Usar cuando pregunten: ¿cuánto vendió cada tienda? ¿qué tienda vende más? "
                "¿cómo están las tiendas? ranking de oficinas de venta, desempeño por sucursal."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "period": {
                        "type": "string",
                        "description": (
                            "Período YYYY-MM (mes) o YYYY (año). "
                            "Sin valor = acumulado anual. Ej: '2026-07' o '2026'."
                        )
                    },
                    "top_n": {
                        "type": "integer",
                        "description": "Número de tiendas a mostrar. Default: 20."
                    },
                },
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_store_detail",
            "description": (
                "Análisis detallado de UNA tienda específica: resumen de ventas, top 5 productos "
                "y top 5 clientes de esa tienda. "
                "Usar cuando pregunten por una tienda específica: "
                "'¿cómo le fue a SOLE Trujillo?', '¿cuáles son los productos más vendidos en SH01?', "
                "'detalle de la tienda ME10', '¿cómo está la tienda de Callao?'. "
                "REQUIERE el código de tienda (ej: SH01, ME10, SH04, SH12)."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "store_code": {
                        "type": "string",
                        "description": (
                            "Código de la oficina de venta. Ej: 'SH01' (SOLE Lima), "
                            "'ME10' (OF. MT CALLAO), 'SH04' (SOLE Trujillo), 'SH12' (E-COMMERCE). "
                            "OBLIGATORIO."
                        )
                    },
                    "period": {
                        "type": "string",
                        "description": (
                            "Período YYYY-MM o YYYY. Sin valor = año actual acumulado."
                        )
                    },
                },
                "required": ["store_code"],
            },
        },
    },
    # ── Herramientas PUNTO_VENTA (Fase 0.5) ────────────────────────────────────
    {
        "type": "function",
        "function": {
            "name": "get_stock_by_product",
            "description": (
                "Consulta el stock disponible de un material/producto en tiempo real. "
                "Muestra stock libre, bloqueado, en tránsito y en control de calidad por almacén. "
                "Usar cuando pregunten: ¿cuánto stock hay de X? ¿hay disponibilidad de X? "
                "¿cuántas unidades tenemos de X? stock de un producto, inventario disponible."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "product_name": {
                        "type": "string",
                        "description": (
                            "Nombre o fragmento del material a buscar. "
                            "Ej: 'TERMA SOLE', 'COBRE 10MM', 'VALVULA'. "
                            "Usar si el usuario da el nombre del producto."
                        )
                    },
                    "product_code": {
                        "type": "string",
                        "description": (
                            "Código SAP exacto del material (opcional). "
                            "Usar si el usuario da el código exacto."
                        )
                    },
                    "center": {
                        "type": "string",
                        "description": (
                            "Código del centro/almacén SAP (opcional). "
                            "Ej: 'M310', 'G411'. Sin valor = todos los almacenes."
                        )
                    },
                    "top_n": {
                        "type": "integer",
                        "description": "Máximo de materiales a mostrar. Default: 20."
                    },
                },
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_pending_orders",
            "description": (
                "Lista pedidos bloqueados (con bloqueo de entrega o de facturación). "
                "Muestra número de pedido, fecha, tipo de bloqueo, valor neto y tienda. "
                "Usar cuando pregunten: ¿qué pedidos están bloqueados? ¿hay pedidos pendientes? "
                "¿cuánto valor tenemos en pedidos bloqueados? pedidos sin entregar, pedidos retenidos."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "days": {
                        "type": "integer",
                        "description": (
                            "Número de días hacia atrás a considerar. "
                            "Default: 90. Máximo: 365."
                        )
                    },
                    "store_code": {
                        "type": "string",
                        "description": (
                            "Código de la oficina de venta (opcional). "
                            "Ej: 'SH01', 'ME10'. Sin valor = todas las tiendas."
                        )
                    },
                    "block_type": {
                        "type": "string",
                        "enum": ["entrega", "factura"],
                        "description": (
                            "'entrega' = solo con bloqueo de entrega. "
                            "'factura' = solo con bloqueo de facturación. "
                            "Sin valor = ambos tipos de bloqueo."
                        )
                    },
                    "top_n": {
                        "type": "integer",
                        "description": "Máximo de pedidos a mostrar. Default: 30."
                    },
                },
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_returns_summary",
            "description": (
                "Resumen de devoluciones de clientes: total de solicitudes, monto devuelto "
                "y ranking de productos más devueltos. "
                "Usar cuando pregunten: ¿cuántas devoluciones hubo? ¿qué productos se devuelven más? "
                "¿cuánto perdemos en devoluciones? análisis de devoluciones, productos con más retornos."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "period": {
                        "type": "string",
                        "description": (
                            "Período YYYY-MM (mes) o YYYY (año). "
                            "Sin valor = año actual acumulado (YTD). "
                            "Ej: '2026-07', '2026', '2025'."
                        )
                    },
                    "top_n": {
                        "type": "integer",
                        "description": "Número de productos en el ranking. Default: 15."
                    },
                },
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_customer_contact",
            "description": (
                "Datos de contacto completos de un cliente: nombre, RUC/DNI, "
                "teléfono, email y dirección. "
                "Usar cuando pregunten: ¿cuál es el teléfono/email/dirección del cliente X? "
                "¿cómo contacto a X? datos de contacto de un cliente. "
                "REQUIERE el código SAP del cliente — usar search_customer_by_name primero si no se tiene."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "customer_id": {
                        "type": "string",
                        "description": (
                            "Código SAP del cliente (7-10 dígitos). "
                            "Obtenerlo con search_customer_by_name si el usuario da un nombre."
                        )
                    },
                },
                "required": ["customer_id"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_vendor_performance_vs_target",
            "description": (
                "Cumplimiento de ventas por vendedor: ventas reales vs meta estimada del mes. "
                "Calcula % de cumplimiento, gap en soles y proyección de cierre. "
                "Las metas individuales se estiman distribuyendo la meta de tienda "
                "según el share histórico del mes anterior. "
                "Usar cuando pregunten: ¿cómo van los vendedores vs su meta? "
                "¿qué vendedor está cumpliendo? ranking de cumplimiento, forecast por vendedor, "
                "quién está por debajo de la meta, desempeño individual vs objetivo."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "year": {
                        "type": "integer",
                        "description": "Año. Default: 2026."
                    },
                    "month": {
                        "type": "integer",
                        "description": "Mes (1-12). Default: mes actual."
                    },
                    "store_id": {
                        "type": "string",
                        "description": "Código de tienda (opcional). Ej: 'SH22'."
                    },
                    "top_n": {
                        "type": "integer",
                        "description": "Número de vendedores a mostrar. Default: 20."
                    },
                },
            },
        },
    },
    # ── Fase 0.6 — 8 quick wins ───────────────────────────────────────────────
    {
        "type": "function",
        "function": {
            "name": "get_open_receivables",
            "description": (
                "Lista de facturas pendientes de cobro (cuentas por cobrar abiertas). "
                "Muestra monto por cobrar, días de antigüedad y quién debe. "
                "Usar cuando pregunten: ¿cuánto nos deben? ¿qué clientes tienen facturas pendientes? "
                "¿cuánto hay vencido? cartera vencida, cuentas por cobrar, morosidad."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "customer_id": {
                        "type": "string",
                        "description": "Código SAP del cliente (opcional). Sin valor = todos los clientes."
                    },
                    "days_overdue": {
                        "type": "integer",
                        "description": "Mostrar solo documentos con N+ días vencidos (opcional). Ej: 30, 60, 90."
                    },
                    "top_n": {
                        "type": "integer",
                        "description": "Máximo de documentos. Default: 30."
                    },
                },
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_customer_credit",
            "description": (
                "Límite de crédito, monto utilizado y disponible de un cliente. "
                "Usar cuando pregunten: ¿cuánto crédito tiene disponible el cliente X? "
                "¿está bloqueado? ¿cuál es su límite? ¿cuándo pagó por última vez? "
                "REQUIERE código SAP del cliente."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "customer_id": {
                        "type": "string",
                        "description": "Código SAP del cliente (7-10 dígitos)."
                    },
                },
                "required": ["customer_id"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_customer_price",
            "description": (
                "Precios especiales negociados para un cliente en el punto de venta. "
                "Usar cuando pregunten: ¿a qué precio le vendemos X a este cliente? "
                "¿qué precio especial tiene? ¿cuánto cuesta para el cliente Y? "
                "REQUIERE código SAP del cliente."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "customer_id": {
                        "type": "string",
                        "description": "Código SAP del cliente."
                    },
                    "product_name": {
                        "type": "string",
                        "description": "Nombre o fragmento del producto (opcional). Ej: 'TERMA', 'CALEFON'."
                    },
                    "product_code": {
                        "type": "string",
                        "description": "Código SAP exacto del material (opcional). Ej: 'RU-REZ20I'."
                    },
                    "top_n": {
                        "type": "integer",
                        "description": "Máximo de materiales. Default: 20."
                    },
                },
                "required": ["customer_id"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_clients_by_store",
            "description": (
                "Lista de clientes asignados a una tienda/oficina de venta o zona. "
                "Muestra la cartera de clientes por punto de venta. "
                "Usar cuando pregunten: ¿qué clientes tiene la tienda X? "
                "¿quiénes están en la zona Y? cartera de clientes de una oficina."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "store_code": {
                        "type": "string",
                        "description": "Código de la oficina de venta. Ej: 'ME10', 'SH01', 'AR01'."
                    },
                    "zone": {
                        "type": "string",
                        "description": "Código de zona de ventas (opcional). Ej: '15', '22'."
                    },
                    "top_n": {
                        "type": "integer",
                        "description": "Máximo de clientes. Default: 50."
                    },
                },
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_service_orders",
            "description": (
                "Historial de órdenes de servicio técnico: instalaciones, reparaciones y mantenimientos. "
                "Usar cuando pregunten: ¿qué servicios tuvo el cliente X? ¿cuántas instalaciones hubo? "
                "¿qué técnico atendió? historial de servicio técnico, fallas reportadas, garantías."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "customer_doc": {
                        "type": "string",
                        "description": "DNI, RUC u otro documento del cliente (opcional)."
                    },
                    "product_name": {
                        "type": "string",
                        "description": "Nombre o fragmento del producto (opcional). Ej: 'TERMA', 'CALEFON'."
                    },
                    "state": {
                        "type": "string",
                        "description": "Estado del servicio (opcional). Ej: 'COMPLETADA', 'PENDIENTE', 'ANULADA'."
                    },
                    "days": {
                        "type": "integer",
                        "description": "Días hacia atrás a consultar. Default: 90."
                    },
                    "top_n": {
                        "type": "integer",
                        "description": "Máximo de órdenes. Default: 20."
                    },
                },
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_delivery_status",
            "description": (
                "Estado actual de entregas y despachos (sistema Beetrack). "
                "Permite rastrear si un pedido fue entregado, está en ruta o falló. "
                "Usar cuando pregunten: ¿llegó el pedido X? ¿en qué estado está el envío? "
                "¿fue entregado el despacho Y? tracking de entrega, seguimiento de pedidos."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "order_number": {
                        "type": "string",
                        "description": "Número de pedido SAP. Ej: '7501653027'."
                    },
                    "guide_number": {
                        "type": "string",
                        "description": "Número de guía de remisión (opcional)."
                    },
                    "customer_name": {
                        "type": "string",
                        "description": "Nombre o fragmento del destinatario (opcional)."
                    },
                    "days": {
                        "type": "integer",
                        "description": "Días hacia atrás a buscar. Default: 30."
                    },
                    "top_n": {
                        "type": "integer",
                        "description": "Máximo de despachos. Default: 20."
                    },
                },
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_inventory_value",
            "description": (
                "Valor económico del inventario en soles por material y centro de valoración. "
                "Usar cuando pregunten: ¿cuánto vale el inventario? ¿qué productos tienen mayor stock en valor? "
                "valorización de inventario, stock valorizado, inversión en inventario."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "center": {
                        "type": "string",
                        "description": "Centro/ámbito de valoración SAP (opcional). Ej: 'M310', 'G411'."
                    },
                    "product_name": {
                        "type": "string",
                        "description": "Nombre o fragmento del material (opcional)."
                    },
                    "top_n": {
                        "type": "integer",
                        "description": "Top N materiales por valor. Default: 20."
                    },
                },
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_nps_summary",
            "description": (
                "Resumen del Net Promoter Score (NPS) de satisfacción de clientes. "
                "Calcula promotores (9-10), pasivos (7-8), detractores (0-6) y score final. "
                "Usar cuando pregunten: ¿cómo está la satisfacción del cliente? ¿cuál es el NPS? "
                "¿qué dicen los clientes? satisfacción, encuestas, NPS, comentarios de clientes."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "period": {
                        "type": "string",
                        "description": (
                            "Período a analizar: YYYY-MM (mes) o YYYY (año). "
                            "Sin valor = año actual. Ej: '2026-07', '2026'."
                        )
                    },
                    "top_n": {
                        "type": "integer",
                        "description": "Número de comentarios recientes a incluir. Default: 10."
                    },
                },
            },
        },
    },
    # ── Fase 0.7 — nuevas herramientas analíticas ──────────────────────────────
    {
        "type": "function",
        "function": {
            "name": "get_customer_products",
            "description": (
                "Productos o categorías que ha comprado un cliente específico. "
                "Útil para detectar oportunidades de cross-sell y upsell: qué líneas consume, "
                "cuánto gasta en cada producto, cuántas veces lo ha pedido y cuándo fue la última compra. "
                "Usar cuando pregunten: ¿qué productos compra X cliente? ¿qué le podemos ofrecer a X? "
                "¿en qué categorías participa X? ¿qué consume el cliente? cross-sell, portafolio del cliente."
            ),
            "parameters": {
                "type": "object",
                "required": ["customer_id"],
                "properties": {
                    "customer_id": {
                        "type": "string",
                        "description": "Código SAP del solicitante (VC_solicitante_codigo). Usar search_customer_by_name primero si solo se conoce el nombre."
                    },
                    "period": {
                        "type": "string",
                        "description": "Período: YYYY-MM (mes) o YYYY (año). Sin valor = histórico completo."
                    },
                    "top_n": {
                        "type": "integer",
                        "description": "Top N productos/categorías por ventas. Default: 20."
                    },
                    "group_by": {
                        "type": "string",
                        "enum": ["producto", "categoria"],
                        "description": "'producto' agrupa por código de material; 'categoria' agrupa por directorio de producto. Default: 'producto'."
                    },
                },
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_discount_analysis",
            "description": (
                "Análisis de descuentos aplicados: porcentaje promedio de descuento por vendedor o cliente. "
                "Muestra quién da más descuento, cuánto se está cediendo en precio y el impacto en facturación. "
                "Usar cuando pregunten: ¿cuánto descuento está dando X vendedor? ¿quiénes tienen mayor descuento? "
                "¿cuál es el descuento promedio? descuentos, política de precios, margen de precio."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "period": {
                        "type": "string",
                        "description": "Período: YYYY-MM o YYYY. Sin valor = mes actual."
                    },
                    "vendor_id": {
                        "type": "string",
                        "description": "Filtrar por código de vendedor (opcional)."
                    },
                    "customer_id": {
                        "type": "string",
                        "description": "Filtrar por código SAP de cliente (opcional)."
                    },
                    "top_n": {
                        "type": "integer",
                        "description": "Top N resultados. Default: 20."
                    },
                    "group_by": {
                        "type": "string",
                        "enum": ["vendedor", "cliente"],
                        "description": "'vendedor' agrupa por vendedor; 'cliente' agrupa por cliente. Default: 'vendedor'."
                    },
                },
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_real_margin",
            "description": (
                "Margen real de ventas usando costo real del producto (DE_costo_real). "
                "Calcula margen en soles y porcentaje por vendedor, categoría o producto. "
                "Más preciso que el margen de precio porque refleja el costo real incurrido. "
                "Usar cuando pregunten: ¿cuál es el margen real? ¿cuánto ganamos en X categoría? "
                "¿qué vendedor vende con más margen? rentabilidad real, ganancia, margen de contribución."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "period": {
                        "type": "string",
                        "description": "Período: YYYY-MM o YYYY. Sin valor = mes actual."
                    },
                    "vendor_id": {
                        "type": "string",
                        "description": "Filtrar por código de vendedor (opcional)."
                    },
                    "category": {
                        "type": "string",
                        "description": "Filtrar por categoría/directorio de producto (opcional)."
                    },
                    "top_n": {
                        "type": "integer",
                        "description": "Top N resultados. Default: 20."
                    },
                    "group_by": {
                        "type": "string",
                        "enum": ["vendedor", "categoria", "producto"],
                        "description": "Agrupar por vendedor, categoría o producto. Default: 'vendedor'."
                    },
                },
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_sales_by_geography",
            "description": (
                "Ventas desagregadas por ubicación geográfica del cliente: departamento, provincia o distrito. "
                "Muestra dónde están concentradas las ventas y qué regiones tienen mayor potencial. "
                "Usar cuando pregunten: ¿de qué regiones son nuestros clientes? ¿dónde vendemos más? "
                "¿cuánto facturamos en Lima? ventas por región, departamento, provincia, geografía, mapa de ventas."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "period": {
                        "type": "string",
                        "description": "Período: YYYY-MM o YYYY. Sin valor = mes actual."
                    },
                    "level": {
                        "type": "string",
                        "enum": ["departamento", "provincia", "distrito"],
                        "description": "Nivel geográfico de agrupación. Default: 'departamento'."
                    },
                    "top_n": {
                        "type": "integer",
                        "description": "Top N ubicaciones por ventas. Default: 20."
                    },
                },
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_customer_pareto",
            "description": (
                "Análisis Pareto (80/20) de clientes: clasifica en Clase A (top 80% de ventas), "
                "Clase B (siguiente 15%) y Clase C (último 5%). Muestra la concentración de la cartera "
                "y cuántos clientes generan la mayor parte del negocio. "
                "Usar cuando pregunten: ¿cuántos clientes son clave? ¿cuál es el 80/20 de clientes? "
                "¿quiénes son los clientes A? Pareto, concentración de cartera, clientes importantes."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "period": {
                        "type": "string",
                        "description": "Período: YYYY-MM o YYYY. Sin valor = mes actual."
                    },
                    "top_n": {
                        "type": "integer",
                        "description": "Número de clientes a evaluar en el ranking. Default: 50."
                    },
                    "vendor_id": {
                        "type": "string",
                        "description": "Filtrar por cartera de un vendedor específico (opcional)."
                    },
                },
            },
        },
    },
]

# Set de nombres válidos (para validación rápida)
ALL_TOOL_NAMES = {s["function"]["name"] for s in TOOL_SCHEMAS}


# ── System prompt del agente ───────────────────────────────────────────────────

def _build_system_prompt() -> str:
    now = datetime.now()
    prev_month = now.month - 1 or 12
    prev_year = now.year if now.month > 1 else now.year - 1

    return f"""Eres SOLE, el asistente de inteligencia artificial de ventas de MT Industrial (empresa industrial peruana).

📅 Fecha actual: {now.strftime('%d/%m/%Y')} | Mes actual: {now.year}-{now.month:02d} | Mes pasado: {prev_year}-{prev_month:02d}

## Tu misión
Responder preguntas sobre ventas, clientes e inventario usando datos reales de la base de datos. \
Funcionar como un analista de ventas inteligente: no solo dar datos, sino interpretarlos y \
dar contexto útil para la toma de decisiones.

## Cómo trabajar
1. Analiza la pregunta con detenimiento para entender qué información necesitas.
2. Llama a las herramientas necesarias — puedes llamar varias si la pregunta lo requiere.
3. Lee los resultados y sintetiza una respuesta analítica, clara y útil en español.
4. Si los datos revelan algo importante (caída, incumplimiento, patrón), señálalo proactivamente.
5. Si no tienes herramientas para responder, sé honesto sobre las limitaciones.

## Reglas CRÍTICAS
- 🔒 SOLO LECTURA: nunca ejecutes escrituras ni modificaciones de datos.
- 🇵🇪 Responde SIEMPRE en español.
- 📊 Sé analítico: no copies los datos crudos, interprértalos y da contexto.
- ✅ No inventes datos. Si una herramienta no devuelve resultados, dilo.
- 🔍 BÚSQUEDA DE CLIENTES — regla obligatoria: si el usuario menciona un cliente por nombre, razón social o RUC/DNI (en lugar de dar el código SAP directamente), USA SIEMPRE search_customer_by_name PRIMERO para obtener el código SAP. Luego usa ese código en la tool correspondiente: get_customer_insights, get_customer_credit, get_customer_price, get_open_receivables, get_customer_contact, get_service_orders o cualquier otra que pida customer_id. NUNCA le pidas el código SAP al usuario — encuéntralo tú. Si la búsqueda devuelve varios candidatos, usa el que tenga mayor total_compras. Si la búsqueda devuelve match_type "aproximado", menciona brevemente que encontraste al cliente por similitud de nombre.

## Limitaciones del sistema (lo que NO puedes responder con datos)
- Forecast a nivel de producto individual (solo existe a nivel total de ventas)
- Comparación contra competencia
- Precios de productos o cotizaciones
- Información de proveedores
- Datos de recursos humanos o nómina
- Tipo de cambio o cotización del dólar

Cuando pregunten por algo en esa lista, explícalo amablemente con una o dos oraciones y sugiere \
lo que sí puedes mostrar.

## Estilo de respuesta
- Usa emojis con moderación (📊 ✅ ⚠️ 📈 📉 🏆) para mejorar la legibilidad
- Formato: listas cuando hay múltiples ítems, párrafos cuando es análisis
- Siempre menciona el período o contexto de los datos
- Montos en soles (S/) con separador de miles
- Cuando los datos son parciales o pueden tener limitaciones, indícalo brevemente"""


# ── Resultado del agente ───────────────────────────────────────────────────────

@dataclass
class AgentResult:
    response: str
    tools_used: List[str] = field(default_factory=list)
    error: Optional[str] = None


# ── Loop principal ─────────────────────────────────────────────────────────────

async def run_agent(
    question: str,
    tool_registry: Dict[str, Any],
    allowed_tools: Optional[List[str]] = None,
) -> AgentResult:
    """
    Ejecuta el loop agéntico: DeepSeek decide qué consultar, ejecutamos, sintetiza respuesta.

    Args:
        question:      Pregunta en lenguaje natural del usuario.
        tool_registry: Diccionario {tool_name: callable_async} con las herramientas de BD.
        allowed_tools: Lista de herramientas que el rol del usuario puede usar.
                       None = todas las herramientas disponibles.

    Returns:
        AgentResult con el texto de respuesta y las herramientas que se invocaron.
    """
    client = _get_client()
    if not client:
        return AgentResult(
            response=(
                "El sistema de IA no está configurado. "
                "Contacta al administrador para verificar la API key."
            ),
            error="DEEPSEEK_API_KEY not configured",
        )

    # Filtrar schemas por RBAC
    if allowed_tools is not None:
        available_schemas = [
            s for s in TOOL_SCHEMAS
            if s["function"]["name"] in allowed_tools
        ]
    else:
        available_schemas = TOOL_SCHEMAS

    messages = [
        {"role": "system", "content": _build_system_prompt()},
        {"role": "user", "content": question},
    ]

    tools_called: List[str] = []

    for round_num in range(MAX_ROUNDS):
        logger.info(f"[Agent] Round {round_num + 1}/{MAX_ROUNDS} — question: '{question[:80]}'")

        try:
            api_response = await client.chat.completions.create(
                model="deepseek-chat",
                messages=messages,
                tools=available_schemas or None,
                tool_choice="auto",
                temperature=0.3,
                max_tokens=1500,
            )
        except Exception as exc:
            logger.error(f"[Agent] DeepSeek API error on round {round_num + 1}: {exc}")
            return AgentResult(
                response=(
                    "Ocurrió un error conectando con el sistema de IA. "
                    "Por favor intenta en unos segundos."
                ),
                tools_used=tools_called,
                error=str(exc),
            )

        choice = api_response.choices[0]
        finish_reason = choice.finish_reason

        # ── DeepSeek quiere llamar herramientas ────────────────────────────────
        if finish_reason == "tool_calls":
            tool_calls = choice.message.tool_calls or []
            # Adjuntar el mensaje del assistant (con sus tool_calls) al historial
            messages.append(choice.message)

            # Parsear todos los tool calls primero
            parsed: List[tuple] = []
            for tc in tool_calls:
                try:
                    fn_args = json.loads(tc.function.arguments or "{}")
                except json.JSONDecodeError:
                    fn_args = {}
                parsed.append((tc, tc.function.name, fn_args))
                logger.info(f"[Agent] → Tool call: {tc.function.name}({fn_args})")

            # Ejecutar todas las herramientas EN PARALELO con asyncio.gather
            async def _run_tool(tc, fn_name: str, fn_args: dict) -> tuple:
                """Ejecuta una herramienta y devuelve (tool_call_id, result_json).
                Usa caché de 15 min para evitar queries SQL duplicadas.
                """
                if fn_name not in tool_registry:
                    result = {"error": f"Herramienta '{fn_name}' no existe en el sistema."}
                elif allowed_tools is not None and fn_name not in allowed_tools:
                    result = {"error": f"Sin permiso para acceder a '{fn_name}'."}
                else:
                    # Intentar caché (excepto tools que no deben cachearse)
                    cache_key = f"{fn_name}:{json.dumps(fn_args, sort_keys=True, default=str)}"
                    cached_result = None if fn_name in _NO_CACHE_TOOLS else _TOOL_CACHE.get(cache_key)

                    if cached_result is not None:
                        logger.info(f"[Agent] ← {fn_name} (caché hit)")
                        tools_called.append(fn_name)
                        result = cached_result
                    else:
                        try:
                            raw = await tool_registry[fn_name](**fn_args)
                            tools_called.append(fn_name)
                            logger.debug(f"[Agent] ← {fn_name} OK")
                            if fn_name not in _NO_CACHE_TOOLS:
                                _TOOL_CACHE.set(cache_key, raw)
                            result = raw
                        except Exception as exc:
                            logger.error(f"[Agent] Tool {fn_name} raised: {exc}")
                            result = {"error": f"Error al ejecutar {fn_name}: {exc}"}
                return tc.id, json.dumps(result, ensure_ascii=False, default=str)

            results = await asyncio.gather(*[_run_tool(tc, fn, args) for tc, fn, args in parsed])

            for tool_call_id, result_json in results:
                messages.append({
                    "role": "tool",
                    "tool_call_id": tool_call_id,
                    "content": result_json,
                })

            # Continuar loop — en la siguiente ronda DeepSeek sintetiza con los datos
            continue

        # ── DeepSeek generó respuesta de texto (done) ─────────────────────────
        final_text = (choice.message.content or "").strip()

        if not final_text:
            final_text = "No pude generar una respuesta. Por favor reformula tu pregunta."

        logger.info(
            f"[Agent] Done after {round_num + 1} rounds. "
            f"Tools used: {tools_called}. "
            f"Response length: {len(final_text)} chars."
        )

        return AgentResult(
            response=final_text,
            tools_used=list(dict.fromkeys(tools_called)),  # Deduplicar, mantener orden
        )

    # ── Límite de rondas alcanzado ─────────────────────────────────────────────
    logger.warning(f"[Agent] MAX_ROUNDS ({MAX_ROUNDS}) reached for question: '{question[:80]}'")
    return AgentResult(
        response=(
            "Alcancé el límite de consultas para procesar esta pregunta. "
            "Por favor intenta reformularla de forma más específica."
        ),
        tools_used=tools_called,
        error="MAX_ROUNDS exceeded",
    )


# ── Mensajes de estado para streaming ─────────────────────────────────────────
#
# Aparecen en el chat MIENTRAS el agente ejecuta cada tool.
# El usuario ve progreso en tiempo real en vez del punto blanco.

_TOOL_STATUS: Dict[str, str] = {
    "search_customer_by_name":   "🔍 Buscando cliente en la base de datos...",
    "get_customer_insights":     "📋 Consultando historial del cliente...",
    "get_customer_credit":       "💳 Consultando límite de crédito...",
    "get_customer_price":        "🏷️ Consultando precios especiales...",
    "get_customer_contact":      "📞 Consultando datos de contacto...",
    "get_open_receivables":      "📑 Consultando cuentas por cobrar...",
    "get_clients_by_store":      "🏪 Consultando cartera de tienda...",
    "get_service_orders":        "🔧 Consultando órdenes de servicio técnico...",
    "get_delivery_status":       "🚚 Consultando estado de entregas...",
    "get_inventory_value":       "📦 Consultando valorización de inventario...",
    "get_nps_summary":           "⭐ Consultando encuestas de satisfacción...",
    "get_stock_by_product":      "📦 Consultando stock del producto...",
    "get_pending_orders":        "📋 Consultando pedidos pendientes...",
    "get_returns_summary":       "🔄 Consultando devoluciones...",
    "get_sales_summary":         "📊 Consultando resumen de ventas...",
    "get_sales_targets":         "🎯 Consultando metas de venta...",
    "get_sales_forecast":        "📈 Consultando forecast...",
    "get_sales_performance":     "🏆 Consultando rendimiento de vendedores...",
    "get_customer_insights":     "📋 Consultando historial del cliente...",
    "get_inventory_by_sales":    "📦 Consultando inventario...",
    "get_gap_to_target":         "📊 Calculando brecha a la meta...",
    "get_inactive_customers":    "😴 Buscando clientes inactivos...",
    "get_new_customers":         "🌟 Consultando nuevos clientes...",
    "get_top_margin_products":   "💰 Consultando productos con mejor margen...",
    "get_product_sales_ranking": "🏅 Consultando ranking de productos...",
    "get_monthly_trend":         "📈 Consultando tendencia mensual...",
    "get_sales_by_channel":      "📢 Consultando ventas por canal...",
    "get_sales_by_store":        "🏪 Consultando ventas por tienda...",
    "get_store_detail":          "🏪 Consultando detalle de tienda...",
    "get_vendor_performance_vs_target": "📊 Calculando cumplimiento por vendedor...",
    "generate_forecast_report":         "📊 Generando reporte de forecast...",
    # Fase 0.7
    "get_customer_products":    "🛍️ Consultando productos del cliente...",
    "get_discount_analysis":    "💹 Analizando descuentos...",
    "get_real_margin":          "📊 Calculando margen real...",
    "get_sales_by_geography":   "🗺️ Analizando ventas por región...",
    "get_customer_pareto":      "🏆 Calculando análisis Pareto de clientes...",
}


async def run_agent_streaming(
    question: str,
    tool_registry: Dict[str, Any],
    allowed_tools: Optional[List[str]] = None,
) -> AsyncGenerator[Tuple[str, str], None]:
    """
    Versión streaming del agente agéntico.

    Emite tuplas (tipo, contenido) durante la ejecución:
      ("status",   "🔍 Buscando cliente...")  — antes de ejecutar cada tool
      ("response", "El crédito disponible...") — respuesta final del LLM
      ("error",    "mensaje")                  — si falla algo crítico

    Permite al frontend mostrar progreso en tiempo real mientras el agente
    consulta las bases de datos, eliminando el "punto blanco" de espera.
    """
    client = _get_client()
    if not client:
        yield ("error", "El sistema de IA no está configurado. Contacta al administrador.")
        return

    # Filtrar schemas por RBAC
    if allowed_tools is not None:
        available_schemas = [
            s for s in TOOL_SCHEMAS
            if s["function"]["name"] in allowed_tools
        ]
    else:
        available_schemas = TOOL_SCHEMAS

    messages = [
        {"role": "system", "content": _build_system_prompt()},
        {"role": "user", "content": question},
    ]

    tools_called: List[str] = []

    for round_num in range(MAX_ROUNDS):
        logger.info(f"[AgentStream] Round {round_num + 1}/{MAX_ROUNDS}")

        try:
            api_response = await client.chat.completions.create(
                model="deepseek-chat",
                messages=messages,
                tools=available_schemas or None,
                tool_choice="auto",
                temperature=0.3,
                max_tokens=1500,
            )
        except Exception as exc:
            logger.error(f"[AgentStream] DeepSeek API error: {exc}")
            yield ("error", "Ocurrió un error conectando con el sistema de IA. Intenta de nuevo.")
            return

        choice = api_response.choices[0]
        finish_reason = choice.finish_reason

        if finish_reason == "tool_calls":
            tool_calls = choice.message.tool_calls or []
            messages.append(choice.message)

            parsed: List[tuple] = []
            for tc in tool_calls:
                try:
                    fn_args = json.loads(tc.function.arguments or "{}")
                except json.JSONDecodeError:
                    fn_args = {}
                parsed.append((tc, tc.function.name, fn_args))

                # Emitir status ANTES de ejecutar la tool
                status_msg = _TOOL_STATUS.get(
                    tc.function.name,
                    f"⚙️ Consultando {tc.function.name.replace('_', ' ')}..."
                )
                yield ("status", status_msg)
                logger.info(f"[AgentStream] → {tc.function.name}({fn_args})")

            # Ejecutar tools en paralelo
            async def _run_tool_stream(tc, fn_name: str, fn_args: dict) -> tuple:
                if fn_name not in tool_registry:
                    result = {"error": f"Herramienta '{fn_name}' no existe."}
                elif allowed_tools is not None and fn_name not in allowed_tools:
                    result = {"error": f"Sin permiso para '{fn_name}'."}
                else:
                    cache_key = f"{fn_name}:{json.dumps(fn_args, sort_keys=True, default=str)}"
                    cached = None if fn_name in _NO_CACHE_TOOLS else _TOOL_CACHE.get(cache_key)
                    if cached is not None:
                        tools_called.append(fn_name)
                        result = cached
                    else:
                        try:
                            raw = await tool_registry[fn_name](**fn_args)
                            tools_called.append(fn_name)
                            if fn_name not in _NO_CACHE_TOOLS:
                                _TOOL_CACHE.set(cache_key, raw)
                            result = raw
                        except Exception as exc:
                            logger.error(f"[AgentStream] Tool {fn_name} error: {exc}")
                            result = {"error": f"Error al ejecutar {fn_name}: {exc}"}
                return tc.id, json.dumps(result, ensure_ascii=False, default=str)

            results = await asyncio.gather(*[_run_tool_stream(tc, fn, args) for tc, fn, args in parsed])

            for tool_call_id, result_json in results:
                messages.append({
                    "role": "tool",
                    "tool_call_id": tool_call_id,
                    "content": result_json,
                })
            continue

        # Respuesta final
        final_text = (choice.message.content or "").strip()
        if not final_text:
            final_text = "No pude generar una respuesta. Por favor reformula tu pregunta."

        logger.info(
            f"[AgentStream] Done after {round_num + 1} rounds. "
            f"Tools: {tools_called}. Chars: {len(final_text)}"
        )
        yield ("response", final_text)
        return

    yield ("error", "Alcancé el límite de consultas. Por favor reformula tu pregunta.")
