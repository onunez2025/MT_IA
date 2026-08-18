# backend/main.py
from fastapi import FastAPI, Header, HTTPException, Depends
from pydantic import BaseModel
from typing import Optional
from config import settings
from models.query import QueryResponse
from models.user import User
from layers.orchestrator import Orchestrator
from connectors.entra_connector import EntraConnector
import logging

logging.basicConfig(level=settings.log_level)
logger = logging.getLogger(__name__)

app = FastAPI(
    title="SOLE AI - Fase 0",
    version="0.1.0",
    description="Conversational AI for sales data queries"
)

orchestrator = Orchestrator()
entra = EntraConnector()


class ChatRequest(BaseModel):
    question: str


async def get_current_user(authorization: str = Header(default="")) -> User:
    """Extract and validate user from Entra ID token."""
    token = authorization.replace("Bearer ", "").strip()
    if not token:
        # Fase 0 dev fallback: return demo user if no token
        return User(
            user_id="dev-user",
            email="dev@mtindustrial.com",
            roles=["Jefe_Ventas"],
            is_admin=False,
        )
    user = await entra.validate_token(token)
    if not user:
        raise HTTPException(status_code=401, detail="Token inválido o expirado")
    return user


@app.on_event("startup")
async def startup_event():
    logger.info("🚀 SOLE AI starting up...")
    logger.info(f"Environment: {settings.environment}")
    # TODO: Validate connections on startup


@app.get("/health")
async def health():
    """Health check endpoint"""
    return {"status": "ok", "version": "0.1.0"}


@app.post("/api/chat", response_model=QueryResponse)
async def chat(
    request: ChatRequest,
    user: User = Depends(get_current_user),
):
    """Main chat endpoint — processes natural language questions."""
    return await orchestrator.process_question(
        user=user,
        question=request.question,
    )


@app.get("/api/tools")
async def list_tools(user: User = Depends(get_current_user)):
    """List tools available to the current user."""
    from guards.rbac import get_allowed_tools
    return {"user_id": user.user_id, "allowed_tools": get_allowed_tools(user.roles)}


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        "main:app",
        host="127.0.0.1",
        port=8000,
        reload=settings.debug
    )
