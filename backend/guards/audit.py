# backend/guards/audit.py
import json
import logging
from datetime import datetime
from typing import Optional, List, Dict, Any

from models.audit import AuditLog

logger = logging.getLogger(__name__)

# In-memory audit store for Fase 0 (replace with DB in Fase 1)
_audit_log: List[Dict[str, Any]] = []


def log_audit_entry(
    user_id: str,
    user_roles: List[str],
    tool_name: str,
    parameters: Dict[str, Any],
    status: str,  # "SUCCESS" | "BLOCKED" | "ERROR"
    result_row_count: int = 0,
    tokens_used: Optional[int] = None,
    response_time_ms: float = 0.0,
    ip_address: str = "unknown",
) -> AuditLog:
    """
    Log an audit entry for every query attempt.
    Every query is logged regardless of outcome (SUCCESS, BLOCKED, ERROR).
    """
    entry = AuditLog(
        timestamp=datetime.utcnow(),
        user_id=user_id,
        user_roles=user_roles,
        tool_name=tool_name,
        parameters=parameters,
        status=status,
        result_row_count=result_row_count,
        tokens_used=tokens_used,
        response_time_ms=response_time_ms,
        ip_address=ip_address,
    )

    # Log to structured logger
    logger.info(
        "AUDIT",
        extra={
            "user_id": user_id,
            "tool": tool_name,
            "status": status,
            "response_ms": response_time_ms,
            "tokens": tokens_used,
        },
    )

    # Store in memory (Fase 0)
    _audit_log.append(entry.model_dump())

    return entry


def get_audit_log(limit: int = 100) -> List[Dict[str, Any]]:
    """Return recent audit entries (admin use)."""
    return _audit_log[-limit:]


def clear_audit_log() -> None:
    """Clear in-memory log (for testing)."""
    _audit_log.clear()


class AuditLogger:
    """Context manager / helper for structured audit logging."""

    def __init__(
        self,
        user_id: str,
        user_roles: List[str],
        tool_name: str,
        parameters: Dict[str, Any],
        ip_address: str = "unknown",
    ):
        self.user_id = user_id
        self.user_roles = user_roles
        self.tool_name = tool_name
        self.parameters = parameters
        self.ip_address = ip_address
        self._start: Optional[datetime] = None

    def start(self) -> "AuditLogger":
        self._start = datetime.utcnow()
        return self

    def finish(
        self,
        status: str,
        result_row_count: int = 0,
        tokens_used: Optional[int] = None,
    ) -> AuditLog:
        elapsed_ms = 0.0
        if self._start:
            elapsed_ms = (datetime.utcnow() - self._start).total_seconds() * 1000

        return log_audit_entry(
            user_id=self.user_id,
            user_roles=self.user_roles,
            tool_name=tool_name if (tool_name := self.tool_name) else "unknown",
            parameters=self.parameters,
            status=status,
            result_row_count=result_row_count,
            tokens_used=tokens_used,
            response_time_ms=elapsed_ms,
            ip_address=self.ip_address,
        )
