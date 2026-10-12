"""Production configuration and bounded HTTP middleware regression tests."""

import asyncio
from copy import copy

from fastapi import FastAPI, Request
from fastapi.testclient import TestClient

import mysql.connector
import pytest

from app.core.config import Settings, _env_int, settings
from app.database import connection as db_connection
from app.core.middleware import (
    AgentRateLimitMiddleware,
    RequestSizeLimitMiddleware,
)
from app.main import app as main_app
from app.main import internal_server_error, lifespan


def production_settings() -> Settings:
    configured = copy(settings)
    configured.app_env = "production"
    configured.mysql_user = "service-account"
    configured.mysql_password = "test-only-password"
    configured.mysql_database = "cinematch_db"
    configured.mysql_test_database = "cinematch_test_db"
    configured.mysql_ssl_verify_cert = True
    configured.auto_initialize_database = False
    configured.frontend_origins = ["https://app.example.com"]
    configured.llm_provider = "mock"
    configured.openai_api_key = ""
    return configured


def test_valid_production_configuration_passes_startup_validation() -> None:
    production_settings().validate_startup()


def test_production_configuration_requires_tls_and_exact_origins() -> None:
    configured = production_settings()
    configured.mysql_ssl_verify_cert = False
    with pytest.raises(ValueError, match="MYSQL_SSL_VERIFY_CERT"):
        configured.validate_startup()

    configured = production_settings()
    configured.frontend_origins = ["https://app.example.com/path"]
    with pytest.raises(ValueError, match="FRONTEND_ORIGINS"):
        configured.validate_startup()


def test_production_openai_mode_requires_a_key_without_echoing_it() -> None:
    configured = production_settings()
    configured.llm_provider = "openai"
    configured.openai_api_key = ""

    with pytest.raises(ValueError, match="OPENAI_API_KEY") as error:
        configured.validate_startup()

    assert "test-only-password" not in str(error.value)


def test_production_never_auto_initializes_database() -> None:
    configured = production_settings()
    configured.auto_initialize_database = True

    with pytest.raises(ValueError, match="APP_AUTO_INIT_DB"):
        configured.validate_startup()


def test_read_only_startup_does_not_initialize_database(monkeypatch) -> None:
    verified: list[str] = []

    monkeypatch.setattr(settings, "validate_startup", lambda: None)
    monkeypatch.setattr(settings, "auto_initialize_database", False)
    monkeypatch.setattr(
        "app.main.verify_database_ready",
        lambda database: verified.append(database) or True,
    )
    monkeypatch.setattr(
        "app.main.initialize_database",
        lambda *_: pytest.fail("read-only startup must not initialize schema"),
    )

    async def start_and_stop() -> None:
        async with lifespan(main_app):
            pass

    asyncio.run(start_and_stop())

    assert verified == [settings.mysql_database]


def test_invalid_integer_configuration_error_does_not_echo_value(monkeypatch) -> None:
    monkeypatch.setenv("MYSQL_PORT", "not-a-port-secret")

    with pytest.raises(ValueError, match="MYSQL_PORT") as error:
        _env_int("MYSQL_PORT", 3306, 1, 65535)

    assert "not-a-port-secret" not in str(error.value)


def test_request_body_limit_rejects_oversized_content() -> None:
    app = FastAPI()

    @app.post("/echo")
    async def echo(request: Request) -> dict[str, int]:
        return {"bytes": len(await request.body())}

    client = TestClient(RequestSizeLimitMiddleware(app, max_bytes=64))
    response = client.post("/echo", content=b"x" * 65)

    assert response.status_code == 413
    assert response.json()["detail"]["code"] == "request_too_large"


def test_agent_rate_limit_is_applied_to_agent_run_only() -> None:
    app = FastAPI()

    @app.post("/api/agent/run")
    async def run_agent() -> dict[str, str]:
        return {"status": "accepted"}

    @app.get("/api/health")
    async def health() -> dict[str, str]:
        return {"status": "ok"}

    client = TestClient(AgentRateLimitMiddleware(app, max_requests=1))
    assert client.post("/api/agent/run").status_code == 200
    limited = client.post("/api/agent/run")
    assert limited.status_code == 429
    assert limited.headers["retry-after"]
    assert client.get("/api/health").status_code == 200


def test_mysql_connection_passes_tls_verification_options(monkeypatch) -> None:
    captured: dict[str, object] = {}

    class StubConnection:
        def commit(self) -> None:
            pass

        def rollback(self) -> None:
            pass

        def close(self) -> None:
            pass

    def fake_connect(**kwargs: object) -> StubConnection:
        captured.update(kwargs)
        return StubConnection()

    monkeypatch.setattr(settings, "mysql_user", "test-account")
    monkeypatch.setattr(settings, "mysql_ssl_ca", "test-ca.pem")
    monkeypatch.setattr(settings, "mysql_ssl_verify_cert", True)
    monkeypatch.setattr(db_connection.mysql.connector, "connect", fake_connect)

    with db_connection.connect():
        pass

    assert captured["ssl_ca"] == "test-ca.pem"
    assert captured["ssl_verify_cert"] is True
    assert captured["ssl_verify_identity"] is True


def test_mysql_rollback_failure_does_not_mask_original_error(
    monkeypatch, caplog
) -> None:
    state = {"closed": False}

    class RollbackFailureConnection:
        def commit(self) -> None:
            pass

        def rollback(self) -> None:
            raise mysql.connector.Error("private database diagnostic")

        def close(self) -> None:
            state["closed"] = True

    monkeypatch.setattr(settings, "mysql_user", "test-account")
    monkeypatch.setattr(
        db_connection.mysql.connector,
        "connect",
        lambda **_: RollbackFailureConnection(),
    )

    with pytest.raises(ValueError, match="original failure"):
        with db_connection.connect():
            raise ValueError("original failure")

    assert state["closed"] is True
    assert "private database diagnostic" not in caplog.text


def test_mysql_commit_failure_rolls_back_and_closes(monkeypatch) -> None:
    state = {"rolled_back": False, "closed": False}

    class CommitFailureConnection:
        def commit(self) -> None:
            raise mysql.connector.Error("private commit diagnostic")

        def rollback(self) -> None:
            state["rolled_back"] = True

        def close(self) -> None:
            state["closed"] = True

    monkeypatch.setattr(settings, "mysql_user", "test-account")
    monkeypatch.setattr(
        db_connection.mysql.connector,
        "connect",
        lambda **_: CommitFailureConnection(),
    )

    with pytest.raises(mysql.connector.Error):
        with db_connection.connect():
            pass

    assert state == {"rolled_back": True, "closed": True}


def test_unhandled_exception_response_and_logs_hide_private_message(caplog) -> None:
    app = FastAPI()
    app.add_exception_handler(Exception, internal_server_error)

    @app.get("/failure")
    async def failure() -> None:
        raise RuntimeError("private password should not be exposed")

    response = TestClient(app, raise_server_exceptions=False).get("/failure")

    assert response.status_code == 500
    assert response.json() == {
        "detail": {
            "code": "internal_error",
            "message": "The request could not be completed.",
        }
    }
    assert "private password" not in response.text
    assert "private password" not in caplog.text
