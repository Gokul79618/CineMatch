"""MySQL connection helpers."""

import logging
from contextlib import contextmanager
from collections.abc import Sequence
from typing import Any, Iterator

import mysql.connector
from mysql.connector import MySQLConnection

from app.core.config import settings

logger = logging.getLogger("cinematch.database")


@contextmanager
def connect(database_name: str | None = None) -> Iterator[MySQLConnection]:
    """Open a short-lived connection to the configured MySQL schema."""
    if not settings.mysql_user:
        raise RuntimeError(
            "MYSQL_USER is required. Configure backend/.env before connecting to MySQL."
        )
    connection = mysql.connector.connect(
        host=settings.mysql_host,
        port=settings.mysql_port,
        user=settings.mysql_user,
        password=settings.mysql_password,
        database=database_name or settings.resolve_database_name(),
        charset="utf8mb4",
        collation="utf8mb4_unicode_ci",
        connection_timeout=settings.mysql_connect_timeout_seconds,
        ssl_ca=settings.mysql_ssl_ca or None,
        ssl_verify_cert=settings.mysql_ssl_verify_cert,
        ssl_verify_identity=settings.mysql_ssl_verify_cert,
    )
    operation_error: Exception | None = None
    try:
        yield connection
        connection.commit()
    except Exception as exc:
        operation_error = exc
        try:
            connection.rollback()
        except mysql.connector.Error as rollback_error:
            logger.warning(
                "event=mysql_rollback_failed error_type=%s",
                type(rollback_error).__name__,
            )
        raise
    finally:
        try:
            connection.close()
        except mysql.connector.Error as close_error:
            logger.warning(
                "event=mysql_connection_close_failed error_type=%s",
                type(close_error).__name__,
            )
            if operation_error is None:
                raise


def verify_database_ready(database_name: str | None = None) -> bool:
    """Check connection and the initialized movie schema without writing."""
    expected_database = database_name or settings.resolve_database_name()
    with connect(expected_database) as connection:
        cursor = connection.cursor()
        try:
            cursor.execute("SELECT DATABASE(), 1")
            row = cursor.fetchone()
            if not row or row[0] != expected_database or row[1] != 1:
                return False
        finally:
            cursor.close()
        return has_movie_schema(connection)


def execute(
    connection: MySQLConnection,
    statement: str,
    parameters: Sequence[Any] = (),
) -> Any:
    """Execute a parameterized statement and return a dictionary cursor."""
    cursor = connection.cursor(dictionary=True)
    cursor.execute(statement, parameters)
    return cursor


def has_movie_schema(connection: MySQLConnection) -> bool:
    """Return whether the movies table has been initialized."""
    cursor = execute(
        connection,
        """
        SELECT 1
        FROM information_schema.tables
        WHERE table_schema = DATABASE() AND table_name = %s
        """,
        ("movies",),
    )
    try:
        return cursor.fetchone() is not None
    finally:
        cursor.close()
