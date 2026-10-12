"""Bounded orchestration loop with input, tool, and output guardrails."""

import asyncio
import hashlib
import json
import re
import time
from pathlib import Path
from uuid import uuid4

from pydantic import TypeAdapter, ValidationError

from app.agent.guardrails import (
    check_final_output,
    check_tool_arguments_size,
    check_user_input,
)
from app.agent.policy import HarnessPolicy
from app.agent.provider import AgentProvider
from app.agent.schemas import (
    AgentDecision,
    AgentRunConfig,
    AgentRunResponse,
    FinalDecision,
    ToolObservation,
    TraceEvidence,
)
from app.agent.tool_registry import build_movie_tool_registry
from app.agent.trace import RunTrace, TraceStore
from app.core.config import settings
from app.schemas.movies import Movie, MovieResults
from app.rag.guardrails import check_retrieved_content
from app.rag.retriever import RagSearch, RagUnavailableError
from app.rag.schemas import RetrievalResponse

DECISION_ADAPTER = TypeAdapter(AgentDecision)
MAX_TOOL_ARGUMENT_BYTES = 8_192
SECRET_VALUE_PATTERN = re.compile(
    r"(?i)\b(?:sk-[a-z0-9_-]{12,}|bearer\s+[a-z0-9._-]{12,})\b"
)


class AgentOrchestrator:
    def __init__(
        self,
        provider: AgentProvider,
        trace_store: TraceStore,
        database_name: str | None = None,
        catalog_path: Path | str | None = None,
        rag_retriever: RagSearch | None = None,
    ):
        self.provider = provider
        self.trace_store = trace_store
        self.registry = build_movie_tool_registry(
            database_name, catalog_path, rag_retriever
        )

    async def run(self, message: str, config: AgentRunConfig) -> AgentRunResponse:
        run_id = uuid4()
        trace = RunTrace(run_id)
        policy = HarnessPolicy(config)
        observations: list[ToolObservation] = []
        tool_call_count = 0
        consecutive_errors = 0
        iterations = 0
        status = "invalid_decision"
        final_response = ""
        invalid_output: object | None = None
        output_was_rejected = False
        deadline = time.monotonic() + config.timeout_seconds
        trace.add("run_started", iteration=0, result_summary="Agent run accepted.")

        input_check = check_user_input(message)
        self._record_guardrail(
            trace,
            "input",
            input_check.allowed,
            input_check.reason_code,
            iteration=0,
            execution_blocked=not input_check.allowed,
        )
        if not input_check.allowed:
            status = "input_denied"
            final_response = (
                "This request was blocked by input safety checks. "
                "Please ask a movie-related question without instructions "
                "to bypass system safeguards."
            )

        iterations_to_run = (
            range(1, config.max_iterations + 1)
            if input_check.allowed
            else range(1, 1)
        )
        for iteration in iterations_to_run:
            iterations = iteration
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                status = "timeout"
                final_response = "The agent request exceeded its configured timeout."
                trace.add("timeout", iteration=iteration, error=final_response)
                break
            try:
                raw_decision = await asyncio.wait_for(
                    self.provider.decide(message, observations), timeout=remaining
                )
            except asyncio.TimeoutError:
                status = "timeout"
                final_response = "The agent request exceeded its configured timeout."
                trace.add("timeout", iteration=iteration, error=final_response)
                break
            except Exception:
                status = "provider_error"
                final_response = "The decision provider failed; no further action was taken."
                trace.add("provider_error", iteration=iteration, error=final_response)
                break

            try:
                decision = DECISION_ADAPTER.validate_python(raw_decision)
            except (ValidationError, TypeError, ValueError):
                if (
                    isinstance(raw_decision, dict)
                    and raw_decision.get("type") == "final"
                ):
                    raw_response = raw_decision.get("response")
                    raw_output_check = check_final_output(
                        raw_response, config.max_response_chars, observations
                    )
                    trace.add(
                        "decision_received",
                        iteration=iteration,
                        decision={"type": "final"},
                    )
                    if raw_output_check.allowed:
                        status = "invalid_decision"
                        final_response = (
                            "The decision provider returned an invalid decision."
                        )
                        self._record_guardrail(
                            trace,
                            "model_decision",
                            False,
                            "decision_schema_invalid",
                            iteration=iteration,
                            execution_blocked=True,
                        )
                        trace.add(
                            "invalid_decision",
                            iteration=iteration,
                            error="Provider returned a malformed final decision.",
                        )
                    else:
                        invalid_output = raw_response
                        output_was_rejected = True
                        status = "output_denied"
                        final_response = self._safe_output_denial()
                        trace.add(
                            "invalid_decision",
                            iteration=iteration,
                            error="Provider returned an invalid final response.",
                        )
                else:
                    status = "invalid_decision"
                    final_response = "The decision provider returned an invalid decision."
                    self._record_guardrail(
                        trace,
                        "model_decision",
                        False,
                        "decision_schema_invalid",
                        iteration=iteration,
                        execution_blocked=True,
                    )
                    trace.add("invalid_decision", iteration=iteration, error=final_response)
                break

            if isinstance(decision, FinalDecision):
                trace.add(
                    "decision_received",
                    iteration=iteration,
                    decision={"type": decision.type},
                    result_summary="Provider returned a final response.",
                )
                status = "completed"
                final_response = decision.response
                break

            tool_call_count += 1
            try:
                encoded_args = json.dumps(
                    decision.arguments, sort_keys=True, separators=(",", ":")
                )
            except (TypeError, ValueError):
                encoded_args = None
            safe_arguments = (
                self._trace_safe_arguments(decision.arguments)
                if encoded_args is not None
                and len(encoded_args.encode("utf-8")) <= MAX_TOOL_ARGUMENT_BYTES
                else {"_truncated": "Arguments are invalid or exceed 8192 bytes."}
            )
            if decision.tool_name == "retrieve_movie_context" and "query" in safe_arguments:
                safe_arguments["query"] = "[OMITTED]"
            trace.add(
                "decision_received",
                iteration=iteration,
                decision={
                    "type": decision.type,
                    "tool_name": decision.tool_name,
                    "arguments": safe_arguments,
                },
                requested_tool=decision.tool_name,
                arguments=safe_arguments,
            )

            size_check = check_tool_arguments_size(
                encoded_args, MAX_TOOL_ARGUMENT_BYTES
            )
            if not size_check.allowed:
                status = "invalid_decision"
                final_response = "The requested tool arguments exceed the allowed size."
                self._record_guardrail(
                    trace,
                    "tool_arguments",
                    False,
                    size_check.reason_code,
                    iteration=iteration,
                    requested_tool=decision.tool_name,
                    execution_blocked=True,
                )
                trace.add(
                    "tool_denied",
                    iteration=iteration,
                    requested_tool=decision.tool_name,
                    denial_reason=size_check.reason_code,
                    error="Tool arguments exceeded the configured size limit.",
                    execution_blocked=True,
                )
                break

            signature = hashlib.sha256(
                f"{decision.tool_name}\0{encoded_args}".encode("utf-8")
            ).hexdigest()
            registered_tool = self.registry.get(decision.tool_name)
            authorization = policy.authorize(registered_tool, signature)
            reason_code = self._authorization_reason_code(authorization.reason)
            trace.add(
                "tool_authorization",
                iteration=iteration,
                requested_tool=decision.tool_name,
                arguments=safe_arguments,
                authorized=authorization.allowed,
                denial_reason=authorization.reason,
                execution_blocked=not authorization.allowed,
            )
            self._record_guardrail(
                trace,
                "tool_authorization",
                authorization.allowed,
                reason_code,
                iteration=iteration,
                requested_tool=decision.tool_name,
                authorized=authorization.allowed,
                denial_reason=authorization.reason,
                execution_blocked=not authorization.allowed,
            )
            if not authorization.allowed:
                status = "policy_denied"
                final_response = "The requested action was denied by policy."
                trace.add(
                    "tool_denied",
                    iteration=iteration,
                    requested_tool=decision.tool_name,
                    authorized=False,
                    denial_reason=reason_code,
                    execution_blocked=True,
                )
                break

            assert registered_tool is not None
            try:
                validated_arguments = registered_tool.input_schema.model_validate(
                    decision.arguments
                )
            except ValidationError:
                consecutive_errors += 1
                self._record_guardrail(
                    trace,
                    "tool_arguments",
                    False,
                    "tool_arguments_schema_invalid",
                    iteration=iteration,
                    requested_tool=decision.tool_name,
                    authorized=True,
                    execution_blocked=True,
                )
                trace.add(
                    "tool_validation_error",
                    iteration=iteration,
                    requested_tool=decision.tool_name,
                    authorized=True,
                    denial_reason="tool_arguments_schema_invalid",
                    error="Tool arguments did not match the registered schema.",
                    execution_blocked=True,
                )
                observations.append(
                    ToolObservation(
                        tool_name=decision.tool_name,
                        arguments=safe_arguments,
                        error="Tool arguments did not match the registered schema.",
                    )
                )
                if consecutive_errors >= config.max_consecutive_tool_errors:
                    status = "tool_error_limit"
                    final_response = (
                        "The maximum consecutive tool error limit was reached."
                    )
                    break
                continue

            self._record_guardrail(
                trace,
                "tool_arguments",
                True,
                "tool_arguments_schema_valid",
                iteration=iteration,
                requested_tool=decision.tool_name,
                authorized=True,
                execution_blocked=False,
            )
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                status = "timeout"
                final_response = "The agent request exceeded its configured timeout."
                trace.add("timeout", iteration=iteration, error=final_response)
                break
            try:
                result = await asyncio.wait_for(
                    asyncio.to_thread(
                        registered_tool.execute, **validated_arguments.model_dump()
                    ),
                    timeout=remaining,
                )
            except asyncio.TimeoutError:
                status = "timeout"
                final_response = "The agent request exceeded its configured timeout."
                trace.add("timeout", iteration=iteration, error=final_response)
                break
            except RagUnavailableError:
                status = "retrieval_unavailable"
                final_response = (
                    "Local retrieval is not ready. Install the configured "
                    "embedding dependency and build the RAG index."
                )
                trace.add(
                    "tool_execution_error",
                    iteration=iteration,
                    requested_tool=decision.tool_name,
                    authorized=True,
                    error="Local retrieval model or index is unavailable.",
                )
                break
            except Exception:
                consecutive_errors += 1
                error_summary = "The registered tool failed during execution."
                trace.add(
                    "tool_execution_error",
                    iteration=iteration,
                    requested_tool=decision.tool_name,
                    authorized=True,
                    error=error_summary,
                )
                observations.append(
                    ToolObservation(
                        tool_name=decision.tool_name,
                        arguments=safe_arguments,
                        error=error_summary,
                    )
                )
                if consecutive_errors >= config.max_consecutive_tool_errors:
                    status = "tool_error_limit"
                    final_response = (
                        "The maximum consecutive tool error limit was reached."
                    )
                    break
                continue

            consecutive_errors = 0
            if isinstance(result, RetrievalResponse):
                result = self._guard_retrieved_result(result, trace, iteration)
            result_value = self._provider_value(result)
            trace.add(
                "tool_executed",
                iteration=iteration,
                requested_tool=decision.tool_name,
                authorized=True,
                result_summary=self._result_summary(result),
                evidence=self._trace_evidence(result),
            )
            observations.append(
                ToolObservation(
                    tool_name=decision.tool_name,
                    arguments=safe_arguments,
                    result=result_value,
                    content_trust=(
                        "untrusted_retrieved_content"
                        if decision.tool_name == "retrieve_movie_context"
                        else "untrusted_catalog_data"
                    ),
                )
            )
        else:
            if input_check.allowed:
                status = "iteration_limit"
                final_response = "The maximum agent iteration limit was reached."
                trace.add(
                    "iteration_limit",
                    iteration=iterations,
                    result_summary=final_response,
                )

        if not final_response:
            final_response = "The agent run ended without a final response."

        output_candidate = invalid_output if output_was_rejected else final_response
        output_check = check_final_output(
            output_candidate, config.max_response_chars, observations
        )
        self._record_guardrail(
            trace,
            "output",
            output_check.allowed,
            output_check.reason_code,
            iteration=iterations,
            execution_blocked=not output_check.allowed,
        )
        if not output_check.allowed:
            status = "output_denied"
            final_response = self._safe_output_denial()
        else:
            final_response = final_response.strip()

        trace.add(
            "run_finished",
            iteration=iterations,
            result_summary=f"Agent run ended with status {status}.",
            execution_status=status,
        )
        trace.add(
            "run_ended",
            iteration=iterations,
            result_summary=f"Agent run ended with status {status}.",
            execution_status=status,
        )
        self.trace_store.save(trace, status, iterations, tool_call_count)
        return AgentRunResponse(
            run_id=run_id,
            final_response=final_response,
            status=status,
            provider_mode=getattr(self.provider, "mode", "custom"),
            provider_model=getattr(self.provider, "model", "custom"),
            iteration_count=iterations,
            tool_call_count=tool_call_count,
            trace_summary=trace.summary(),
        )

    @staticmethod
    def _record_guardrail(
        trace: RunTrace,
        stage: str,
        allowed: bool,
        reason_code: str,
        *,
        iteration: int,
        execution_blocked: bool,
        requested_tool: str | None = None,
        authorized: bool | None = None,
        denial_reason: str | None = None,
    ) -> None:
        trace.add(
            "guardrail_check",
            iteration=iteration,
            requested_tool=requested_tool,
            authorized=authorized,
            denial_reason=denial_reason,
            guardrail_stage=stage,
            guardrail_result="allowed" if allowed else "denied",
            reason_code=reason_code,
            execution_blocked=execution_blocked,
        )

    @staticmethod
    def _authorization_reason_code(reason: str | None) -> str:
        if reason is None:
            return "tool_authorized"
        if reason == "Tool is not registered.":
            return "tool_not_registered"
        if reason == "Tool is registered but not permitted.":
            return "tool_not_permitted"
        if reason == "Repeated identical tool call denied.":
            return "repeated_tool_call"
        return "tool_policy_denied"

    @staticmethod
    def _safe_output_denial() -> str:
        return (
            "The generated response could not be safely returned. "
            "Please rephrase your question or try again."
        )

    @staticmethod
    def _trace_safe_arguments(arguments: dict[str, object]) -> dict[str, object]:
        def sanitize(value: object, key: str = "") -> object:
            if re.search(r"(?:api[_-]?key|secret|token|password)", key, re.I):
                return "[REDACTED]"
            if isinstance(value, dict):
                return {
                    str(child_key): sanitize(child_value, str(child_key))
                    for child_key, child_value in value.items()
                }
            if isinstance(value, list):
                return [sanitize(item) for item in value]
            if isinstance(value, str):
                redacted = SECRET_VALUE_PATTERN.sub("[REDACTED]", value)
                if settings.mysql_password:
                    redacted = redacted.replace(
                        settings.mysql_password, "[REDACTED]"
                    )
                return redacted
            return value

        return {
            str(key): sanitize(value, str(key))
            for key, value in arguments.items()
        }

    @staticmethod
    def _provider_value(value: object) -> object:
        if isinstance(value, (Movie, MovieResults, RetrievalResponse)):
            return value.model_dump(mode="json")
        return value

    @staticmethod
    def _result_summary(value: object) -> str:
        if isinstance(value, RetrievalResponse):
            return (
                f"Retrieved {value.count} source-attributed passage(s)."
                if value.passages
                else "The local knowledge base returned no sufficiently relevant evidence."
            )
        if isinstance(value, MovieResults):
            if not value.items:
                return f"Search returned no matches (0 of {value.count})."
            titles = ", ".join(movie.title for movie in value.items[:3])
            return (
                f"Search returned {value.count} match(es); "
                f"first result(s): {titles}."
            )
        if isinstance(value, Movie):
            return f"Retrieved movie record {value.movie_id}."
        if value is None:
            return "No movie record matched the requested ID."
        return "Tool execution returned a structured result."

    def _guard_retrieved_result(
        self,
        result: RetrievalResponse,
        trace: RunTrace,
        iteration: int,
    ) -> RetrievalResponse:
        safe_passages = []
        for passage in result.passages:
            check = check_retrieved_content(
                f"{passage.source_title}\n{passage.source_reference}\n{passage.text}",
                passage.metadata,
            )
            self._record_guardrail(
                trace,
                "retrieved_content",
                check.allowed,
                check.reason_code,
                iteration=iteration,
                requested_tool="retrieve_movie_context",
                execution_blocked=not check.allowed,
            )
            if check.allowed:
                safe_passages.append(passage)
        if not result.passages:
            self._record_guardrail(
                trace,
                "retrieved_content",
                True,
                "retrieved_content_empty",
                iteration=iteration,
                requested_tool="retrieve_movie_context",
                execution_blocked=False,
            )
        return result.model_copy(
            update={
                "passages": safe_passages,
                "count": len(safe_passages),
                "status": "results" if safe_passages else "no_results",
            }
        )

    @staticmethod
    def _trace_evidence(value: object) -> list[TraceEvidence] | None:
        if not isinstance(value, RetrievalResponse) or not value.passages:
            return None
        return [
            TraceEvidence(
                source_title=passage.source_title,
                source_reference=passage.source_reference,
                movie_id=passage.movie_id,
                excerpt=passage.text[:600],
                similarity=passage.similarity,
            )
            for passage in value.passages
        ]
