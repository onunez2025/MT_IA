from pydantic import BaseModel
from typing import Optional, List, Dict, Any

class ToolParameter(BaseModel):
    name: str
    type: str  # "string", "int", "date"
    required: bool = True
    description: str = ""

class Tool(BaseModel):
    name: str
    description: str
    parameters: List[ToolParameter]

class QueryRequest(BaseModel):
    user_id: str
    question: str
    conversation_id: Optional[str] = None

class QueryResponse(BaseModel):
    status: str  # "success", "error", "blocked"
    response: str
    sources: List[Dict[str, Any]]
    tokens_used: Optional[int] = None
    error_message: Optional[str] = None
