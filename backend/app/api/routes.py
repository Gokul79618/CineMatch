"""HTTP endpoints for service health and platform information."""

import logging

from fastapi import APIRouter
from fastapi.responses import JSONResponse
import mysql.connector

from app.api.agent import router as agent_router
from app.api.movies import router as movies_router
from app.core.config import settings
from app.database.connection import verify_database_ready
from app.schemas.system import (
    HealthResponse,
    ReadinessResponse,
    SystemInfoResponse,
)

router = APIRouter()
logger = logging.getLogger("cinematch.api")
router.include_router(agent_router, prefix="/agent", tags=["agent"])
router.include_router(movies_router, prefix="/movies", tags=["movies"])

PLANNED_CAPABILITIES = [
    "Agent harness engineering",
    "Guardrails",
    "LLM tool calling",
    "Retrieval-Augmented Generation (RAG)",
    "Evals and golden-set testing",
]


@router.get("/health", response_model=HealthResponse, tags=["service"])
def read_health() -> HealthResponse:
    """Return the current API process health."""
    return HealthResponse(
        status="ok",
        service=settings.app_name,
        version=settings.app_version,
    )


@router.get("/ready", response_model=ReadinessResponse, tags=["service"])
def read_readiness() -> ReadinessResponse | JSONResponse:
    """Check application readiness using a read-only MySQL query."""
    try:
        ready = verify_database_ready(settings.resolve_database_name())
    except (mysql.connector.Error, RuntimeError) as exc:
        logger.warning(
            "event=readiness_database_unavailable error_type=%s",
            type(exc).__name__,
        )
        ready = False
    if not ready:
        return JSONResponse(
            status_code=503,
            content={"status": "not_ready", "database": "unavailable"},
        )
    return ReadinessResponse(status="ready", database="available")


@router.get("/system/info", response_model=SystemInfoResponse, tags=["system"])
def read_system_info() -> SystemInfoResponse:
    """Describe the application and its planned core capabilities."""
    return SystemInfoResponse(
        application_name=settings.app_name,
        api_version=settings.api_version,
        planned_capabilities=PLANNED_CAPABILITIES,
    )
