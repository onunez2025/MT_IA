# backend/api/openai_compat.py
"""
Endpoints compatibles con la API de OpenAI.

Permite conectar Open WebUI (u otro frontend) al backend SOLE AI
sin cambiar nada del motor agéntico interno.

Endpoints implementados:
  GET  /v1/models                — lista de modelos disponibles
  POST /v1/chat/completions      — chat con streaming SSE (formato OpenAI)

Autenticación temporal (mientras no hay Entra ID en producción):
  Bearer token en Authorization header → se mapea a un rol.
  Si no hay token → rol por defecto: Jefe_Ventas (acceso completo de ventas).
"""

import json
import time
import uuid
import logging
from typing import List, Optional, AsyncGenerator

from fastapi import APIRouter, Header, HTTPException, Request
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from models.user import User
from layers.agent import run_agent, run_agent_streaming
from layers.orchestrator import TOOL_REGISTRY
from guards.rbac import validate_rbac, ROLE_PERMISSIONS

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/v1", tags=["OpenAI-compatible"])

# ── Rol por defecto cuando no hay autenticación configurada ───────────────────
#
# En producción con Entra ID: se extraerá el rol del token JWT.
# Por ahora: token Bearer simple → rol.
#
# Tokens de acceso por rol (configurar en Open WebUI como API key):
#   sole-vendedor     → Vendedor
#   sole-jefe         → Jefe_Ventas
#   sole-gerente      → Gerente
#   sole-admin        → Admin
#   (cualquier otro)  → Jefe_Ventas (default)
_TOKEN_TO_ROLE = {
    "sole-vendedor": "Vendedor",
    "sole-jefe":     "Jefe_Ventas",
    "sole-gerente":  "Gerente",
    "sole-admin":    "Admin",
}
_DEFAULT_ROLE = "Jefe_Ventas"


def _resolve_role(authorization: Optional[str]) -> str:
    """Extrae el rol del Bearer token."""
    if not authorization or not authorization.startswith("Bearer "):
        return _DEFAULT_ROLE
    token = authorization.removeprefix("Bearer ").strip()
    return _TOKEN_TO_ROLE.get(token, _DEFAULT_ROLE)


# ── Modelos Pydantic (formato OpenAI) ─────────────────────────────────────────

class ChatMessage(BaseModel):
    role: str           # "user" | "assistant" | "system"
    content: str


class ChatCompletionRequest(BaseModel):
    model: str = "sole-ai"
    messages: List[ChatMessage]
    stream: bool = True
    temperature: Optional[float] = None
    max_tokens: Optional[int] = None
    # Campos de OpenAI que ignoramos pero aceptamos para compatibilidad
    top_p: Optional[float] = None
    frequency_penalty: Optional[float] = None
    presence_penalty: Optional[float] = None


# ── Helpers de formato OpenAI ─────────────────────────────────────────────────

def _make_chunk(content: str, finish_reason: Optional[str], req_id: str) -> str:
    """Crea una línea SSE con formato OpenAI."""
    chunk = {
        "id": req_id,
        "object": "chat.completion.chunk",
        "created": int(time.time()),
        "model": "sole-ai",
        "choices": [{
            "index": 0,
            "delta": {"content": content} if content else {},
            "finish_reason": finish_reason,
        }],
    }
    return f"data: {json.dumps(chunk, ensure_ascii=False)}\n\n"


def _role_chunk(req_id: str) -> str:
    """Primer chunk obligatorio: declara el role=assistant."""
    return f"data: {json.dumps({'id': req_id, 'object': 'chat.completion.chunk', 'created': int(time.time()), 'model': 'sole-ai', 'choices': [{'index': 0, 'delta': {'role': 'assistant'}, 'finish_reason': None}]})}\n\n"


async def _stream_agent(
    question: str,
    tool_registry: dict,
    allowed_tools: list,
    req_id: str,
) -> AsyncGenerator[str, None]:
    """
    Streaming real del agente agéntico.

    Emite:
      1. Mensajes de estado inmediatamente cuando el agente llama una tool
         → el usuario ve "🔍 Buscando cliente..." en vez del punto blanco
      2. La respuesta final token por token (efecto de tipeo)

    Formato SSE compatible con OpenAI / Open WebUI.
    """
    import re

    # ── Primer chunk: declara el role ────────────────────────────────────────
    yield _role_chunk(req_id)

    status_lines: list[str] = []
    got_response = False

    async for event_type, content in run_agent_streaming(question, tool_registry, allowed_tools):
        if event_type == "status":
            # Emitir status inmediatamente como texto en cursiva
            # Open WebUI lo renderiza en markdown → se ve como indicador de progreso
            line = f"*{content}*\n"
            status_lines.append(line)
            yield _make_chunk(line, None, req_id)

        elif event_type == "response":
            got_response = True
            # Separador visual si hubo líneas de status
            if status_lines:
                yield _make_chunk("\n", None, req_id)

            # Emitir respuesta final token por token (efecto de tipeo)
            tokens = re.split(r'(\s+)', content)
            for token in tokens:
                if token:
                    yield _make_chunk(token, None, req_id)

        elif event_type == "error":
            if status_lines:
                yield _make_chunk("\n", None, req_id)
            yield _make_chunk(f"\n⚠️ {content}", None, req_id)

    yield _make_chunk("", "stop", req_id)
    yield "data: [DONE]\n\n"


async def _stream_response(
    full_text: str,
    req_id: str,
) -> AsyncGenerator[str, None]:
    """Streaming simple para el fallback (respuesta ya calculada)."""
    import re
    yield _role_chunk(req_id)
    for token in re.split(r'(\s+)', full_text):
        if token:
            yield _make_chunk(token, None, req_id)
    yield _make_chunk("", "stop", req_id)
    yield "data: [DONE]\n\n"


# ── Endpoints ─────────────────────────────────────────────────────────────────

@router.get("/models")
async def list_models():
    """Lista los modelos disponibles (Open WebUI los necesita para el selector)."""
    return {
        "object": "list",
        "data": [
            {
                "id": "sole-ai",
                "object": "model",
                "created": 1700000000,
                "owned_by": "MT Industrial",
                "name": "SOLE AI",
                "description": "Asistente de ventas MT Industrial — Fase 0",
            }
        ],
    }


@router.get("/models/{model_id}")
async def get_model(model_id: str):
    return {
        "id": model_id,
        "object": "model",
        "created": 1700000000,
        "owned_by": "MT Industrial",
    }


@router.post("/chat/completions")
async def chat_completions(
    request: ChatCompletionRequest,
    authorization: Optional[str] = Header(default=None),
):
    """
    Endpoint principal de chat — compatible con OpenAI.

    Extrae el último mensaje del usuario, lo procesa con el agente SOLE,
    y devuelve la respuesta en formato OpenAI (streaming o completo).
    """
    req_id = f"chatcmpl-{uuid.uuid4().hex[:12]}"

    # Resolver rol desde el token
    role = _resolve_role(authorization)
    user = User(user_id="openwebui-user", email="openwebui@mtindustrial.com", roles=[role])

    # Extraer la pregunta del usuario (último mensaje con role="user")
    user_messages = [m for m in request.messages if m.role == "user"]
    if not user_messages:
        raise HTTPException(status_code=400, detail="No user message found")

    question = user_messages[-1].content.strip()
    if not question:
        raise HTTPException(status_code=400, detail="Empty question")

    logger.info(f"[OpenAI compat] role={role} q='{question[:80]}'")

    # Calcular herramientas permitidas por RBAC
    allowed_tools = [
        t for t in TOOL_REGISTRY
        if validate_rbac(user.roles, t)
    ]

    _sse_headers = {
        "Cache-Control": "no-cache",
        "X-Accel-Buffering": "no",   # Para Nginx / EasyPanel
    }

    # ── Streaming (modo principal) ─────────────────────────────────────────────
    # El agente emite status + respuesta en tiempo real.
    # Open WebUI muestra cada chunk conforme llega → no hay punto blanco.
    if request.stream:
        return StreamingResponse(
            _stream_agent(question, TOOL_REGISTRY, allowed_tools, req_id),
            media_type="text/event-stream",
            headers=_sse_headers,
        )

    # ── Respuesta completa (no-streaming, fallback) ────────────────────────────
    try:
        agent_result = await run_agent(
            question=question,
            tool_registry=TOOL_REGISTRY,
            allowed_tools=allowed_tools,
        )
    except Exception as exc:
        logger.error(f"[OpenAI compat] Agent error: {exc}")
        raise HTTPException(status_code=500, detail=str(exc))

    response_text = agent_result.response or "No pude generar una respuesta."
    prompt_tokens     = len(question.split())
    completion_tokens = len(response_text.split())

    return {
        "id": req_id,
        "object": "chat.completion",
        "created": int(time.time()),
        "model": "sole-ai",
        "choices": [{
            "index": 0,
            "message": {"role": "assistant", "content": response_text},
            "finish_reason": "stop",
        }],
        "usage": {
            "prompt_tokens": prompt_tokens,
            "completion_tokens": completion_tokens,
            "total_tokens": prompt_tokens + completion_tokens,
        },
    }
