# backend/main.py
import os
import re
from fastapi import FastAPI, Header, HTTPException, Depends
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from pydantic import BaseModel
from typing import Optional
from pathlib import Path
from config import settings
from models.query import QueryResponse
from models.user import User
from layers.orchestrator import Orchestrator
from connectors.entra_connector import EntraConnector
from api.openai_compat import router as openai_router
from api.reports import router as reports_router
import logging

logging.basicConfig(level=settings.log_level)
logger = logging.getLogger(__name__)

app = FastAPI(
    title="SOLE AI - Fase 0",
    version="0.1.0",
    description="Conversational AI for sales data queries"
)

# Endpoints compatibles con OpenAI (para Open WebUI y otros clientes)
app.include_router(openai_router)

# Endpoints de reportes y análisis (Fase 1)
app.include_router(reports_router)

orchestrator = Orchestrator()
entra = EntraConnector()


class ChatRequest(BaseModel):
    question: str
    # Campos opcionales para testing en modo desarrollo (ignorados en producción)
    user_id: Optional[str] = None
    roles: Optional[list] = None


async def get_current_user(
    request_body: ChatRequest = None,
    authorization: str = Header(default=""),
) -> User:
    """Extract and validate user from Entra ID token."""
    token = authorization.replace("Bearer ", "").strip()

    # Producción: validar token de Entra ID
    if token:
        user = await entra.validate_token(token)
        if not user:
            raise HTTPException(status_code=401, detail="Token inválido o expirado")
        return user

    # Desarrollo: si se pasan user_id/roles en el body, úsalos para testing
    if settings.environment in ("development", "dev") and request_body:
        if request_body.user_id and request_body.roles is not None:
            return User(
                user_id=request_body.user_id,
                email=f"{request_body.user_id}@mtindustrial.com",
                roles=request_body.roles,
                is_admin="Admin" in request_body.roles,
            )

    # Fallback genérico para dev sin token
    return User(
        user_id="dev-user",
        email="dev@mtindustrial.com",
        roles=["Jefe_Ventas"],
        is_admin=False,
    )



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
    authorization: str = Header(default=""),
):
    """Main chat endpoint — processes natural language questions."""
    user = await get_current_user(request_body=request, authorization=authorization)
    return await orchestrator.process_question(
        user=user,
        question=request.question,
    )


@app.get("/api/tools")
async def list_tools(user: User = Depends(get_current_user)):
    """List tools available to the current user."""
    from guards.rbac import get_allowed_tools
    return {"user_id": user.user_id, "allowed_tools": get_allowed_tools(user.roles)}


@app.get("/reports/{filename}")
async def download_report(filename: str):
    """
    Descarga un reporte generado (Excel de forecast).
    Solo permite archivos .xlsx con nombre seguro (sin path traversal).
    """
    # Validar que el nombre sea seguro: solo letras, números, _, -, . y termine en .xlsx
    if not re.match(r'^[\w\-]+\.xlsx$', filename):
        raise HTTPException(status_code=400, detail="Nombre de archivo inválido.")

    output_dir = os.getenv("FORECAST_OUTPUT_DIR", "/tmp")
    filepath = os.path.join(output_dir, filename)

    if not os.path.isfile(filepath):
        raise HTTPException(
            status_code=404,
            detail=f"Reporte '{filename}' no encontrado. Puede que haya expirado — genera uno nuevo."
        )

    return FileResponse(
        path=filepath,
        filename=filename,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    )


# ── Frontend estático ────────────────────────────────────────────
# Servir archivos CSS/JS en /static/*
_static_dir = Path(__file__).parent / "static"
if _static_dir.exists():
    app.mount("/static", StaticFiles(directory=str(_static_dir)), name="static")

    @app.get("/", include_in_schema=False)
    async def serve_frontend():
        """Sirve el chat web en la raíz."""
        return FileResponse(str(_static_dir / "index.html"))


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        "main:app",
        host="127.0.0.1",
        port=8000,
        reload=settings.debug
    )
