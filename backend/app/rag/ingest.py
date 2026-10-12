"""Build the local RAG index from the catalog and maintained JSON documents."""

import sys

from app.core.config import settings
from app.rag.chunking import chunk_documents
from app.rag.documents import load_knowledge_documents
from app.rag.embeddings import EmbeddingDependencyError, SentenceTransformerEncoder
from app.rag.index import VectorIndex


def main() -> int:
    try:
        documents = load_knowledge_documents(
            settings.resolve_catalog_path(),
            settings.resolve_rag_documents_path(),
        )
        chunks = chunk_documents(
            documents,
            max_chars=settings.rag_chunk_size,
            overlap_chars=settings.rag_chunk_overlap,
        )
        encoder = SentenceTransformerEncoder(
            settings.rag_embedding_model,
            settings.rag_embedding_revision,
        )
        index = VectorIndex.rebuild(
            chunks,
            encoder,
            settings.resolve_rag_index_path(),
        )
    except (EmbeddingDependencyError, OSError, ValueError, RuntimeError) as exc:
        print(f"RAG index was not changed: {exc}", file=sys.stderr)
        return 1

    print(
        f"Built local RAG index with {len(index.data.chunks)} chunks "
        f"using {index.data.embedding_model_id}."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
