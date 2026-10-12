"""Response models for service and system endpoints."""

from pydantic import BaseModel


class ServiceMessage(BaseModel):
    message: str


class HealthResponse(BaseModel):
    status: str
    service: str
    version: str


class ReadinessResponse(BaseModel):
    status: str
    database: str


class SystemInfoResponse(BaseModel):
    application_name: str
    api_version: str
    planned_capabilities: list[str]
