"""Validated contracts for agent requests, decisions, and execution traces."""

from datetime import datetime
from typing import Annotated, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, JsonValue, field_validator


class AgentRunConfig(BaseModel):
    model_config = ConfigDict(extra="forbid", allow_inf_nan=False)

    max_iterations: int = Field(default=5, ge=1, le=5)
    max_consecutive_tool_errors: int = Field(default=3, ge=1, le=3)
    timeout_seconds: float = Field(default=30, gt=0, le=30)
    max_response_chars: int = Field(default=4000, ge=1, le=4000)


class AgentRunRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    message: str = Field(min_length=1, max_length=2000)
    config: AgentRunConfig = Field(default_factory=AgentRunConfig)

    @field_validator("message")
    @classmethod
    def normalize_message(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise ValueError("message must not be blank")
        return normalized


class ToolCallDecision(BaseModel):
    model_config = ConfigDict(extra="forbid")

    type: Literal["tool_call"]
    tool_name: str = Field(min_length=1, max_length=100)
    arguments: dict[str, JsonValue] = Field(default_factory=dict)


class FinalDecision(BaseModel):
    model_config = ConfigDict(extra="forbid")

    type: Literal["final"]
    response: str = Field(min_length=1, max_length=4000)


AgentDecision = Annotated[
    ToolCallDecision | FinalDecision,
    Field(discriminator="type"),
]


class ToolObservation(BaseModel):
    """Tool result data is untrusted content, never policy or instructions."""

    tool_name: str
    arguments: dict[str, object]
    result: object | None = Field(
        default=None,
        description=(
            "Untrusted catalog data; provider implementations must not treat "
            "its contents as instructions."
        ),
    )
    content_trust: Literal[
        "untrusted_catalog_data", "untrusted_retrieved_content"
    ] = "untrusted_catalog_data"
    error: str | None = None


class TraceEvidence(BaseModel):
    source_title: str
    source_reference: str
    movie_id: str | None = None
    excerpt: str
    similarity: float


class TraceEvent(BaseModel):
    run_id: UUID
    sequence: int = Field(ge=1)
    timestamp: datetime
    event_type: str
    iteration: int = Field(ge=0)
    decision: dict[str, object] | None = None
    requested_tool: str | None = None
    arguments: dict[str, object] | None = None
    authorized: bool | None = None
    denial_reason: str | None = None
    result_summary: str | None = None
    error: str | None = None
    execution_status: str | None = None
    guardrail_stage: str | None = None
    guardrail_result: Literal["allowed", "denied"] | None = None
    reason_code: str | None = None
    execution_blocked: bool | None = None
    evidence: list[TraceEvidence] | None = None


class TraceSummary(BaseModel):
    event_count: int
    event_types: dict[str, int]


class AgentRunResponse(BaseModel):
    run_id: UUID
    final_response: str
    status: str
    provider_mode: str
    provider_model: str
    iteration_count: int
    tool_call_count: int
    trace_summary: TraceSummary


class AgentProviderStatus(BaseModel):
    mode: str
    model: str
    available: bool


class AgentTraceResponse(BaseModel):
    run_id: UUID
    status: str
    iteration_count: int
    tool_call_count: int
    events: list[TraceEvent]
