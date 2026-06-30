"""
GovTech Citizen Chatbot — FastAPI application entry point.

Mounts all routers and exposes a /health endpoint used by Docker Swarm
healthchecks and load balancer probes.
"""

from __future__ import annotations

from contextlib import asynccontextmanager
from typing import AsyncGenerator

import structlog
from fastapi import FastAPI
from fastapi.responses import JSONResponse

from app.core.config import settings
from app.core.logging import setup_logging
from app.webhook.chatwoot import router as chatwoot_router

logger = structlog.get_logger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    """
    Application lifespan context.

    Runs setup_logging() once at startup so structlog is configured before
    the first request. Logs startup info including the active agent type.
    """
    setup_logging(log_level=settings.LOG_LEVEL, json_logs=settings.JSON_LOGS)
    logger.info(
        "app.startup",
        agent_type=settings.AGENT_TYPE,
        chatwoot_url=settings.CHATWOOT_URL,
        log_level=settings.LOG_LEVEL,
    )
    yield
    logger.info("app.shutdown")


app = FastAPI(
    title="GovTech Citizen Chatbot",
    description=(
        "Production-ready framework for WhatsApp/Chatwoot AI chatbots "
        "serving Brazilian municipal government citizens."
    ),
    version="1.0.0",
    lifespan=lifespan,
    docs_url="/docs",
    redoc_url="/redoc",
)

# --- Routers ---
app.include_router(chatwoot_router)


# --- Health check ---
@app.get("/health", tags=["observability"])
async def health() -> JSONResponse:
    """
    Liveness + basic readiness probe.

    Checks Redis connectivity. The agent/OpenAI are not probed here since
    they are invoked per-request and a slow OpenAI response should not mark
    the service as unhealthy.

    Returns:
        200 with {"status": "ok", "redis": true/false, "agent_type": "..."}
    """
    from app.core.dedup import ping_redis

    redis_ok = await ping_redis()
    return JSONResponse(
        status_code=200,
        content={
            "status": "ok",
            "redis": redis_ok,
            "agent_type": settings.AGENT_TYPE,
            "model": settings.OPENAI_MODEL,
        },
    )
