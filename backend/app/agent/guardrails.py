"""Independent validation checks for agent input and final output."""

import re
from dataclasses import dataclass
from typing import Any, Sequence

from app.core.config import settings


@dataclass(frozen=True)
class GuardrailResult:
    allowed: bool
    reason_code: str


_OVERRIDE_INTENTS = (
    "ignore all previous instructions",
    "ignore previous instructions",
    "disregard all prior instructions",
    "override your instructions",
    "forget your system prompt",
    "bypass the policy",
    "ignore your safety rules",
)
_PROTECTED_TARGETS = (
    "delete_movie_database",
    "drop database",
    "run sql",
    "execute sql",
    "run shell",
    "execute shell",
    "filesystem",
    "environment variables",
    "credentials",
    "password",
    "api key",
    "unregistered tool",
)
_DISCLOSURE_ACTIONS = ("reveal", "print", "show", "send", "expose", "dump")
_SECRET_TARGETS = ("credentials", "password", "api key", "environment variables", "token")
_DIRECTIVE_HEADS = {
    "bypass",
    "call",
    "delete",
    "disregard",
    "drop",
    "execute",
    "expose",
    "forget",
    "ignore",
    "override",
    "print",
    "reveal",
    "run",
    "send",
    "show",
    "use",
}

_SECRET_PATTERN = re.compile(
    r"(?i)(?:\bsk-[a-z0-9_-]{12,}\b|\bbearer\s+[a-z0-9._-]{12,}\b|"
    r"\b(?:MYSQL_PASSWORD|OPENAI_API_KEY|API_KEY)\s*[:=])"
)
_TRACEBACK_PATTERN = re.compile(
    r"(?im)(?:^Traceback \(most recent call last\):|^\s*File \".+\", line \d+|"
    r"^\w+(?:Error|Exception):)"
)
_RUNTIME_CLAIM_PATTERN = re.compile(
    r"(?i)(?:runtime[^.\n]{0,24}\b\d{1,3}\s*(?:minutes?|mins?)\b|"
    r"\b\d{1,3}\s*(?:minutes?|mins?)\s+(?:long|runtime)\b)"
)
_RATING_CLAIM_PATTERN = re.compile(
    r"(?i)(?:rating[^.\n]{0,24}\b\d(?:\.\d)?\b|"
    r"\brated\s+\d(?:\.\d)?(?:\s*/\s*10)?\b|"
    r"\b\d(?:\.\d)?\s*/\s*10\b)"
)


def check_user_input(message: object, max_length: int = 2000) -> GuardrailResult:
    """Check message shape, size, and high-confidence instruction hijacking."""
    if not isinstance(message, str):
        return GuardrailResult(False, "input_type_invalid")
    normalized = message.strip()
    if not normalized:
        return GuardrailResult(False, "input_empty")
    if len(normalized) > max_length:
        return GuardrailResult(False, "input_too_long")
    if _looks_like_instruction_hijacking(normalized):
        return GuardrailResult(False, "prompt_injection_suspected")
    return GuardrailResult(True, "input_valid")


def _looks_like_instruction_hijacking(message: str) -> bool:
    """Require override intent, command structure, and a protected target."""
    text = " ".join(message.casefold().split())
    has_override = any(marker in text for marker in _OVERRIDE_INTENTS)
    has_protected_target = any(target in text for target in _PROTECTED_TARGETS)
    clauses = re.split(r"[.!?;]+|\b(?:and then|then)\b", text)
    directive_clauses = [
        clause.strip().removeprefix("please ").removeprefix("now ")
        for clause in clauses
    ]
    has_directive_clause = any(
        clause.split(maxsplit=1)[0] in _DIRECTIVE_HEADS
        for clause in directive_clauses
        if clause
    )
    asks_for_secrets = (
        has_directive_clause
        and any(action in text for action in _DISCLOSURE_ACTIONS)
        and any(target in text for target in _SECRET_TARGETS)
    )
    return asks_for_secrets or (
        has_directive_clause
        and has_protected_target
        and (has_override or any(action in text for action in _DISCLOSURE_ACTIONS))
    )


def check_tool_arguments_size(arguments_json: str | None, max_bytes: int) -> GuardrailResult:
    if arguments_json is None:
        return GuardrailResult(False, "tool_arguments_not_json")
    if len(arguments_json.encode("utf-8")) > max_bytes:
        return GuardrailResult(False, "tool_arguments_too_large")
    return GuardrailResult(True, "tool_arguments_size_valid")


def check_final_output(
    response: object,
    max_length: int,
    observations: Sequence[Any] = (),
) -> GuardrailResult:
    """Reject malformed, unsafe, oversized, or unsupported metadata output."""
    if not isinstance(response, str) or not response.strip():
        return GuardrailResult(False, "output_empty_or_invalid")
    if len(response) > max_length:
        return GuardrailResult(False, "output_too_long")
    if _SECRET_PATTERN.search(response):
        return GuardrailResult(False, "output_sensitive_content")
    if settings.mysql_password and settings.mysql_password in response:
        return GuardrailResult(False, "output_sensitive_content")
    if _TRACEBACK_PATTERN.search(response):
        return GuardrailResult(False, "output_internal_error_content")
    if _claims_missing_metadata(response, observations):
        return GuardrailResult(False, "output_unsupported_movie_metadata")
    return GuardrailResult(True, "output_valid")


def _claims_missing_metadata(response: str, observations: Sequence[Any]) -> bool:
    text = response.casefold()
    for observation in observations:
        result = getattr(observation, "result", None)
        for movie in _movie_records(result):
            title = movie.get("title")
            movie_id = movie.get("movie_id")
            mentioned = (
                isinstance(title, str) and title.casefold() in text
            ) or (isinstance(movie_id, str) and movie_id.casefold() in text)
            if not mentioned:
                continue
            if movie.get("runtime_minutes") is None and _RUNTIME_CLAIM_PATTERN.search(response):
                return True
            if movie.get("rating") is None and _RATING_CLAIM_PATTERN.search(response):
                return True
    return False


def _movie_records(value: object) -> list[dict[str, object]]:
    if isinstance(value, dict):
        if {"movie_id", "title", "runtime_minutes", "rating"}.issubset(value):
            return [value]
        items = value.get("items")
        if isinstance(items, list):
            return [record for item in items for record in _movie_records(item)]
    return []
