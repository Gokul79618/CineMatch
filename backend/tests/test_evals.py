"""Deterministic metric and safety-evaluation tests."""

from app.agent.policy import HarnessPolicy
from app.agent.schemas import AgentRunConfig
from app.agent.tool_registry import build_movie_tool_registry
from app.agent.guardrails import check_final_output
from app.evals.runner import (
    GoldenCase,
    calculate_metrics,
    citation_matches,
)
from app.rag.schemas import RetrievalResponse, RetrievedPassage


def case(
    case_id: str,
    *,
    answerable: bool = True,
    relevant: list[str] | None = None,
    source_references: dict[str, str] | None = None,
) -> GoldenCase:
    return GoldenCase(
        case_id=case_id,
        query="test query",
        answerable=answerable,
        minimum_similarity=0.25,
        relevant_document_ids=relevant or [],
        supported_facts=[],
        source_references=source_references or {},
        unsupported_claims=[],
    )


def passage(movie_id: str, source_reference: str) -> RetrievedPassage:
    return RetrievedPassage(
        source_title=movie_id,
        source_reference=source_reference,
        movie_id=movie_id,
        text="Verified evidence excerpt.",
        similarity=0.9,
        metadata={},
    )


def test_retrieval_metrics_compute_recall_mrr_coverage_and_citations() -> None:
    target_reference = "https://example.test/target"
    unrelated_reference = "https://example.test/other"
    cases = [
        case(
            "target",
            relevant=["movie:target"],
            source_references={"movie:target": target_reference},
        ),
        case("unanswerable", answerable=False),
    ]
    results = {
        "target": RetrievalResponse(
            status="results",
            count=2,
            passages=[
                passage("other", unrelated_reference),
                passage("target", target_reference),
            ],
        ),
        "unanswerable": RetrievalResponse(
            status="no_results",
            count=0,
            passages=[],
        ),
    }

    metrics = calculate_metrics(
        cases,
        results,
        {
            "movie:target": target_reference,
            "movie:other": unrelated_reference,
        },
        top_k=3,
    )

    assert metrics == {
        "recall_at_k": 1.0,
        "mean_reciprocal_rank": 0.5,
        "retrieval_coverage": 1.0,
        "empty_result_accuracy": 1.0,
        "source_attribution_correctness": 1.0,
    }


def test_citation_metric_detects_wrong_and_missing_references() -> None:
    expected = {"movie:target": "https://example.test/target"}
    assert citation_matches(
        "movie:target",
        "https://example.test/target",
        expected,
    )
    assert not citation_matches(
        "movie:target",
        "https://example.test/fabricated",
        expected,
    )
    assert not citation_matches("movie:target", "", expected)


def test_unsupported_movie_rating_claim_is_rejected() -> None:
    observation = type(
        "Observation",
        (),
        {
            "result": {
                "movie_id": "baashha-1995",
                "title": "Baashha",
                "runtime_minutes": None,
                "rating": None,
            }
        },
    )()
    result = check_final_output("Baashha has a rating of 9.1.", 4000, [observation])
    assert not result.allowed
    assert result.reason_code == "output_unsupported_movie_metadata"


def test_unregistered_tool_remains_denied_by_evaluation_safety_boundary() -> None:
    registry = build_movie_tool_registry()
    authorization = HarnessPolicy(AgentRunConfig()).authorize(
        registry.get("delete_movie_database"),
        "eval-malicious-call",
    )
    assert not authorization.allowed
    assert authorization.reason == "Tool is not registered."

