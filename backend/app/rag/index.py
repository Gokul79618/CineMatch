"""Versioned JSON vector index with validated, atomic rebuilds."""

import json
import math
import os
import tempfile
from pathlib import Path
from typing import Sequence

from pydantic import BaseModel, ConfigDict, Field, JsonValue, model_validator

from app.rag.embeddings import EmbeddingEncoder
from app.rag.schemas import ChunkRecord

INDEX_VERSION = 1
MAX_INDEX_BYTES = 25 * 1024 * 1024


class VectorIndexData(BaseModel):
    model_config = ConfigDict(extra="forbid", allow_inf_nan=False)

    index_version: int
    embedding_model_id: str
    dimension: int = Field(ge=0)
    chunks: list[ChunkRecord]
    vectors: list[list[float]]

    @model_validator(mode="after")
    def validate_vectors(self) -> "VectorIndexData":
        if len(self.chunks) != len(self.vectors):
            raise ValueError("Index chunk and vector counts do not match.")
        if len({chunk.chunk_id for chunk in self.chunks}) != len(self.chunks):
            raise ValueError("Index contains duplicate chunk IDs.")
        for vector in self.vectors:
            if len(vector) != self.dimension:
                raise ValueError("Index vector dimensions are inconsistent.")
            if any(not math.isfinite(value) for value in vector):
                raise ValueError("Index contains a non-finite embedding value.")
        if self.chunks and self.dimension == 0:
            raise ValueError("A non-empty index must have a positive dimension.")
        return self


class IndexCompatibilityError(RuntimeError):
    """The stored vector index is incompatible with the configured model."""


class VectorIndex:
    def __init__(self, data: VectorIndexData):
        self.data = data

    @classmethod
    def rebuild(
        cls,
        chunks: Sequence[ChunkRecord],
        encoder: EmbeddingEncoder,
        path: Path | str,
    ) -> "VectorIndex":
        unique: dict[str, ChunkRecord] = {}
        for chunk in chunks:
            previous = unique.get(chunk.chunk_id)
            if previous is not None and previous != chunk:
                raise ValueError("Conflicting data uses the same chunk ID.")
            unique[chunk.chunk_id] = chunk
        ordered_chunks = [unique[key] for key in sorted(unique)]
        vectors = encoder.encode([chunk.text for chunk in ordered_chunks])
        if len(vectors) != len(ordered_chunks):
            raise ValueError("Embedding model returned an unexpected vector count.")
        dimension = len(vectors[0]) if vectors else 0
        if dimension < 1 and vectors:
            raise ValueError("Embedding vectors must have at least one dimension.")
        if any(len(vector) != dimension for vector in vectors):
            raise ValueError("Embedding model returned inconsistent dimensions.")

        data = VectorIndexData(
            index_version=INDEX_VERSION,
            embedding_model_id=encoder.model_id,
            dimension=dimension,
            chunks=ordered_chunks,
            vectors=vectors,
        )
        serialized = data.model_dump_json()
        if len(serialized.encode("utf-8")) > MAX_INDEX_BYTES:
            raise ValueError("RAG index exceeds the 25 MiB size limit.")
        index_path = Path(path)
        index_path.parent.mkdir(parents=True, exist_ok=True)
        temporary_path: Path | None = None
        try:
            with tempfile.NamedTemporaryFile(
                mode="w",
                encoding="utf-8",
                dir=index_path.parent,
                prefix=f".{index_path.name}.",
                suffix=".tmp",
                delete=False,
            ) as temporary:
                temporary.write(serialized)
                temporary.flush()
                os.fsync(temporary.fileno())
                temporary_path = Path(temporary.name)
            os.replace(temporary_path, index_path)
        finally:
            if temporary_path is not None and temporary_path.exists():
                temporary_path.unlink()
        return cls(data)

    @classmethod
    def load(
        cls,
        path: Path | str,
        expected_model_id: str,
    ) -> "VectorIndex":
        index_path = Path(path)
        if not index_path.is_file():
            raise FileNotFoundError("RAG index has not been built.")
        if index_path.stat().st_size > MAX_INDEX_BYTES:
            raise ValueError("RAG index exceeds the configured size limit.")
        data = VectorIndexData.model_validate_json(
            index_path.read_text(encoding="utf-8")
        )
        if data.index_version != INDEX_VERSION:
            raise IndexCompatibilityError(
                "RAG index version is incompatible; rebuild the index."
            )
        if data.embedding_model_id != expected_model_id:
            raise IndexCompatibilityError(
                "RAG embedding model differs from the index; rebuild the index."
            )
        return cls(data)
