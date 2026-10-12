"""Offline deterministic tests for agent orchestration and policy."""

import asyncio

import pytest

from app.agent.orchestrator import AgentOrchestrator
from app.agent.provider import MockProvider, ProviderError, ScriptedMockProvider
from app.agent.schemas import (
    AgentRunConfig,
    FinalDecision,
    ToolCallDecision,
)
from app.agent.trace import TraceStore


def test_mock_provider_executes_successful_search(
    temporary_database_path, sample_catalog_path
) -> None:
    store = TraceStore()
    result = asyncio.run(AgentOrchestrator(
        MockProvider(), store, temporary_database_path, sample_catalog_path
    ).run("Find action movies in Tamil", AgentRunConfig()))

    assert result.status == "completed"
    assert result.tool_call_count == 1
    assert "matching catalog record" in result.final_response
    trace = store.get(result.run_id)
    assert trace is not None
    assert any(event.event_type == "tool_executed" for event in trace.events)


def test_mock_provider_uses_catalog_filters_for_recommendation_requests(
    temporary_database_path, sample_catalog_path
) -> None:
    store = TraceStore()
    result = asyncio.run(
        AgentOrchestrator(
            MockProvider(), store, temporary_database_path, sample_catalog_path
        ).run("Recommend a Tamil action movie", AgentRunConfig())
    )

    trace = store.get(result.run_id)
    assert result.status == "completed"
    assert result.tool_call_count == 1
    assert "2 matching catalog record(s)" in result.final_response
    assert trace is not None
    assert [
        event.requested_tool
        for event in trace.events
        if event.event_type == "tool_executed"
    ] == ["filter_movies"]


def test_mock_provider_routes_movie_metadata_questions_to_details(
    temporary_database_path, sample_catalog_path
) -> None:
    store = TraceStore()
    result = asyncio.run(
        AgentOrchestrator(
            MockProvider(), store, temporary_database_path, sample_catalog_path
        ).run("What is Alpha's runtime and rating?", AgentRunConfig())
    )

    trace = store.get(result.run_id)
    assert result.status == "completed"
    assert result.tool_call_count == 2
    assert "Alpha (2001)" in result.final_response
    assert "Runtime: 120 minutes" in result.final_response
    assert "rating: 8.2." in result.final_response
    assert "rating: 8.2 not sourced" not in result.final_response
    assert "https://example.test/alpha" in result.final_response
    assert trace is not None
    assert [
        event.requested_tool
        for event in trace.events
        if event.event_type == "tool_executed"
    ] == ["search_movies", "get_movie_details"]


def test_mock_provider_reports_unavailable_metadata_without_inventing_values(
    temporary_database_path, sample_catalog_path
) -> None:
    result = asyncio.run(
        AgentOrchestrator(
            MockProvider(), TraceStore(), temporary_database_path, sample_catalog_path
        ).run("What is Beta's runtime and rating?", AgentRunConfig())
    )

    assert result.status == "completed"
    assert "Beta (2005)" in result.final_response
    assert "Runtime: not available" in result.final_response
    assert "rating: not available" in result.final_response
    assert "https://example.test/beta" in result.final_response


def test_mock_provider_reports_empty_catalog_results_without_recommending_movies(
    temporary_database_path, sample_catalog_path
) -> None:
    result = asyncio.run(
        AgentOrchestrator(
            MockProvider(), TraceStore(), temporary_database_path, sample_catalog_path
        ).run("Find a movie named ZzzNotInCatalog", AgentRunConfig())
    )

    assert result.status == "completed"
    assert result.tool_call_count == 1
    assert result.final_response == "No movies in the catalog matched that request."


def test_mock_provider_calls_search_then_details(
    temporary_database_path, sample_catalog_path
) -> None:
    store = TraceStore()
    result = asyncio.run(AgentOrchestrator(
        MockProvider(), store, temporary_database_path, sample_catalog_path
    ).run("Tell me about Alpha", AgentRunConfig()))

    trace = store.get(result.run_id)
    assert result.status == "completed"
    assert result.tool_call_count == 2
    assert trace is not None
    assert [
        event.requested_tool
        for event in trace.events
        if event.event_type == "tool_executed"
    ] == ["search_movies", "get_movie_details"]
    assert "Alpha (2001)" in result.final_response


def test_unknown_tool_is_denied_and_trace_records_reason(
    temporary_database_path, sample_catalog_path
) -> None:
    provider = ScriptedMockProvider(
        [
            ToolCallDecision(
                type="tool_call",
                tool_name="delete_movie_database",
                arguments={},
            )
        ]
    )
    store = TraceStore()
    result = asyncio.run(AgentOrchestrator(
        provider, store, temporary_database_path, sample_catalog_path
    ).run("Delete the database", AgentRunConfig()))

    trace = store.get(result.run_id)
    assert result.status == "policy_denied"
    assert trace is not None
    denied = next(event for event in trace.events if event.event_type == "tool_authorization")
    assert denied.authorized is False
    assert denied.denial_reason == "Tool is not registered."
    assert denied.execution_blocked is True
    guardrail = next(
        event for event in trace.events
        if event.guardrail_stage == "tool_authorization"
    )
    assert guardrail.guardrail_result == "denied"
    assert guardrail.reason_code == "tool_not_registered"
    assert not any(event.event_type == "tool_executed" for event in trace.events)


def test_invalid_tool_arguments_are_reported(
    temporary_database_path, sample_catalog_path
) -> None:
    provider = ScriptedMockProvider(
        [
            ToolCallDecision(
                type="tool_call",
                tool_name="search_movies",
                arguments={"limit": 0},
            )
        ]
    )
    store = TraceStore()
    result = asyncio.run(AgentOrchestrator(
        provider, store, temporary_database_path, sample_catalog_path
    ).run("Find movies", AgentRunConfig(max_iterations=1)))
    assert result.status == "iteration_limit"
    assert result.iteration_count == 1
    trace = store.get(result.run_id)
    assert trace is not None
    assert any(event.event_type == "tool_validation_error" for event in trace.events)
    assert not any(event.event_type == "tool_executed" for event in trace.events)


def test_invalid_tool_arguments_stop_at_consecutive_error_limit(
    temporary_database_path, sample_catalog_path
) -> None:
    provider = ScriptedMockProvider(
        [
            ToolCallDecision(
                type="tool_call",
                tool_name="search_movies",
                arguments={"limit": 0, "unexpected": value},
            )
            for value in ("one", "two", "three")
        ]
    )
    store = TraceStore()
    result = asyncio.run(AgentOrchestrator(
        provider, store, temporary_database_path, sample_catalog_path
    ).run("Find movies", AgentRunConfig()))
    assert result.status == "tool_error_limit"
    assert result.iteration_count == 3
    assert sum(
        event.event_type == "tool_validation_error"
        for event in store.get(result.run_id).events
    ) == 3


def test_repeated_identical_tool_call_is_denied(
    temporary_database_path, sample_catalog_path
) -> None:
    call = ToolCallDecision(
        type="tool_call",
        tool_name="search_movies",
        arguments={"query": "Alpha", "limit": 20},
    )
    provider = ScriptedMockProvider([call, call])
    store = TraceStore()
    result = asyncio.run(AgentOrchestrator(
        provider, store, temporary_database_path, sample_catalog_path
    ).run("Find Alpha", AgentRunConfig()))
    trace = store.get(result.run_id)

    assert result.status == "policy_denied"
    assert result.tool_call_count == 2
    assert trace is not None
    assert any(
        event.denial_reason == "Repeated identical tool call denied."
        for event in trace.events
    )


def test_iteration_limit_is_enforced(
    temporary_database_path, sample_catalog_path
) -> None:
    provider = ScriptedMockProvider(
        [
            ToolCallDecision(
                type="tool_call",
                tool_name="search_movies",
                arguments={"query": "Alpha"},
            )
        ]
    )
    result = asyncio.run(AgentOrchestrator(
        provider, TraceStore(), temporary_database_path, sample_catalog_path
    ).run("Find Alpha", AgentRunConfig(max_iterations=1)))
    assert result.status == "iteration_limit"
    assert result.iteration_count == 1


def test_provider_failure_ends_run_truthfully(
    temporary_database_path, sample_catalog_path
) -> None:
    provider = ScriptedMockProvider([ProviderError("private provider detail")])
    store = TraceStore()
    result = asyncio.run(AgentOrchestrator(
        provider, store, temporary_database_path, sample_catalog_path
    ).run("Search", AgentRunConfig()))
    trace = store.get(result.run_id)

    assert result.status == "provider_error"
    assert "private provider detail" not in result.final_response
    assert trace is not None
    assert [event.sequence for event in trace.events] == list(
        range(1, len(trace.events) + 1)
    )
    assert all(event.run_id == result.run_id for event in trace.events)
    assert trace.events[-1].execution_status == "provider_error"


def test_final_provider_decision_is_terminal(
    temporary_database_path, sample_catalog_path
) -> None:
    result = asyncio.run(AgentOrchestrator(
        ScriptedMockProvider(
            [FinalDecision(type="final", response="No tool needed.")]
        ),
        TraceStore(),
        temporary_database_path,
        sample_catalog_path,
    ).run("Say hello", AgentRunConfig()))
    assert result.status == "completed"
    assert result.tool_call_count == 0
    assert result.final_response == "No tool needed."


def test_final_response_content_is_not_duplicated_in_trace(
    temporary_database_path, sample_catalog_path
) -> None:
    sensitive_text = "A private answer containing sk-abcdefghijklmnopqrstuv"
    store = TraceStore()
    result = asyncio.run(AgentOrchestrator(
        ScriptedMockProvider(
            [FinalDecision(type="final", response=sensitive_text)]
        ),
        store,
        temporary_database_path,
        sample_catalog_path,
    ).run("Respond", AgentRunConfig()))
    trace = store.get(result.run_id)

    assert result.status == "output_denied"
    assert "could not be safely returned" in result.final_response
    assert trace is not None
    assert "sk-abcdefghijklmnopqrstuv" not in trace.model_dump_json()


def test_malformed_provider_decision_ends_without_tool_execution(
    temporary_database_path, sample_catalog_path
) -> None:
    provider = ScriptedMockProvider([{"type": "unknown"}])
    store = TraceStore()
    result = asyncio.run(AgentOrchestrator(
        provider, store, temporary_database_path, sample_catalog_path
    ).run("Find Alpha", AgentRunConfig()))
    trace = store.get(result.run_id)

    assert result.status == "invalid_decision"
    assert result.tool_call_count == 0
    assert trace is not None
    assert any(event.event_type == "invalid_decision" for event in trace.events)
    assert not any(event.event_type == "tool_executed" for event in trace.events)


def test_provider_timeout_is_enforced(
    temporary_database_path, sample_catalog_path
) -> None:
    class SlowProvider:
        async def decide(self, message, observations):
            del message, observations
            await asyncio.sleep(0.1)
            return FinalDecision(type="final", response="Too late.")

    result = asyncio.run(AgentOrchestrator(
        SlowProvider(), TraceStore(), temporary_database_path, sample_catalog_path
    ).run(
        "Wait", AgentRunConfig(timeout_seconds=0.01)
    ))
    assert result.status == "timeout"
    assert result.tool_call_count == 0
