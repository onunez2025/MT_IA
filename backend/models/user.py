from pydantic import BaseModel
from typing import List

class Role(BaseModel):
    name: str  # "Ventas", "Finanzas", etc.
    tools: List[str]  # ["get_sales_summary", "get_sales_targets"]

class User(BaseModel):
    user_id: str  # user@mtind.com
    email: str
    roles: List[str]
    is_admin: bool = False

class Permission(BaseModel):
    user_id: str
    tool_name: str
    role_name: str
    granted: bool
