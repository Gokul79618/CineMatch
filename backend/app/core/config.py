"""Validated environment-backed application settings."""

import math
import os
from pathlib import Path
from urllib.parse import urlsplit

from dotenv import load_dotenv

load_dotenv(Path(__file__).resolve().parents[2] / ".env")


def _env_int(name: str, default: int, minimum: int, maximum: int) -> int:
    raw_value = os.getenv(name, str(default))
    try:
        value = int(raw_value)
    except ValueError:
        raise ValueError(f"{name} must be an integer.") from None
    if not minimum <= value <= maximum:
        raise ValueError(f"{name} must be between {minimum} and {maximum}.")
    return value


def _env_float(name: str, default: float, minimum: float, maximum: float) -> float:
    raw_value = os.getenv(name, str(default))
    try:
        value = float(raw_value)
    except ValueError:
        raise ValueError(f"{name} must be a number.") from None
    if not math.isfinite(value) or not minimum <= value <= maximum:
        raise ValueError(f"{name} must be between {minimum} and {maximum}.")
    return value


def _env_bool(name: str, default: bool) -> bool:
    raw_value = os.getenv(name)
    if raw_value is None:
        return default
    normalized = raw_value.strip().casefold()
    if normalized in {"true", "1", "yes"}:
        return True
    if normalized in {"false", "0", "no"}:
        return False
    raise ValueError(f"{name} must be true or false.")


def _env_origins(name: str, defaults: tuple[str, ...]) -> list[str]:
    raw_value = os.getenv(name)
    if raw_value is None:
        return list(defaults)
    return [origin.strip().rstrip("/") for origin in raw_value.split(",") if origin.strip()]


class Settings:
    """Environment-backed settings with explicit production safeguards."""

    app_name: str = os.getenv("APP_NAME", "CineMatch AI").strip()
    app_version: str = os.getenv("APP_VERSION", "0.1.0").strip()
    api_version: str = os.getenv("API_VERSION", "v1").strip()
    app_env: str = os.getenv("APP_ENV", "development").strip().casefold()
    backend_dir: Path = Path(__file__).resolve().parents[2]
    mysql_host: str = os.getenv("MYSQL_HOST", "127.0.0.1").strip()
    mysql_port: int = _env_int("MYSQL_PORT", 3306, 1, 65535)
    mysql_user: str = os.getenv("MYSQL_USER", "").strip()
    mysql_password: str = os.getenv("MYSQL_PASSWORD", "")
    mysql_database: str = os.getenv("MYSQL_DATABASE", "cinematch_db").strip()
    mysql_test_database: str = os.getenv(
        "MYSQL_TEST_DATABASE", "cinematch_test_db"
    ).strip()
    mysql_connect_timeout_seconds: int = _env_int(
        "MYSQL_CONNECT_TIMEOUT_SECONDS", 10, 1, 30
    )
    mysql_ssl_ca: str = os.getenv("MYSQL_SSL_CA", "").strip()
    mysql_ssl_verify_cert: bool = _env_bool("MYSQL_SSL_VERIFY_CERT", False)
    catalog_path: Path = Path(
        os.getenv(
            "MOVIES_CATALOG_PATH",
            str(Path(__file__).resolve().parents[2] / "data" / "movies.json"),
        )
    )
    rag_documents_path: Path = Path(
        os.getenv(
            "RAG_DOCUMENTS_PATH",
            str(Path(__file__).resolve().parents[2] / "data" / "rag_documents.json"),
        )
    )
    rag_index_path: Path = Path(
        os.getenv(
            "RAG_INDEX_PATH",
            str(Path(__file__).resolve().parents[2] / "data" / "rag_index.json"),
        )
    )
    rag_embedding_model: str = os.getenv(
        "RAG_EMBEDDING_MODEL",
        "sentence-transformers/all-MiniLM-L6-v2",
    ).strip()
    rag_embedding_revision: str = os.getenv("RAG_EMBEDDING_REVISION", "main").strip()
    rag_chunk_size: int = _env_int("RAG_CHUNK_SIZE", 800, 100, 10000)
    rag_chunk_overlap: int = _env_int("RAG_CHUNK_OVERLAP", 100, 0, 5000)
    rag_default_top_k: int = _env_int("RAG_DEFAULT_TOP_K", 3, 1, 5)
    rag_minimum_similarity: float = _env_float(
        "RAG_MINIMUM_SIMILARITY", 0.30, -1.0, 1.0
    )
    llm_provider: str = os.getenv("LLM_PROVIDER", "mock").strip().casefold()
    openai_api_key: str = os.getenv("OPENAI_API_KEY", "")
    openai_model: str = os.getenv("OPENAI_MODEL", "gpt-4o-mini").strip()
    openai_base_url: str = os.getenv(
        "OPENAI_BASE_URL", "https://api.openai.com/v1"
    ).strip().rstrip("/")
    openai_timeout_seconds: float = _env_float(
        "OPENAI_TIMEOUT_SECONDS", 20, 0.1, 30
    )
    openai_max_retries: int = _env_int("OPENAI_MAX_RETRIES", 1, 0, 2)
    frontend_origins: list[str] = _env_origins(
        "FRONTEND_ORIGINS",
        ("http://localhost:5173", "http://127.0.0.1:5173"),
    )
    auto_initialize_database: bool = _env_bool(
        "APP_AUTO_INIT_DB", os.getenv("APP_ENV", "development").casefold() != "production"
    )
    max_request_bytes: int = _env_int(
        "MAX_REQUEST_BYTES", 1_048_576, 1_024, 10_485_760
    )
    agent_requests_per_minute: int = _env_int(
        "AGENT_REQUESTS_PER_MINUTE", 20, 1, 1000
    )

    def validate_startup(self) -> None:
        """Reject unsafe or incomplete production configuration without echoing values."""
        if self.app_env not in {"development", "test", "production"}:
            raise ValueError("APP_ENV must be development, test, or production.")
        if not self.app_name or not self.app_version or not self.api_version:
            raise ValueError("APP_NAME, APP_VERSION, and API_VERSION must not be blank.")
        if not self.mysql_host or not self.mysql_user or not self.mysql_database:
            raise ValueError("MYSQL_HOST, MYSQL_USER, and MYSQL_DATABASE are required.")
        if not self.mysql_test_database or self.mysql_test_database == self.mysql_database:
            raise ValueError("MYSQL_TEST_DATABASE must differ from MYSQL_DATABASE.")
        if self.rag_chunk_overlap >= self.rag_chunk_size:
            raise ValueError("RAG_CHUNK_OVERLAP must be smaller than RAG_CHUNK_SIZE.")
        if not self.rag_embedding_model or not self.rag_embedding_revision:
            raise ValueError(
                "RAG_EMBEDDING_MODEL and RAG_EMBEDDING_REVISION must not be blank."
            )
        if self.llm_provider not in {"mock", "openai"}:
            raise ValueError("LLM_PROVIDER must be either mock or openai.")
        if not self.openai_model:
            raise ValueError("OPENAI_MODEL must not be blank.")
        parsed_provider_url = urlsplit(self.openai_base_url)
        if (
            parsed_provider_url.scheme != "https"
            or not parsed_provider_url.netloc
            or parsed_provider_url.username
            or parsed_provider_url.password
            or parsed_provider_url.query
            or parsed_provider_url.fragment
        ):
            raise ValueError("OPENAI_BASE_URL must be an HTTPS origin and path without credentials.")
        try:
            parsed_provider_url.port
        except ValueError:
            raise ValueError("OPENAI_BASE_URL contains an invalid port.") from None
        for origin in self.frontend_origins:
            parsed_origin = urlsplit(origin)
            if (
                parsed_origin.scheme not in {"http", "https"}
                or not parsed_origin.netloc
                or parsed_origin.path
                or parsed_origin.query
                or parsed_origin.fragment
                or parsed_origin.username
                or parsed_origin.password
            ):
                raise ValueError("FRONTEND_ORIGINS must contain comma-separated origins only.")
            try:
                parsed_origin.port
            except ValueError:
                raise ValueError("FRONTEND_ORIGINS contains an invalid port.") from None

        if self.app_env == "production":
            if self.mysql_database != "cinematch_db":
                raise ValueError("Production MYSQL_DATABASE must remain cinematch_db.")
            if self.mysql_test_database != "cinematch_test_db":
                raise ValueError(
                    "Production MYSQL_TEST_DATABASE must remain cinematch_test_db."
                )
            if not self.mysql_password.strip():
                raise ValueError("MYSQL_PASSWORD is required in production.")
            if not self.mysql_ssl_verify_cert:
                raise ValueError("MYSQL_SSL_VERIFY_CERT must be true in production.")
            if self.auto_initialize_database:
                raise ValueError("APP_AUTO_INIT_DB must be false in production.")
            if not self.frontend_origins or any(
                urlsplit(origin).scheme != "https" for origin in self.frontend_origins
            ):
                raise ValueError("Production FRONTEND_ORIGINS must use HTTPS.")
            if self.llm_provider == "openai" and not self.openai_api_key.strip():
                raise ValueError(
                    "OPENAI_API_KEY is required when LLM_PROVIDER=openai in production."
                )

    def resolve_database_name(self) -> str:
        """Return the configured MySQL schema name."""
        return self.mysql_database

    def resolve_catalog_path(self) -> Path:
        """Resolve a relative catalog path from the backend directory."""
        if self.catalog_path.is_absolute():
            return self.catalog_path
        return self.backend_dir / self.catalog_path

    def resolve_rag_documents_path(self) -> Path:
        """Resolve the optional locally maintained RAG document file."""
        if self.rag_documents_path.is_absolute():
            return self.rag_documents_path
        return self.backend_dir / self.rag_documents_path

    def resolve_rag_index_path(self) -> Path:
        """Resolve the generated local vector index path."""
        if self.rag_index_path.is_absolute():
            return self.rag_index_path
        return self.backend_dir / self.rag_index_path


settings = Settings()
