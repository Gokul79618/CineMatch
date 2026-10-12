"""FastAPI application entry point for CineMatch AI."""

import logging
import time
from contextlib import asynccontextmanager
from collections.abc import AsyncGenerator

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.middleware.base import RequestResponseEndpoint
from starlette.responses import Response
import mysql.connector

from app.api import router
from app.core.config import settings
from app.core.middleware import AgentRateLimitMiddleware, RequestSizeLimitMiddleware
from app.database.connection import verify_database_ready
from app.database.init_db import initialize_database
from app.schemas.system import ServiceMessage

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s %(message)s",
)
logger = logging.getLogger("cinematch.api")


@asynccontextmanager
async def lifespan(_: FastAPI) -> AsyncGenerator[None, None]:
    settings.validate_startup()
    try:
        if settings.auto_initialize_database:
            initialize_database(
                settings.resolve_database_name(),
                settings.resolve_catalog_path(),
            )
        elif not verify_database_ready(settings.resolve_database_name()):
            raise RuntimeError("The configured MySQL database is not ready.")
    except (mysql.connector.Error, RuntimeError, OSError, ValueError) as exc:
        logger.error("event=startup_database_check_failed error_type=%s", type(exc).__name__)
        raise RuntimeError(
            "CineMatch startup could not verify the configured MySQL database."
        ) from None
    yield


app = FastAPI(
    title=settings.app_name,
    version=settings.app_version,
    description="CineMatch AI platform API and deterministic movie catalog.",
    lifespan=lifespan,
)


@app.exception_handler(RequestValidationError)
async def request_validation_error(
    _: Request, _exc: RequestValidationError
) -> JSONResponse:
    """Return a safe validation response without echoing submitted values."""
    return JSONResponse(
        status_code=422,
        content={
            "detail": {
                "code": "invalid_request",
                "message": "Request body or parameters are invalid.",
            }
        },
    )


@app.exception_handler(Exception)
async def internal_server_error(_: Request, exc: Exception) -> JSONResponse:
    """Log a safe error class and return a non-sensitive response."""
    logger.error("event=unhandled_api_error error_type=%s", type(exc).__name__)
    return JSONResponse(
        status_code=500,
        content={
            "detail": {
                "code": "internal_error",
                "message": "The request could not be completed.",
            }
        },
    )


@app.middleware("http")
async def log_http_request(
    request: Request,
    call_next: RequestResponseEndpoint,
) -> Response:
    started_at = time.monotonic()
    response = await call_next(request)
    route = request.scope.get("route")
    logger.info(
        "event=http_request method=%s path=%s status_code=%s duration_ms=%.1f",
        request.method,
        getattr(route, "path", "unmatched"),
        response.status_code,
        (time.monotonic() - started_at) * 1000,
    )
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["Referrer-Policy"] = "no-referrer"
    return response


app.add_middleware(
    RequestSizeLimitMiddleware,
    max_bytes=settings.max_request_bytes,
)
app.add_middleware(
    AgentRateLimitMiddleware,
    max_requests=settings.agent_requests_per_minute,
)


app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.frontend_origins,
    allow_credentials=False,
    allow_methods=["GET", "POST"],
    allow_headers=["Content-Type", "Authorization"],
)

app.include_router(router, prefix="/api")


@app.get("/", response_model=ServiceMessage, tags=["service"])
def read_root() -> ServiceMessage:
    """Confirm that the service is running."""
    return ServiceMessage(message=f"{settings.app_name} API is running.")
