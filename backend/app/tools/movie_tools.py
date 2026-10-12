"""Deterministic MySQL-backed movie search, filtering, and lookup tools."""

from pathlib import Path
from typing import Any

from mysql.connector import MySQLConnection

from app.database.connection import connect, execute
from app.database.init_db import ensure_database_initialized
from app.schemas.movies import (
    Movie,
    MovieFilterRequest,
    MovieIdRequest,
    MovieResults,
    MovieSearchRequest,
    MovieStats,
)


def _movie_from_row(connection: MySQLConnection, row: dict[str, Any]) -> Movie:
    genre_cursor = execute(
        connection,
        """
        SELECT g.name
        FROM genres AS g
        JOIN movie_genres AS mg ON mg.genre_id = g.genre_id
        WHERE mg.movie_id = %s
        ORDER BY LOWER(g.name)
        """,
        (row["movie_id"],),
    )
    genres = genre_cursor.fetchall()
    genre_cursor.close()
    return Movie(
        movie_id=row["movie_id"],
        title=row["title"],
        language=row["language"],
        genres=[genre["name"] for genre in genres],
        release_year=row["release_year"],
        runtime_minutes=row["runtime_minutes"],
        overview=row["overview"],
        rating=row["rating"],
        source_url=row["source_url"],
    )


def _run_query(
    conditions: list[str],
    parameters: list[Any],
    limit: int,
    database_name: str | None,
    catalog_path: Path | str | None,
) -> MovieResults:
    ensure_database_initialized(database_name, catalog_path)
    where = " AND ".join(conditions) if conditions else "1 = 1"
    with connect(database_name) as connection:
        count_cursor = execute(
            connection,
            f"SELECT COUNT(*) AS count FROM movies AS m WHERE {where}",
            parameters,
        )
        count = count_cursor.fetchone()["count"]
        count_cursor.close()

        rows_cursor = execute(
            connection,
            f"""
            SELECT m.*
            FROM movies AS m
            WHERE {where}
            ORDER BY LOWER(m.title), m.movie_id
            LIMIT %s
            """,
            [*parameters, limit],
        )
        rows = rows_cursor.fetchall()
        rows_cursor.close()
        items = [_movie_from_row(connection, row) for row in rows]
    return MovieResults(count=int(count), limit=limit, items=items)


def search_movies(
    query: str | None = None,
    language: str | None = None,
    genre: str | None = None,
    release_year: int | None = None,
    limit: int = 20,
    *,
    database_name: str | None = None,
    catalog_path: Path | str | None = None,
) -> MovieResults:
    """Search titles and overviews, optionally narrowing by catalog metadata."""
    request = MovieSearchRequest(
        query=query,
        language=language,
        genre=genre,
        release_year=release_year,
        limit=limit,
    )
    conditions: list[str] = []
    parameters: list[Any] = []
    if request.query:
        escaped = (
            request.query.casefold()
            .replace("!", "!!")
            .replace("%", "!%")
            .replace("_", "!_")
        )
        conditions.append(
            "(LOWER(m.title) LIKE LOWER(%s) ESCAPE '!' "
            "OR LOWER(m.overview) LIKE LOWER(%s) ESCAPE '!')"
        )
        parameters.extend((f"%{escaped}%", f"%{escaped}%"))
    if request.language:
        conditions.append("LOWER(m.language) = LOWER(%s)")
        parameters.append(request.language)
    if request.genre:
        conditions.append(
            """
            EXISTS (
                SELECT 1 FROM movie_genres AS mg
                JOIN genres AS g ON g.genre_id = mg.genre_id
                WHERE mg.movie_id = m.movie_id AND LOWER(g.name) = LOWER(%s)
            )
            """
        )
        parameters.append(request.genre)
    if request.release_year is not None:
        conditions.append("m.release_year = %s")
        parameters.append(request.release_year)
    return _run_query(
        conditions, parameters, request.limit, database_name, catalog_path
    )


def filter_movies(
    language: str | None = None,
    genre: str | None = None,
    min_year: int | None = None,
    max_year: int | None = None,
    min_runtime: int | None = None,
    max_runtime: int | None = None,
    min_rating: float | None = None,
    limit: int = 20,
    *,
    database_name: str | None = None,
    catalog_path: Path | str | None = None,
) -> MovieResults:
    """Apply validated, conjunctive constraints to known movie metadata."""
    request = MovieFilterRequest(
        language=language,
        genre=genre,
        min_year=min_year,
        max_year=max_year,
        min_runtime=min_runtime,
        max_runtime=max_runtime,
        min_rating=min_rating,
        limit=limit,
    )
    conditions: list[str] = []
    parameters: list[Any] = []
    if request.language:
        conditions.append("LOWER(m.language) = LOWER(%s)")
        parameters.append(request.language)
    if request.genre:
        conditions.append(
            """
            EXISTS (
                SELECT 1 FROM movie_genres AS mg
                JOIN genres AS g ON g.genre_id = mg.genre_id
                WHERE mg.movie_id = m.movie_id AND LOWER(g.name) = LOWER(%s)
            )
            """
        )
        parameters.append(request.genre)
    if request.min_year is not None:
        conditions.append("m.release_year >= %s")
        parameters.append(request.min_year)
    if request.max_year is not None:
        conditions.append("m.release_year <= %s")
        parameters.append(request.max_year)
    if request.min_runtime is not None:
        conditions.extend(("m.runtime_minutes IS NOT NULL", "m.runtime_minutes >= %s"))
        parameters.append(request.min_runtime)
    if request.max_runtime is not None:
        conditions.extend(("m.runtime_minutes IS NOT NULL", "m.runtime_minutes <= %s"))
        parameters.append(request.max_runtime)
    if request.min_rating is not None:
        conditions.extend(("m.rating IS NOT NULL", "m.rating >= %s"))
        parameters.append(request.min_rating)
    return _run_query(
        conditions, parameters, request.limit, database_name, catalog_path
    )


def get_movie_details(
    movie_id: str,
    *,
    database_name: str | None = None,
    catalog_path: Path | str | None = None,
) -> Movie | None:
    """Return a movie by exact stable ID, or None when that ID is unknown."""
    request = MovieIdRequest(movie_id=movie_id)
    ensure_database_initialized(database_name, catalog_path)
    with connect(database_name) as connection:
        cursor = execute(
            connection,
            "SELECT * FROM movies WHERE movie_id = %s",
            (request.movie_id,),
        )
        row = cursor.fetchone()
        cursor.close()
        return _movie_from_row(connection, row) if row is not None else None


def get_movie_stats(
    *,
    database_name: str | None = None,
    catalog_path: Path | str | None = None,
) -> MovieStats:
    """Calculate catalog statistics from stored records."""
    ensure_database_initialized(database_name, catalog_path)
    with connect(database_name) as connection:
        cursor = execute(
            connection,
            """
            SELECT
                COUNT(*) AS total_movies,
                COUNT(DISTINCT LOWER(language)) AS distinct_languages,
                SUM(CASE WHEN runtime_minutes IS NULL THEN 1 ELSE 0 END) AS missing_runtime,
                SUM(CASE WHEN rating IS NULL THEN 1 ELSE 0 END) AS missing_rating
            FROM movies
            """,
        )
        row = cursor.fetchone()
        cursor.close()
        genre_cursor = execute(
            connection,
            """
            SELECT COUNT(DISTINCT LOWER(g.name)) AS distinct_genres
            FROM genres AS g
            JOIN movie_genres AS mg ON mg.genre_id = g.genre_id
            """,
        )
        distinct_genres = genre_cursor.fetchone()["distinct_genres"]
        genre_cursor.close()
    return MovieStats(
        total_movies=row["total_movies"],
        distinct_languages=row["distinct_languages"],
        distinct_genres=distinct_genres,
        missing_runtime=row["missing_runtime"],
        missing_rating=row["missing_rating"],
    )
