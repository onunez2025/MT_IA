# backend/main.py
from fastapi import FastAPI
from config import settings
import logging

logging.basicConfig(level=settings.log_level)
logger = logging.getLogger(__name__)

app = FastAPI(
    title="SOLE AI - Fase 0",
    version="0.1.0",
    description="Conversational AI for sales data queries"
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


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        "main:app",
        host="127.0.0.1",
        port=8000,
        reload=settings.debug
    )
