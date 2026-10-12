"""Replaceable local embedding interface and Sentence Transformers adapter."""

from importlib import import_module
from pathlib import Path
from threading import Lock
from typing import Protocol, Sequence


class EmbeddingDependencyError(RuntimeError):
    """The configured local embedding runtime or model is unavailable."""


class EmbeddingEncoder(Protocol):
    @property
    def model_id(self) -> str: ...

    def encode(self, texts: Sequence[str]) -> list[list[float]]: ...


class SentenceTransformerEncoder:
    def __init__(
        self,
        model_name: str = "sentence-transformers/all-MiniLM-L6-v2",
        revision: str = "main",
        local_files_only: bool = False,
    ) -> None:
        try:
            sentence_transformers = import_module("sentence_transformers")
        except ModuleNotFoundError as exc:
            if exc.name == "sentence_transformers":
                raise EmbeddingDependencyError(
                    "Missing dependency 'sentence-transformers'. Install "
                    "backend requirements and make the configured local model "
                    "available before building the RAG index."
                ) from exc
            raise
        try:
            self._model = sentence_transformers.SentenceTransformer(
                model_name,
                revision=revision,
                device="cpu",
                local_files_only=local_files_only,
            )
        except OSError as exc:
            raise EmbeddingDependencyError(
                "The configured embedding model is not available locally. "
                "Download or cache the configured model, then rebuild the index."
            ) from exc
        resolved_revision = revision
        try:
            hub = import_module("huggingface_hub")
            cached_config = hub.try_to_load_from_cache(
                model_name,
                "config.json",
                revision=revision,
            )
            if isinstance(cached_config, str):
                resolved_revision = Path(cached_config).parent.name
        except (AttributeError, OSError, ValueError):
            pass
        self._model_id = f"{model_name}@{resolved_revision}"
        self._encode_lock = Lock()

    @property
    def model_id(self) -> str:
        return self._model_id

    def encode(self, texts: Sequence[str]) -> list[list[float]]:
        if not texts:
            return []
        with self._encode_lock:
            vectors = self._model.encode(
                list(texts),
                convert_to_numpy=True,
                normalize_embeddings=True,
                show_progress_bar=False,
            )
        return [[float(value) for value in vector] for vector in vectors.tolist()]
