"""API contract tests for the movie catalog."""


def test_movie_search_returns_catalog_records(movie_api_client) -> None:
    response = movie_api_client.get("/api/movies", params={"query": "alpha"})
    assert response.status_code == 200
    payload = response.json()
    assert payload["count"] == 1
    assert payload["items"][0]["movie_id"] == "alpha-2001"


def test_movie_filter_returns_validation_error(movie_api_client) -> None:
    response = movie_api_client.post(
        "/api/movies/filter", json={"min_year": 2010, "max_year": 2000}
    )
    assert response.status_code == 422


def test_movie_filter_returns_constrained_records(movie_api_client) -> None:
    response = movie_api_client.post(
        "/api/movies/filter",
        json={"language": "Tamil", "genre": "Action", "min_year": 2005},
    )
    assert response.status_code == 200
    assert [item["movie_id"] for item in response.json()["items"]] == [
        "gamma-2010"
    ]


def test_movie_details_and_unknown_id_status(movie_api_client) -> None:
    found = movie_api_client.get("/api/movies/alpha-2001")
    missing = movie_api_client.get("/api/movies/no-such-id")
    assert found.status_code == 200
    assert found.json()["title"] == "Alpha"
    assert missing.status_code == 404
    assert missing.json()["detail"] == "Movie not found."


def test_movie_stats_api_returns_real_database_counts(movie_api_client) -> None:
    response = movie_api_client.get("/api/movies/stats")
    assert response.status_code == 200
    assert response.json() == {
        "total_movies": 3,
        "distinct_languages": 2,
        "distinct_genres": 2,
        "missing_runtime": 1,
        "missing_rating": 1,
    }


def test_movie_routes_preserve_phase_one_health(movie_api_client) -> None:
    assert movie_api_client.get("/api/health").status_code == 200
    assert movie_api_client.get("/api/system/info").status_code == 200
