"""Tests for public Phase 1 service endpoints."""

from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


def test_root_returns_service_message() -> None:
    response = client.get("/")

    assert response.status_code == 200
    assert response.json() == {"message": "CineMatch AI API is running."}


def test_health_returns_expected_fields() -> None:
    response = client.get("/api/health")

    assert response.status_code == 200
    assert response.json() == {
        "status": "ok",
        "service": "CineMatch AI",
        "version": "0.1.0",
    }


def test_system_info_returns_application_and_capabilities() -> None:
    response = client.get("/api/system/info")

    assert response.status_code == 200
    payload = response.json()
    assert payload["application_name"] == "CineMatch AI"
    assert payload["api_version"] == "v1"
    assert payload["planned_capabilities"] == [
        "Agent harness engineering",
        "Guardrails",
        "LLM tool calling",
        "Retrieval-Augmented Generation (RAG)",
        "Evals and golden-set testing",
    ]


def test_local_vite_origins_are_allowed() -> None:
    for origin in ("http://localhost:5173", "http://127.0.0.1:5173"):
        response = client.get("/api/health", headers={"Origin": origin})

        assert response.status_code == 200
        assert response.headers["access-control-allow-origin"] == origin


def test_health_response_has_security_headers() -> None:
    response = client.get("/api/health")

    assert response.headers["x-content-type-options"] == "nosniff"
    assert response.headers["x-frame-options"] == "DENY"
    assert response.headers["referrer-policy"] == "no-referrer"


def test_disallowed_origin_is_not_granted_cors_access() -> None:
    response = client.get(
        "/api/health",
        headers={"Origin": "https://untrusted.example"},
    )

    assert response.status_code == 200
    assert "access-control-allow-origin" not in response.headers


def test_readiness_returns_only_database_state(monkeypatch) -> None:
    from app.api import routes

    monkeypatch.setattr(routes, "verify_database_ready", lambda _: True)
    ready = client.get("/api/ready")
    assert ready.status_code == 200
    assert ready.json() == {"status": "ready", "database": "available"}

    def unavailable(_: str) -> bool:
        raise RuntimeError("private host and password must not leak")

    monkeypatch.setattr(routes, "verify_database_ready", unavailable)
    not_ready = client.get("/api/ready")
    assert not_ready.status_code == 503
    assert not_ready.json() == {
        "status": "not_ready",
        "database": "unavailable",
    }
    assert "private host" not in not_ready.text
