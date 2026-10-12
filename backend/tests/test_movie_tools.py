"""Tests for deterministic movie tools using an isolated MySQL test schema."""

from pathlib import Path

import pytest
from pydantic import ValidationError

from app.database.connection import connect
from app.database.init_db import initialize_database, load_catalog
from app.schemas.movies import MovieFilterRequest, MovieSearchRequest
from app.tools.movie_tools import (
    filter_movies,
    get_movie_details,
    get_movie_stats,
    search_movies,
)


def test_database_initialization_is_repeatable_and_non_destructive(
    temporary_database_path: str, sample_catalog_path: Path
) -> None:
    assert initialize_database(temporary_database_path, sample_catalog_path) == 3
    assert initialize_database(temporary_database_path, sample_catalog_path) == 3

    with connect(temporary_database_path) as connection:
        cursor = connection.cursor()
        cursor.execute(
            """
            INSERT INTO movies
                (movie_id, title, language, release_year, runtime_minutes,
                 overview, rating, source_url)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
            """,
            ("local-only", "Local only", "Tamil", 2020, None, "", None, "https://example.test/local"),
        )
        cursor.close()

    assert initialize_database(temporary_database_path, sample_catalog_path) == 4
    with connect(temporary_database_path) as connection:
        cursor = connection.cursor()
        cursor.execute("SELECT COUNT(*) FROM movies")
        assert cursor.fetchone()[0] == 4
        cursor.close()


def test_seed_database_contains_all_thirteen_records_and_metadata(
    temporary_database_path: str,
) -> None:
    source_records = load_catalog()
    assert len(source_records) == 13
    with connect(temporary_database_path) as connection:
        cursor = connection.cursor()
        try:
            cursor.execute("DELETE FROM movie_genres")
            cursor.execute("DELETE FROM movies")
            cursor.execute("DELETE FROM genres")
        finally:
            cursor.close()
    assert initialize_database(temporary_database_path) == 13

    for source in source_records:
        movie = get_movie_details(
            source.movie_id, database_name=temporary_database_path
        )
        assert movie is not None
        actual = movie.model_dump()
        expected = source.model_dump()
        assert set(actual.pop("genres")) == set(expected.pop("genres"))
        assert actual == expected


def test_search_matches_title_case_insensitively(
    temporary_database_path: str, sample_catalog_path: Path
) -> None:
    result = search_movies(
        "  aLpHa ",
        database_name=temporary_database_path,
        catalog_path=sample_catalog_path,
    )
    assert result.count == 1
    assert result.items[0].movie_id == "alpha-2001"


def test_search_matches_overview(
    temporary_database_path: str, sample_catalog_path: Path
) -> None:
    result = search_movies(
        "hidden truth",
        database_name=temporary_database_path,
        catalog_path=sample_catalog_path,
    )
    assert [movie.movie_id for movie in result.items] == ["gamma-2010"]


def test_search_applies_language_genre_and_year_together(
    temporary_database_path: str, sample_catalog_path: Path
) -> None:
    result = search_movies(
        language=" tamil ",
        genre="ACTION",
        release_year=2010,
        database_name=temporary_database_path,
        catalog_path=sample_catalog_path,
    )
    assert [movie.movie_id for movie in result.items] == ["gamma-2010"]


def test_search_empty_results_and_result_limit(
    temporary_database_path: str, sample_catalog_path: Path
) -> None:
    missing = search_movies(
        "no such movie",
        database_name=temporary_database_path,
        catalog_path=sample_catalog_path,
    )
    limited = search_movies(
        limit=1,
        database_name=temporary_database_path,
        catalog_path=sample_catalog_path,
    )
    assert missing.items == []
    assert missing.count == 0
    assert limited.count == 3
    assert len(limited.items) == 1


def test_filter_applies_all_constraints_conjunctively(
    temporary_database_path: str, sample_catalog_path: Path
) -> None:
    result = filter_movies(
        language="Tamil",
        genre="Action",
        min_year=2000,
        max_year=2005,
        min_runtime=100,
        max_runtime=130,
        min_rating=8,
        database_name=temporary_database_path,
        catalog_path=sample_catalog_path,
    )
    assert [movie.movie_id for movie in result.items] == ["alpha-2001"]


def test_runtime_and_rating_filters_exclude_missing_metadata(
    temporary_database_path: str, sample_catalog_path: Path
) -> None:
    by_runtime = filter_movies(
        max_runtime=600,
        database_name=temporary_database_path,
        catalog_path=sample_catalog_path,
    )
    by_rating = filter_movies(
        min_rating=0,
        database_name=temporary_database_path,
        catalog_path=sample_catalog_path,
    )
    assert {movie.movie_id for movie in by_runtime.items} == {
        "alpha-2001",
        "gamma-2010",
    }
    assert {movie.movie_id for movie in by_rating.items} == {
        "alpha-2001",
        "gamma-2010",
    }


def test_filter_result_limit_is_bounded(
    temporary_database_path: str, sample_catalog_path: Path
) -> None:
    result = filter_movies(
        limit=2,
        database_name=temporary_database_path,
        catalog_path=sample_catalog_path,
    )
    assert result.count == 3
    assert len(result.items) == 2


@pytest.mark.parametrize(
    "payload",
    [
        {"limit": 0},
        {"limit": 51},
        {"min_year": 2010, "max_year": 2000},
        {"min_runtime": 200, "max_runtime": 100},
        {"min_rating": 11},
    ],
)
def test_invalid_filter_constraints_are_rejected(payload: dict[str, object]) -> None:
    with pytest.raises(ValidationError):
        MovieFilterRequest.model_validate(payload)


def test_search_limit_is_validated() -> None:
    with pytest.raises(ValidationError):
        MovieSearchRequest(limit=1000)


def test_movie_detail_is_exact_and_unknown_ids_return_none(
    temporary_database_path: str, sample_catalog_path: Path
) -> None:
    movie = get_movie_details(
        "alpha-2001",
        database_name=temporary_database_path,
        catalog_path=sample_catalog_path,
    )
    unknown = get_movie_details(
        "not-a-real-id",
        database_name=temporary_database_path,
        catalog_path=sample_catalog_path,
    )
    assert movie is not None and movie.title == "Alpha"
    assert movie.source_url == "https://example.test/alpha"
    assert unknown is None


def test_stats_are_calculated_from_actual_records(
    temporary_database_path: str, sample_catalog_path: Path
) -> None:
    stats = get_movie_stats(
        database_name=temporary_database_path,
        catalog_path=sample_catalog_path,
    )
    assert stats.model_dump() == {
        "total_movies": 3,
        "distinct_languages": 2,
        "distinct_genres": 2,
        "missing_runtime": 1,
        "missing_rating": 1,
    }
