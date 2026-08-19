# backend/guards/sanitization.py
import re
import logging
from typing import Optional

logger = logging.getLogger(__name__)

# Tools allowed — Fase 0 originales + 7 nuevas Fase 0+
VALID_TOOLS = {
    # Fase 0 originales
    "get_sales_summary",
    "get_sales_targets",
    "get_sales_forecast",
    "get_customer_insights",
    "get_sales_performance",
    "get_inventory_by_sales",
    # Fase 0+ nuevas
    "get_gap_to_target",
    "get_inactive_customers",
    "get_sales_by_channel",
    "get_monthly_trend",
    "get_new_customers",
    "get_top_margin_products",
    "generate_forecast_report",
}

# Patterns that should never appear in user input
_DANGEROUS_PATTERNS = re.compile(
    r"(DROP|DELETE|INSERT|UPDATE|TRUNCATE|ALTER|EXEC|EXECUTE|GRANT|REVOKE|CREATE|--)",
    re.IGNORECASE,
)


def validate_tool_name(tool_name: str) -> bool:
    """Return True if tool_name is a known, allowed tool."""
    return tool_name in VALID_TOOLS


def sanitize_user_input(text: str, max_length: int = 500) -> str:
    """
    Sanitize free-text user input:
    - Truncate to max_length
    - Remove dangerous SQL/command patterns
    - Strip leading/trailing whitespace
    """
    if not text:
        return ""

    # Truncate
    text = text[:max_length]

    # Warn on dangerous patterns (don't silently drop — log it)
    if _DANGEROUS_PATTERNS.search(text):
        logger.warning(f"SANITIZE: dangerous pattern detected in input: {text[:100]!r}")

    return text.strip()
