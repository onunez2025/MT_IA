# backend/guards/rbac.py
import logging
from typing import List, Dict

logger = logging.getLogger(__name__)

# RBAC permissions matrix — maps role → allowed tools
_VENDEDOR_TOOLS = [
    "get_sales_summary",
    "get_sales_targets",
    "get_customer_insights",
    # Nuevas Fase 0+ — acceso para Vendedor
    "get_gap_to_target",
    "get_inactive_customers",
    "get_new_customers",
]

_JEFE_TOOLS = _VENDEDOR_TOOLS + [
    "get_sales_forecast",
    "get_sales_performance",
    "get_inventory_by_sales",
    # Nuevas Fase 0+ — acceso solo Jefe/Gerente/Admin
    "get_sales_by_channel",
    "get_monthly_trend",
    "get_top_margin_products",
    "generate_forecast_report",
]

ROLE_PERMISSIONS: Dict[str, List[str]] = {
    "Vendedor":    _VENDEDOR_TOOLS,
    "Jefe_Ventas": _JEFE_TOOLS,
    "Gerente":     _JEFE_TOOLS,
    "Admin":       _JEFE_TOOLS,
    "Guest":       [],
}

ALL_TOOLS = set(_JEFE_TOOLS)


def validate_rbac(user_roles: List[str], tool_name: str) -> bool:
    """
    Check if any of the user's roles grant access to the requested tool.

    Args:
        user_roles: List of roles from Entra ID (e.g. ["Vendedor"])
        tool_name: Name of the tool being requested

    Returns:
        True if access granted, False otherwise
    """
    if not user_roles:
        logger.warning(f"RBAC DENIED: no roles for tool={tool_name}")
        return False

    for role in user_roles:
        allowed = ROLE_PERMISSIONS.get(role, [])
        if tool_name in allowed:
            logger.info(f"RBAC GRANTED: role={role} tool={tool_name}")
            return True

    logger.warning(f"RBAC DENIED: roles={user_roles} tool={tool_name}")
    return False


def get_allowed_tools(user_roles: List[str]) -> List[str]:
    """Return deduplicated list of tools the user can access."""
    allowed = set()
    for role in user_roles:
        allowed.update(ROLE_PERMISSIONS.get(role, []))
    return sorted(allowed)
