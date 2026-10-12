"""Agent run and trace retrieval routes."""

from pathlib import Path
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException

from app.agent.orchestrator import AgentOrchestrator
from app.agent.provider import (
    AgentProvider,
    MockProvider,
    OpenAIChatProvider,
    UnavailableProvider,
)
from app.agent.schemas import (
    AgentProviderStatus,
    AgentRunRequest,
    AgentRunResponse,
    AgentTraceResponse,
)
from app.agent.trace import TraceStore
from app.core.config import settings
from app.rag.retriever import RagSearch, configured_rag_retriever

router = APIRouter()
trace_store = TraceStore(max_runs=100)
mock_provider = MockProvider()


def get_agent_provider() -> AgentProvider:
    """Select an explicit provider mode without falling back silently."""
    if settings.llm_provider == "mock":
        return mock_provider
    if settings.llm_provider == "openai":
        return OpenAIChatProvider()
    return UnavailableProvider(settings.llm_provider)


def get_agent_provider_status() -> AgentProviderStatus:
    provider = get_agent_provider()
    return AgentProviderStatus(
        mode=getattr(provider, "mode", "custom"),
        model=getattr(provider, "model", "custom"),
        available=getattr(provider, "available", True),
    )


def get_agent_trace_store() -> TraceStore:
    return trace_store


def get_agent_rag_retriever() -> RagSearch:
    return configured_rag_retriever()


def get_agent_database_name() -> str:
    return settings.resolve_database_name()


def get_agent_catalog_path() -> Path:
    return settings.resolve_catalog_path()


@router.get("/provider", response_model=AgentProviderStatus)
def read_agent_provider_status() -> AgentProviderStatus:
    return get_agent_provider_status()


@router.post("/run", response_model=AgentRunResponse)
async def run_agent(
    request: AgentRunRequest,
    provider: AgentProvider = Depends(get_agent_provider),
    store: TraceStore = Depends(get_agent_trace_store),
    database_name: str = Depends(get_agent_database_name),
    catalog_path: Path = Depends(get_agent_catalog_path),
    rag_retriever: RagSearch = Depends(get_agent_rag_retriever),
) -> AgentRunResponse:
    orchestrator = AgentOrchestrator(
        provider=provider,
        trace_store=store,
        database_name=database_name,
        catalog_path=catalog_path,
        rag_retriever=rag_retriever,
    )
    return await orchestrator.run(request.message, request.config)


@router.get("/runs/{run_id}/trace", response_model=AgentTraceResponse)
def read_agent_trace(
    run_id: UUID,
    store: TraceStore = Depends(get_agent_trace_store),
) -> AgentTraceResponse:
    trace = store.get(run_id)
    if trace is None:
        raise HTTPException(
            status_code=404,
            detail="Agent run trace was not found or has expired.",
        )
    return trace
