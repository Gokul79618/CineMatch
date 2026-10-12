"""Safety checks for retrieved evidence before it reaches a provider or client."""

import json
import re

from app.core.config import settings
from app.agent.guardrails import GuardrailResult, _SECRET_PATTERN

_LOCAL_PATH_PATTERN = re.compile(
    r"(?i)(?:\b[A-Z]:\\|file://|(?<!:)//(?:users|home|root|etc|var|tmp)/)"
)
_SENSITIVE_METADATA_KEY = re.compile(
    r'(?i)"[^"]*(?:path|password|secret|token|api[_-]?key)[^"]*"\s*:'
)
_SENSITIVE_URL_PARAMETER = re.compile(
    r"(?i)[?&](?:api[_-]?key|access[_-]?token|token|password|secret)=([^&#\s]+)"
)
_MAX_EVIDENCE_BYTES = 8_000


def check_retrieved_content(
    text: object,
    metadata: object = None,
) -> GuardrailResult:
    if not isinstance(text, str) or not text.strip():
        return GuardrailResult(False, "retrieved_content_invalid")
    if len(text.encode("utf-8")) > _MAX_EVIDENCE_BYTES:
        return GuardrailResult(False, "retrieved_content_too_large")
    searchable = text
    if metadata is not None:
        try:
            searchable += json.dumps(metadata, ensure_ascii=True)
        except (TypeError, ValueError):
            return GuardrailResult(False, "retrieved_metadata_invalid")
    if (
        _SECRET_PATTERN.search(searchable)
        or _LOCAL_PATH_PATTERN.search(searchable)
        or _SENSITIVE_METADATA_KEY.search(searchable)
        or _SENSITIVE_URL_PARAMETER.search(searchable)
        or (settings.mysql_password and settings.mysql_password in searchable)
    ):
        return GuardrailResult(False, "retrieved_content_sensitive")
    return GuardrailResult(True, "retrieved_content_untrusted_allowed")
