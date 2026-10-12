"""Load movie catalog records and explicitly maintained local knowledge docs."""

import json
from pathlib import Path

from app.rag.schemas import KnowledgeDocument
from app.schemas.movies import MovieCatalogRecord

MAX_SOURCE_FILE_BYTES = 5 * 1024 * 1024


def load_knowledge_documents(
    catalog_path: Path | str,
    supporting_documents_path: Path | str,
) -> list[KnowledgeDocument]:
    catalog_file = Path(catalog_path)
    supporting_file = Path(supporting_documents_path)
    if catalog_file.stat().st_size > MAX_SOURCE_FILE_BYTES:
        raise ValueError("Movie catalog exceeds the 5 MiB ingestion limit.")
    raw_movies = json.loads(catalog_file.read_text(encoding="utf-8"))
    if not isinstance(raw_movies, list):
        raise ValueError("Movie catalog must contain a JSON array.")

    documents: list[KnowledgeDocument] = []
    movie_ids: set[str] = set()
    for raw_movie in raw_movies:
        movie = MovieCatalogRecord.model_validate(raw_movie)
        movie_ids.add(movie.movie_id)
        runtime = (
            f"{movie.runtime_minutes} minutes"
            if movie.runtime_minutes is not None
            else "not available in the source catalog"
        )
        rating = (
            str(movie.rating)
            if movie.rating is not None
            else "not available in the source catalog"
        )
        text = (
            f"Title: {movie.title}. Release year: {movie.release_year}. "
            f"Language: {movie.language}. Genres: {', '.join(movie.genres)}. "
            f"Overview: {movie.overview} Runtime: {runtime}. Rating: {rating}."
        )
        documents.append(
            KnowledgeDocument(
                document_id=f"movie:{movie.movie_id}",
                source_title=f"{movie.title} ({movie.release_year})",
                source_reference=movie.source_url,
                movie_id=movie.movie_id,
                text=text,
                metadata=movie.model_dump(mode="json"),
            )
        )

    if supporting_file.exists():
        if supporting_file.stat().st_size > MAX_SOURCE_FILE_BYTES:
            raise ValueError("Supporting documents exceed the 5 MiB ingestion limit.")
        raw_documents = json.loads(supporting_file.read_text(encoding="utf-8"))
        if not isinstance(raw_documents, list):
            raise ValueError("Supporting documents must contain a JSON array.")
        supporting_documents = [
            KnowledgeDocument.model_validate(item) for item in raw_documents
        ]
        if any(
            document.movie_id is not None and document.movie_id not in movie_ids
            for document in supporting_documents
        ):
            raise ValueError(
                "Supporting document movie_id must match a catalog movie."
            )
        documents.extend(supporting_documents)

    ids = [document.document_id for document in documents]
    if len(ids) != len(set(ids)):
        raise ValueError("Knowledge document IDs must be unique.")
    return documents
