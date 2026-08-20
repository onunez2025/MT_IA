# backend/tools/utils.py
import logging
from typing import Dict, List, Any, Optional
from datetime import datetime

logger = logging.getLogger(__name__)

# ── Corrección de signo en SAP.SD_VENTAS ──────────────────────────────────────
# Los créditos/cancelaciones (ZNCV, ZNCD, S1, S2) se almacenan con DE_neto
# POSITIVO en la tabla, igual que las ventas reales. Para calcular ventas netas
# correctas hay que invertirles el signo. Los traslados gratuitos (ZTG*) y los
# registros legacy (F2) se excluyen (contribuyen 0).
#
# Uso: SUM({NETO_SQL}) AS ventas   — en lugar de SUM(DE_neto)
#      AVG({AVG_NETO_SQL}) AS avg  — en lugar de AVG(DE_neto) para tickets promedio
#
_CLASES_POSITIVAS = frozenset({'ZPEF', 'ZPEB', 'ZNDV', 'ZEXP'})
_CLASES_NEGATIVAS = frozenset({'ZNCV', 'ZNCD', 'S1', 'S2'})

NETO_SQL = (
    "CASE "
    "WHEN VC_documento_pago_clase IN ('ZPEF','ZPEB','ZNDV','ZEXP') THEN  DE_neto "
    "WHEN VC_documento_pago_clase IN ('ZNCV','ZNCD','S1','S2')     THEN -DE_neto "
    "ELSE 0 END"
)

# Para AVG: solo promedia las transacciones de venta real (NULLs excluidos automáticamente)
AVG_NETO_SQL = (
    "CASE "
    "WHEN VC_documento_pago_clase IN ('ZPEF','ZPEB','ZNDV','ZEXP') THEN DE_neto "
    "END"
)


def aggregate_sales_data(rows: List[Dict[str, Any]]) -> Dict[str, Any]:
    """Pre-aggregate sales query results (SUM, COUNT, AVG).
    Never passes raw rows to LLM — always returns aggregated metrics.
    """
    if not rows:
        return {
            "total_sales": 0.0,
            "num_orders": 0,
            "num_customers": 0,
            "avg_order_value": 0.0
        }

    def _neto(r: Dict[str, Any]) -> float:
        clase = (r.get("VC_documento_pago_clase") or "").upper()
        neto  = float(r.get("DE_neto") or 0)
        if clase in _CLASES_POSITIVAS:
            return neto
        if clase in _CLASES_NEGATIVAS:
            return -neto
        return 0.0   # ZTG* y otros excluidos

    total_sales = sum(_neto(r) for r in rows)
    num_orders = len(rows)
    customer_codes = {r.get("VC_solicitante_codigo") for r in rows if r.get("VC_solicitante_codigo")}
    num_customers = len(customer_codes)
    avg_order_value = total_sales / num_orders if num_orders > 0 else 0.0

    return {
        "total_sales": round(total_sales, 2),
        "num_orders": num_orders,
        "num_customers": num_customers,
        "avg_order_value": round(avg_order_value, 2)
    }


def format_currency(value: float, currency: str = "PEN") -> str:
    """Format currency for display in Spanish."""
    symbol = "S/" if currency == "PEN" else "$"
    return f"{symbol} {value:,.2f}"


def format_percentage(value: float) -> str:
    """Format percentage for display."""
    return f"{value:.2f}%"


class SimpleCache:
    """Simple in-memory cache with TTL (thread-unsafe, single-process use)."""

    def __init__(self, ttl_seconds: int = 3600):
        self._cache: Dict[str, tuple] = {}
        self.ttl_seconds = ttl_seconds

    def get(self, key: str) -> Optional[Any]:
        if key not in self._cache:
            return None
        value, ts = self._cache[key]
        if datetime.now().timestamp() - ts > self.ttl_seconds:
            del self._cache[key]
            return None
        return value

    def set(self, key: str, value: Any) -> None:
        self._cache[key] = (value, datetime.now().timestamp())

    def clear(self) -> None:
        self._cache.clear()

    def size(self) -> int:
        return len(self._cache)


# Global cache instance (1 hour TTL)
query_cache = SimpleCache(ttl_seconds=3600)
