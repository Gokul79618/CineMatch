"""Shared temporary movie catalog and database fixtures."""

import json
from pathlib import Path
from typing import Iterator
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient

from app.api.movies import get_catalog_path, get_database_name
from app.api.agent import (
    get_agent_catalog_path,
    get_agent_database_name,
    get_agent_provider,
    get_agent_trace_store,
)
from app.agent.provider import MockProvider
from app.agent.trace import TraceStore
from app.core.config import settings
from app.database.connection import connect
from app.database.init_db import initialize_database
from app.main import app


@pytest.fixture
def sample_catalog_path(tmp_path: Path) -> Path:
    catalog = [
        {
            "movie_id": "alpha-2001",
            "title": "Alpha",
            "language": "Tamil",
            "genres": ["Action"],
            "release_year": 2001,
            "runtime_minutes": 120,
            "overview": "A courageous investigator follows a difficult case.",
            "rating": 8.2,
            "source_url": "https://example.test/alpha",
        },
        {
            "movie_id": "beta-2005",
            "title": "Beta",
            "language": "Hindi",
            "genres": ["Drama"],
            "release_year": 2005,
            "runtime_minutes": None,
            "overview": "A family faces change.",
            "rating": None,
            "source_url": "https://example.test/beta",
        },
        {
            "movie_id": "gamma-2010",
            "title": "Gamma",
            "language": "Tamil",
            "genres": ["Action", "Drama"],
            "release_year": 2010,
            "runtime_minutes": 150,
            "overview": "An investigator uncovers a hidden truth.",
            "rating": 7.5,
            "source_url": "https://example.test/gamma",
        },
    ]
    path = tmp_path / "sample_movies.json"
    path.write_text(json.dumps(catalog), encoding="utf-8")
    return path


@pytest.fixture
def temporary_database_path(sample_catalog_path: Path) -> str:
    """Reset only the separately named MySQL test schema before each test."""
    database_name = settings.mysql_test_database
    if (
        settings.mysql_database != "cinematch_db"
        or database_name != "cinematch_test_db"
        or database_name == settings.mysql_database
    ):
        raise RuntimeError(
            "Tests require MYSQL_DATABASE=cinematch_db and "
            "MYSQL_TEST_DATABASE=cinematch_test_db."
        )
    initialize_database(database_name, sample_catalog_path)
    with connect(database_name) as connection:
        cursor = connection.cursor()
        try:
            cursor.execute("SELECT DATABASE()")
            if cursor.fetchone()[0] != "cinematch_test_db":
                raise RuntimeError(
                    "Refusing test cleanup outside cinematch_test_db."
                )
            cursor.execute("DELETE FROM movie_genres")
            cursor.execute("DELETE FROM movies")
            cursor.execute("DELETE FROM genres")
        finally:
            cursor.close()
    initialize_database(database_name, sample_catalog_path)
    return database_name


@pytest.fixture
def movie_api_client(
    temporary_database_path: str, sample_catalog_path: Path
) -> Iterator[TestClient]:
    app.dependency_overrides[get_database_name] = lambda: temporary_database_path
    app.dependency_overrides[get_catalog_path] = lambda: sample_catalog_path
    try:
        yield TestClient(app)
    finally:
        app.dependency_overrides.clear()


@pytest.fixture
def agent_trace_store() -> TraceStore:
    return TraceStore(max_runs=100)


@pytest.fixture
def agent_api_client(
    temporary_database_path: str,
    sample_catalog_path: Path,
    agent_trace_store: TraceStore,
) -> Iterator[TestClient]:
    app.dependency_overrides[get_agent_database_name] = lambda: temporary_database_path
    app.dependency_overrides[get_agent_catalog_path] = lambda: sample_catalog_path
    app.dependency_overrides[get_agent_provider] = MockProvider
    app.dependency_overrides[get_agent_trace_store] = lambda: agent_trace_store
    try:
        yield TestClient(
            app,
            client=(f"testclient-{uuid4()}", 50000),
        )
    finally:
        app.dependency_overrides.clear()
