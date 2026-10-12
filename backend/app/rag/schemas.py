"""Validated contracts for source documents and local retrieval results."""

import json
import re
from typing import Literal
from urllib.parse import urlparse

from pydantic import BaseModel, ConfigDict, Field, JsonValue, field_validator

from app.core.config import settings


class KnowledgeDocument(BaseModel):
    model_config = ConfigDict(extra="forbid", allow_inf_nan=False)

    document_id: str = Field(min_length=1, max_length=160)
    source_title: str = Field(min_length=1, max_length=200)
    source_reference: str = Field(min_length=1, max_length=500)
    movie_id: str | None = Field(default=None, max_length=100)
    text: str = Field(min_length=1, max_length=20_000)
    metadata: dict[str, JsonValue] = Field(default_factory=dict)

    @field_validator("document_id", "source_title", "text")
    @classmethod
    def normalize_required_text(cls, value: str) -> str:
        value = " ".join(value.split())
        if not value:
            raise ValueError("must not be blank")
        return value

    @field_validator("source_reference")
    @classmethod
    def validate_source_reference(cls, value: str) -> str:
        value = value.strip()
        parsed = urlparse(value)
        is_https_url = parsed.scheme == "https" and bool(parsed.netloc)
        is_source_identifier = bool(
            re.fullmatch(r"source:[A-Za-z0-9._:-]{1,200}", value)
        )
        if not is_https_url and not is_source_identifier:
            raise ValueError(
                "source_reference must be an HTTPS URL or source:<identifier>"
            )
        return value

    @field_validator("movie_id")
    @classmethod
    def normalize_movie_id(cls, value: str | None) -> str | None:
        if value is None:
            return None
        value = value.strip()
        if not value:
            raise ValueError("movie_id must not be blank when supplied")
        return value

    @field_validator("metadata")
    @classmethod
    def validate_metadata(cls, value: dict[str, JsonValue]) -> dict[str, JsonValue]:
        if len(json.dumps(value, ensure_ascii=True).encode("utf-8")) > 4096:
            raise ValueError("metadata exceeds the 4096-byte limit")
        if _has_sensitive_key(value):
            raise ValueError("metadata contains a prohibited field")
        return value


class ChunkRecord(BaseModel):
    model_config = ConfigDict(extra="forbid", allow_inf_nan=False)

    document_id: str
    chunk_id: str
    source_title: str
    source_reference: str
    movie_id: str | None
    text: str
    metadata: dict[str, JsonValue]


class RetrievalRequest(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
        allow_inf_nan=False,
        validate_default=True,
    )

    query: str = Field(min_length=1, max_length=500)
    top_k: int = Field(default=settings.rag_default_top_k, ge=1, le=5)
    minimum_similarity: float = Field(
        default=settings.rag_minimum_similarity,
        ge=-1,
        le=1,
    )
    movie_id: str | None = Field(default=None, min_length=1, max_length=100)
    source_reference: str | None = Field(default=None, min_length=1, max_length=500)

    @field_validator("query")
    @classmethod
    def normalize_query(cls, value: str) -> str:
        value = " ".join(value.split())
        if not value:
            raise ValueError("query must not be blank")
        return value

    @field_validator("movie_id", "source_reference")
    @classmethod
    def normalize_filters(cls, value: str | None) -> str | None:
        return value.strip() if value else None


class RetrievedPassage(BaseModel):
    model_config = ConfigDict(extra="forbid", allow_inf_nan=False)

    source_title: str = Field(max_length=200)
    source_reference: str = Field(max_length=500)
    movie_id: str | None = Field(default=None, max_length=100)
    text: str = Field(max_length=2000)
    similarity: float = Field(ge=-1, le=1)
    metadata: dict[str, JsonValue] = Field(default_factory=dict)


class RetrievalResponse(BaseModel):
    model_config = ConfigDict(extra="forbid", allow_inf_nan=False)

    status: Literal["results", "no_results"]
    count: int = Field(ge=0, le=5)
    passages: list[RetrievedPassage] = Field(max_length=5)


def _has_sensitive_key(value: object) -> bool:
    if isinstance(value, dict):
        return any(
            re.search(r"(?:path|password|secret|token|api[_-]?key)", str(key), re.I)
            or _has_sensitive_key(child)
            for key, child in value.items()
        )
    if isinstance(value, list):
        return any(_has_sensitive_key(child) for child in value)
    return False
