from pydantic import BaseModel
from datetime import datetime
from typing import Optional, List

class AuditLog(BaseModel):
    timestamp: datetime
    user_id: str
    user_roles: List[str]
    tool_name: str
    parameters: dict
    status: str  # "SUCCESS", "BLOCKED", "ERROR"
    result_row_count: int
    tokens_used: Optional[int]
    response_time_ms: float
    ip_address: str

class RBACChangeLog(BaseModel):
    timestamp: datetime
    changed_by: str
    event: str  # "USER_CREATED", "TOOL_ASSIGNED_TO_ROLE", "USER_DEACTIVATED"
    details: dict
