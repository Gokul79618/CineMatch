"""Deterministic character-based chunking with bounded overlap."""

import hashlib

from app.rag.schemas import ChunkRecord, KnowledgeDocument


def chunk_text(text: str, max_chars: int = 800, overlap_chars: int = 100) -> list[str]:
    if max_chars < 1 or max_chars > 2000:
        raise ValueError("max_chars must be between 1 and 2000")
    if overlap_chars < 0 or overlap_chars >= max_chars:
        raise ValueError("overlap_chars must be non-negative and smaller than max_chars")

    normalized = " ".join(text.split())
    if not normalized:
        return []

    chunks: list[str] = []
    start = 0
    while start < len(normalized):
        end = min(start + max_chars, len(normalized))
        if end < len(normalized):
            boundary = normalized.rfind(" ", start + 1, end)
            if boundary > start:
                end = boundary
        piece = normalized[start:end].strip()
        if piece:
            chunks.append(piece)
        if end >= len(normalized):
            break
        next_start = max(start + 1, end - overlap_chars)
        while next_start < end and normalized[next_start].isspace():
            next_start += 1
        start = next_start
    return chunks


def chunk_documents(
    documents: list[KnowledgeDocument],
    max_chars: int = 800,
    overlap_chars: int = 100,
) -> list[ChunkRecord]:
    chunks: list[ChunkRecord] = []
    for document in documents:
        for text in chunk_text(document.text, max_chars, overlap_chars):
            digest = hashlib.sha256(
                f"{document.document_id}\0{text}".encode("utf-8")
            ).hexdigest()[:32]
            chunks.append(
                ChunkRecord(
                    document_id=document.document_id,
                    chunk_id=f"chunk:{digest}",
                    source_title=document.source_title,
                    source_reference=document.source_reference,
                    movie_id=document.movie_id,
                    text=text,
                    metadata=document.metadata,
                )
            )
    return chunks
