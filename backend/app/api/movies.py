"""Movie catalog HTTP routes."""

from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, Query

from app.core.config import settings
from app.schemas.movies import (
    Movie,
    MovieFilterRequest,
    MovieResults,
    MovieStats,
)
from app.tools.movie_tools import (
    filter_movies,
    get_movie_details,
    get_movie_stats,
    search_movies,
)

router = APIRouter()


def get_database_name() -> str:
    return settings.resolve_database_name()


def get_catalog_path() -> Path:
    return settings.resolve_catalog_path()


@router.get("", response_model=MovieResults)
def search_movie_catalog(
    query: str | None = Query(default=None, max_length=200),
    language: str | None = Query(default=None, max_length=50),
    genre: str | None = Query(default=None, max_length=80),
    release_year: int | None = Query(default=None, ge=1888, le=2100),
    limit: int = Query(default=20, ge=1, le=50),
    database_name: str = Depends(get_database_name),
    catalog_path: Path = Depends(get_catalog_path),
) -> MovieResults:
    return search_movies(
        query,
        language,
        genre,
        release_year,
        limit,
        database_name=database_name,
        catalog_path=catalog_path,
    )


@router.post("/filter", response_model=MovieResults)
def filter_movie_catalog(
    request: MovieFilterRequest,
    database_name: str = Depends(get_database_name),
    catalog_path: Path = Depends(get_catalog_path),
) -> MovieResults:
    return filter_movies(
        **request.model_dump(),
        database_name=database_name,
        catalog_path=catalog_path,
    )


@router.get("/stats", response_model=MovieStats)
def read_movie_stats(
    database_name: str = Depends(get_database_name),
    catalog_path: Path = Depends(get_catalog_path),
) -> MovieStats:
    return get_movie_stats(database_name=database_name, catalog_path=catalog_path)


@router.get("/{movie_id}", response_model=Movie)
def read_movie_details(
    movie_id: str,
    database_name: str = Depends(get_database_name),
    catalog_path: Path = Depends(get_catalog_path),
) -> Movie:
    movie = get_movie_details(
        movie_id, database_name=database_name, catalog_path=catalog_path
    )
    if movie is None:
        raise HTTPException(status_code=404, detail="Movie not found.")
    return movie
