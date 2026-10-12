"""Deterministic answer-quality scenarios through the guarded agent harness."""

import json
from pathlib import Path
from typing import Any

import httpx
import pytest

from app.agent.provider import OpenAIChatProvider
from app.api.agent import get_agent_provider, get_agent_rag_retriever
from app.main import app
from app.rag.schemas import RetrievalResponse, RetrievedPassage

CASES_PATH = Path(__file__).parent / "data" / "llm_answer_quality_cases.json"
_QUALITY_CASES = json.loads(CASES_PATH.read_text(encoding="utf-8"))
_CASES_BY_ID = {case["case_id"]: case for case in _QUALITY_CASES["cases"]}
_TEST_KEY = "test-only-quality-provider-key"
_SOURCE_REFERENCE = "https://example.test/alpha-evidence"
_SUPPORTED_EVIDENCE = (
    "Alpha follows a courageous investigator through a difficult case."
)


def quality_case(case_id: str) -> dict[str, Any]:
    return _CASES_BY_ID[case_id]


def provider_for(
    responses: list[httpx.Response],
    captured: list[httpx.Request] | None = None,
) -> OpenAIChatProvider:
    def respond(request: httpx.Request) -> httpx.Response:
        if captured is not None:
            captured.append(request)
        if not responses:
            raise AssertionError("Unexpected additional provider request.")
        return responses.pop(0)

    return OpenAIChatProvider(
        api_key=_TEST_KEY,
        max_retries=0,
        transport=httpx.MockTransport(respond),
    )


def completion(
    *,
    content: object = None,
    tool_name: str | None = None,
    arguments: str = "{}",
) -> httpx.Response:
    message: dict[str, object] = {"role": "assistant", "content": content}
    if tool_name is not None:
        message["tool_calls"] = [
            {
                "id": "quality-case-call",
                "type": "function",
                "function": {"name": tool_name, "arguments": arguments},
            }
        ]
    return httpx.Response(
        200,
        json={"choices": [{"message": message}]},
    )


class FixedEvidenceRetriever:
    def __init__(self, passages: list[RetrievedPassage]):
        self.passages = passages

    def retrieve(self, request: object) -> RetrievalResponse:
        del request
        return RetrievalResponse(
            status="results" if self.passages else "no_results",
            count=len(self.passages),
            passages=self.passages,
        )


def evidence_retriever() -> FixedEvidenceRetriever:
    return FixedEvidenceRetriever(
        [
            RetrievedPassage(
                source_title="Alpha verified notes",
                source_reference=_SOURCE_REFERENCE,
                movie_id="alpha-2001",
                text=_SUPPORTED_EVIDENCE,
                similarity=0.91,
                metadata={},
            )
        ]
    )


def test_answer_quality_dataset_is_versioned_and_covers_required_categories() -> None:
    assert _QUALITY_CASES["dataset_version"] == (
        "cinematch-llm-answer-quality-cases-v1"
    )
    categories = {case["category"] for case in _QUALITY_CASES["cases"]}
    assert len(_QUALITY_CASES["cases"]) >= 8
    assert len(categories) >= 8


def test_mocked_openai_catalog_detail_is_grounded_in_test_catalog(
    agent_api_client,
) -> None:
    case = quality_case("catalog-detail")
    provider = provider_for(
        [
            completion(
                tool_name="search_movies",
                arguments='{"query":"Alpha","limit":5}',
            ),
            completion(
                tool_name="get_movie_details",
                arguments='{"movie_id":"alpha-2001"}',
            ),
            completion(
                content=(
                    "Alpha (2001) is a Tamil action film. "
                    "A courageous investigator follows a difficult case."
                )
            ),
        ]
    )
    app.dependency_overrides[get_agent_provider] = lambda: provider

    response = agent_api_client.post(
        "/api/agent/run", json={"message": case["message"]}
    )

    assert response.status_code == 200
    run = response.json()
    assert run["status"] == case["expected_status"]
    assert run["provider_mode"] == "openai"
    trace = agent_api_client.get(
        f"/api/agent/runs/{run['run_id']}/trace"
    ).json()
    executed = [
        event["requested_tool"]
        for event in trace["events"]
        if event["event_type"] == "tool_executed"
    ]
    assert executed == case["expected_tools"]
    assert "A courageous investigator follows a difficult case" in run["final_response"]


def test_mocked_openai_recommendation_uses_catalog_filter(agent_api_client) -> None:
    case = quality_case("catalog-recommendation")
    provider = provider_for(
        [
            completion(
                tool_name="filter_movies",
                arguments='{"language":"Tamil","genre":"Action","limit":5}',
            ),
            completion(
                content=(
                    "Alpha and Gamma match the Tamil action filters in the catalog."
                )
            ),
        ]
    )
    app.dependency_overrides[get_agent_provider] = lambda: provider

    response = agent_api_client.post(
        "/api/agent/run", json={"message": case["message"]}
    )

    assert response.status_code == 200
    run = response.json()
    assert run["status"] == case["expected_status"]
    assert "Alpha" in run["final_response"] and "Gamma" in run["final_response"]
    trace = agent_api_client.get(
        f"/api/agent/runs/{run['run_id']}/trace"
    ).json()
    assert [
        event["requested_tool"]
        for event in trace["events"]
        if event["event_type"] == "tool_executed"
    ] == case["expected_tools"]


@pytest.mark.parametrize("case_id", ["rag-grounded-answer", "rag-source-attribution"])
def test_mocked_openai_rag_answer_preserves_evidence_and_exact_citation(
    agent_api_client,
    case_id: str,
) -> None:
    case = quality_case(case_id)
    provider = provider_for(
        [
            completion(
                tool_name="retrieve_movie_context",
                arguments='{"query":"Alpha investigator","top_k":1}',
            ),
            completion(
                content=(
                    f"{_SUPPORTED_EVIDENCE} "
                    f"[Alpha verified notes]({_SOURCE_REFERENCE})"
                )
            ),
        ]
    )
    app.dependency_overrides[get_agent_provider] = lambda: provider
    app.dependency_overrides[get_agent_rag_retriever] = evidence_retriever

    response = agent_api_client.post(
        "/api/agent/run", json={"message": case["message"]}
    )

    assert response.status_code == 200
    run = response.json()
    assert run["status"] == case["expected_status"]
    assert _SUPPORTED_EVIDENCE in run["final_response"]
    assert _SOURCE_REFERENCE in run["final_response"]
    trace = agent_api_client.get(
        f"/api/agent/runs/{run['run_id']}/trace"
    ).json()
    retrieval_event = next(
        event
        for event in trace["events"]
        if event["event_type"] == "tool_executed"
        and event["requested_tool"] == "retrieve_movie_context"
    )
    assert retrieval_event["authorized"] is True
    assert retrieval_event["evidence"][0]["source_reference"] == _SOURCE_REFERENCE


def test_mocked_openai_abstains_when_retrieval_is_empty(agent_api_client) -> None:
    case = quality_case("outside-corpus")
    provider = provider_for(
        [
            completion(
                tool_name="retrieve_movie_context",
                arguments='{"query":"dragon diplomacy exoplanet","top_k":1}',
            ),
            completion(
                content=(
                    "I cannot answer that from the available evidence; "
                    "the local index returned no relevant passages."
                )
            ),
        ]
    )
    app.dependency_overrides[get_agent_provider] = lambda: provider
    app.dependency_overrides[get_agent_rag_retriever] = lambda: (
        FixedEvidenceRetriever([])
    )

    response = agent_api_client.post(
        "/api/agent/run", json={"message": case["message"]}
    )

    assert response.status_code == 200
    run = response.json()
    assert run["status"] == case["expected_status"]
    assert "cannot answer" in run["final_response"].casefold()
    assert "no relevant passages" in run["final_response"].casefold()


def test_prompt_injection_is_blocked_before_provider_call(agent_api_client) -> None:
    case = quality_case("prompt-injection")
    captured: list[httpx.Request] = []
    provider = provider_for([], captured)
    app.dependency_overrides[get_agent_provider] = lambda: provider

    response = agent_api_client.post(
        "/api/agent/run", json={"message": case["message"]}
    )

    assert response.status_code == 200
    run = response.json()
    assert run["status"] == case["expected_status"]
    assert captured == []


def test_unsupported_catalog_claim_is_rejected_by_output_guardrail(
    agent_api_client,
) -> None:
    case = quality_case("unsupported-claim")
    provider = provider_for(
        [
            completion(
                tool_name="search_movies",
                arguments='{"query":"Beta","limit":5}',
            ),
            completion(content="Beta has a rating of 9.1 out of 10."),
        ]
    )
    app.dependency_overrides[get_agent_provider] = lambda: provider

    response = agent_api_client.post(
        "/api/agent/run", json={"message": case["message"]}
    )

    assert response.status_code == 200
    run = response.json()
    assert run["status"] == case["expected_status"]
    trace = agent_api_client.get(
        f"/api/agent/runs/{run['run_id']}/trace"
    ).json()
    assert any(
        event["guardrail_stage"] == "output"
        and event["guardrail_result"] == "denied"
        and event["reason_code"] == "output_unsupported_movie_metadata"
        for event in trace["events"]
    )


@pytest.mark.parametrize(
    ("case_id", "response"),
    [
        (
            "provider-failure",
            httpx.Response(
                503,
                text=f"{_TEST_KEY} provider outage details",
            ),
        ),
        ("malformed-provider-response", httpx.Response(200, json={"choices": []})),
    ],
)
def test_provider_failure_and_malformed_response_are_terminal_and_safe(
    agent_api_client,
    case_id: str,
    response: httpx.Response,
) -> None:
    case = quality_case(case_id)
    provider = provider_for([response])
    app.dependency_overrides[get_agent_provider] = lambda: provider

    result = agent_api_client.post(
        "/api/agent/run", json={"message": case["message"]}
    ).json()

    assert result["status"] == case["expected_status"]
    assert result["provider_mode"] == "openai"
    assert _TEST_KEY not in result["final_response"]
    assert "provider outage details" not in result["final_response"]


def test_provider_tool_proposals_stay_inside_registry_and_argument_schema(
    agent_api_client,
) -> None:
    cases = [
        (
            "unauthorized-tool",
            "delete_movie_database",
            "{}",
            "policy_denied",
        ),
        (
            "unauthorized-tool",
            "search_movies",
            '{"query":"Alpha","limit":0}',
            "iteration_limit",
        ),
    ]
    for case_id, tool_name, arguments, expected_status in cases:
        case = quality_case(case_id)
        provider = provider_for(
            [completion(tool_name=tool_name, arguments=arguments)]
        )
        app.dependency_overrides[get_agent_provider] = lambda: provider
        payload: dict[str, Any] = {"message": case["message"]}
        if expected_status == "iteration_limit":
            payload["config"] = {"max_iterations": 1}
        response = agent_api_client.post("/api/agent/run", json=payload)

        assert response.status_code == 200
        run = response.json()
        assert run["status"] == expected_status
        trace = agent_api_client.get(
            f"/api/agent/runs/{run['run_id']}/trace"
        ).json()
        assert not any(
            event["event_type"] == "tool_executed"
            for event in trace["events"]
        )


def test_openai_key_is_not_returned_in_api_or_recorded_in_trace(
    agent_api_client,
    caplog: pytest.LogCaptureFixture,
) -> None:
    captured: list[httpx.Request] = []
    provider = provider_for(
        [completion(content="A safe answer.")],
        captured,
    )
    app.dependency_overrides[get_agent_provider] = lambda: provider

    status = agent_api_client.get("/api/agent/provider")
    run = agent_api_client.post(
        "/api/agent/run", json={"message": "Look up a movie"}
    ).json()
    trace = agent_api_client.get(
        f"/api/agent/runs/{run['run_id']}/trace"
    ).text

    assert status.status_code == 200
    assert _TEST_KEY not in status.text
    assert _TEST_KEY not in json.dumps(run)
    assert _TEST_KEY not in trace
    assert captured[0].headers["authorization"] == f"Bearer {_TEST_KEY}"
    assert _TEST_KEY not in captured[0].content.decode()
    assert _TEST_KEY not in caplog.text
    assert run["status"] == "completed"
