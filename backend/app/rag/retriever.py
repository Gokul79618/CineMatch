"""Bounded cosine-similarity retrieval over the local versioned index."""

import math
from pathlib import Path
from threading import Lock
from typing import Protocol, Sequence

from app.core.config import settings
from app.rag.embeddings import EmbeddingDependencyError, EmbeddingEncoder, SentenceTransformerEncoder
from app.rag.index import IndexCompatibilityError, VectorIndex
from app.rag.schemas import (
    ChunkRecord,
    RetrievalRequest,
    RetrievalResponse,
    RetrievedPassage,
)

MAX_RETRIEVAL_RESPONSE_BYTES = 32 * 1024
MINIMUM_RETRIEVAL_TOOL_SIMILARITY = 0.30


class RagUnavailableError(RuntimeError):
    """The configured local model or compatible index is not ready."""


class RagSearch(Protocol):
    def retrieve(self, request: RetrievalRequest) -> RetrievalResponse: ...


class RagRetriever:
    def __init__(self, index: VectorIndex, encoder: EmbeddingEncoder):
        if index.data.embedding_model_id != encoder.model_id:
            raise IndexCompatibilityError(
                "RAG embedding model differs from the index; rebuild the index."
            )
        self.index = index
        self.encoder = encoder

    @classmethod
    def from_path(
        cls,
        path: Path | str,
        encoder: EmbeddingEncoder,
    ) -> "RagRetriever":
        return cls(VectorIndex.load(path, encoder.model_id), encoder)

    def retrieve(self, request: RetrievalRequest) -> RetrievalResponse:
        data = self.index.data
        if not data.chunks:
            return RetrievalResponse(status="no_results", count=0, passages=[])

        query_vectors = self.encoder.encode([request.query])
        if (
            len(query_vectors) != 1
            or len(query_vectors[0]) != data.dimension
            or any(not math.isfinite(value) for value in query_vectors[0])
        ):
            raise IndexCompatibilityError(
                "Query embedding is incompatible with the stored index."
            )
        query_vector = query_vectors[0]

        scored: list[tuple[float, str, ChunkRecord]] = []
        for chunk, vector in zip(data.chunks, data.vectors, strict=True):
            if request.movie_id and chunk.movie_id != request.movie_id:
                continue
            if (
                request.source_reference
                and chunk.source_reference != request.source_reference
            ):
                continue
            similarity = _cosine_similarity(query_vector, vector)
            if similarity >= request.minimum_similarity:
                scored.append((similarity, chunk.chunk_id, chunk))
        scored.sort(key=lambda item: (-item[0], item[1]))
        passages = [
            RetrievedPassage(
                source_title=chunk.source_title,
                source_reference=chunk.source_reference,
                movie_id=chunk.movie_id,
                text=chunk.text,
                similarity=similarity,
                metadata=chunk.metadata,
            )
            for similarity, _, chunk in scored[: request.top_k]
        ]
        while passages:
            response = RetrievalResponse(
                status="results",
                count=len(passages),
                passages=passages,
            )
            if len(response.model_dump_json().encode("utf-8")) <= MAX_RETRIEVAL_RESPONSE_BYTES:
                return response
            passages.pop()
        return RetrievalResponse(status="no_results", count=0, passages=[])


def _cosine_similarity(first: Sequence[float], second: Sequence[float]) -> float:
    if len(first) != len(second):
        raise IndexCompatibilityError("RAG vector dimensions do not match.")
    first_norm = math.sqrt(sum(value * value for value in first))
    second_norm = math.sqrt(sum(value * value for value in second))
    if first_norm == 0 or second_norm == 0:
        return 0.0
    score = sum(a * b for a, b in zip(first, second, strict=True)) / (
        first_norm * second_norm
    )
    return max(-1.0, min(1.0, score))


class ConfiguredRagRetriever:
    """Lazy application service; the model and index load only on retrieval."""

    def __init__(self) -> None:
        self._retriever: RagRetriever | None = None
        self._lock = Lock()

    def retrieve(self, request: RetrievalRequest) -> RetrievalResponse:
        if self._retriever is None:
            with self._lock:
                if self._retriever is None:
                    try:
                        encoder = SentenceTransformerEncoder(
                            settings.rag_embedding_model,
                            settings.rag_embedding_revision,
                            local_files_only=True,
                        )
                        self._retriever = RagRetriever.from_path(
                            settings.resolve_rag_index_path(), encoder
                        )
                    except (
                        EmbeddingDependencyError,
                        FileNotFoundError,
                        IndexCompatibilityError,
                        ValueError,
                    ) as exc:
                        raise RagUnavailableError(
                            "The local embedding model or compatible RAG index is unavailable."
                        ) from exc
        return self._retriever.retrieve(request)


_configured_retriever = ConfiguredRagRetriever()


def configured_rag_retriever() -> ConfiguredRagRetriever:
    return _configured_retriever


def retrieve_movie_context(
    query: str,
    top_k: int = 3,
    minimum_similarity: float = settings.rag_minimum_similarity,
    movie_id: str | None = None,
    source_reference: str | None = None,
    retriever: RagSearch | None = None,
) -> RetrievalResponse:
    request = RetrievalRequest(
        query=query,
        top_k=top_k,
        minimum_similarity=max(
            minimum_similarity,
            settings.rag_minimum_similarity,
            MINIMUM_RETRIEVAL_TOOL_SIMILARITY,
        ),
        movie_id=movie_id,
        source_reference=source_reference,
    )
    return (retriever or configured_rag_retriever()).retrieve(request)
