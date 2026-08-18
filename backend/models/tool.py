from pydantic import BaseModel, ConfigDict
from typing import List, Optional, Callable

class ToolDefinition(BaseModel):
    model_config = ConfigDict(arbitrary_types_allowed=True)

    name: str
    description: str
    parameters: dict
    handler: Optional[Callable] = None
    requires_roles: List[str]
