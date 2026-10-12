"""Safe and repeatable initialization of the MySQL movie catalog."""

import json
from pathlib import Path

from pydantic import ValidationError

from app.core.config import settings
from app.database.connection import connect, execute, has_movie_schema
from app.schemas.movies import MovieCatalogRecord

SCHEMA = """
CREATE TABLE IF NOT EXISTS movies (
    movie_id VARCHAR(128) NOT NULL PRIMARY KEY,
    title VARCHAR(255) NOT NULL,
    language VARCHAR(80) NOT NULL,
    release_year INTEGER NOT NULL,
    runtime_minutes INTEGER,
    overview TEXT NOT NULL,
    rating DECIMAL(3, 1),
    source_url VARCHAR(2048) NOT NULL,
    INDEX idx_movies_title (title),
    INDEX idx_movies_language (language),
    INDEX idx_movies_year (release_year)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
"""

GENRE_SCHEMA = """
CREATE TABLE IF NOT EXISTS genres (
    genre_id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT PRIMARY KEY,
    name VARCHAR(100) NOT NULL,
    UNIQUE KEY uq_genres_name (name)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
"""

MOVIE_GENRE_SCHEMA = """
CREATE TABLE IF NOT EXISTS movie_genres (
    movie_id VARCHAR(128) NOT NULL,
    genre_id BIGINT UNSIGNED NOT NULL,
    PRIMARY KEY (movie_id, genre_id),
    INDEX idx_movie_genres_genre (genre_id),
    CONSTRAINT fk_movie_genres_movie
        FOREIGN KEY (movie_id) REFERENCES movies(movie_id),
    CONSTRAINT fk_movie_genres_genre
        FOREIGN KEY (genre_id) REFERENCES genres(genre_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
"""


def load_catalog(catalog_path: Path | str | None = None) -> list[MovieCatalogRecord]:
    """Load and validate source JSON without modifying the source file."""
    path = Path(catalog_path) if catalog_path is not None else settings.resolve_catalog_path()
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except OSError as exc:
        raise RuntimeError(f"Unable to read movie catalog at {path}: {exc}") from exc
    except json.JSONDecodeError as exc:
        raise ValueError(f"Invalid JSON in movie catalog at {path}: {exc}") from exc

    if not isinstance(payload, list):
        raise ValueError("Movie catalog must be a JSON array.")

    try:
        records = [MovieCatalogRecord.model_validate(item) for item in payload]
    except (ValidationError, TypeError) as exc:
        raise ValueError(f"Movie catalog contains an invalid record: {exc}") from exc

    ids = [record.movie_id for record in records]
    if len(ids) != len(set(ids)):
        raise ValueError("Movie catalog contains duplicate movie_id values.")
    return records


def initialize_database(
    database_name: str | None = None,
    catalog_path: Path | str | None = None,
) -> int:
    """Create tables and insert absent catalog rows without deleting existing data."""
    records = load_catalog(catalog_path)
    with connect(database_name) as connection:
        for statement in (SCHEMA, GENRE_SCHEMA, MOVIE_GENRE_SCHEMA):
            cursor = connection.cursor()
            try:
                cursor.execute(statement)
            finally:
                cursor.close()
        for record in records:
            cursor = execute(
                connection,
                """
                INSERT IGNORE INTO movies
                    (movie_id, title, language, release_year, runtime_minutes,
                     overview, rating, source_url)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                """,
                (
                    record.movie_id,
                    record.title,
                    record.language,
                    record.release_year,
                    record.runtime_minutes,
                    record.overview,
                    record.rating,
                    record.source_url,
                ),
            )
            cursor.close()
            for genre in record.genres:
                cursor = execute(
                    connection,
                    "INSERT IGNORE INTO genres(name) VALUES (%s)",
                    (genre,),
                )
                cursor.close()
                genre_cursor = execute(
                    connection, "SELECT genre_id FROM genres WHERE name = %s", (genre,)
                )
                genre_row = genre_cursor.fetchone()
                genre_cursor.close()
                if genre_row is None:
                    raise RuntimeError(f"Failed to store genre {genre!r}.")
                movie_genre_cursor = execute(
                    connection,
                    """
                    INSERT IGNORE INTO movie_genres(movie_id, genre_id)
                    VALUES (%s, %s)
                    """,
                    (record.movie_id, genre_row["genre_id"]),
                )
                movie_genre_cursor.close()
        count_cursor = execute(connection, "SELECT COUNT(*) AS count FROM movies")
        count = count_cursor.fetchone()["count"]
        count_cursor.close()
    return int(count)


def ensure_database_initialized(
    database_name: str | None = None,
    catalog_path: Path | str | None = None,
) -> None:
    """Initialize an absent database schema and preserve existing databases."""
    with connect(database_name) as connection:
        initialized = has_movie_schema(connection)
    if not initialized:
        initialize_database(database_name, catalog_path)


if __name__ == "__main__":
    total = initialize_database()
    print(
        f"Initialized MySQL schema {settings.resolve_database_name()!r}; "
        f"it contains {total} movie record(s)."
    )
