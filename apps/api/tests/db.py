"""Test database helpers: a migrated `pushtalk_test` database next to the development one."""

import asyncio
import socket
from pathlib import Path

from alembic import command
from alembic.config import Config
from sqlalchemy import make_url, text
from sqlalchemy.ext.asyncio import create_async_engine

from pushtalk.core.config import Settings

TEST_DATABASE = "pushtalk_test"
API_DIR = Path(__file__).resolve().parents[1]


def reachable(host: str | None, port: int | None) -> bool:
    try:
        with socket.create_connection((host or "localhost", port or 5432), timeout=1):
            return True
    except OSError:
        return False


def prepare_test_database(settings: Settings) -> str | None:
    """Creates and migrates the test database; returns its URL, or None if PostgreSQL is down."""
    server_url = make_url(str(settings.database_url))
    if not reachable(server_url.host, server_url.port):
        return None
    test_url = server_url.set(database=TEST_DATABASE).render_as_string(hide_password=False)

    async def create_if_missing() -> None:
        engine = create_async_engine(server_url, isolation_level="AUTOCOMMIT")
        async with engine.connect() as connection:
            exists = await connection.scalar(
                text("SELECT 1 FROM pg_database WHERE datname = :name"), {"name": TEST_DATABASE}
            )
            if not exists:
                await connection.execute(text(f'CREATE DATABASE "{TEST_DATABASE}"'))
        await engine.dispose()

    asyncio.run(create_if_missing())
    config = Config(str(API_DIR / "alembic.ini"))
    config.set_main_option("script_location", str(API_DIR / "migrations"))
    config.set_main_option("sqlalchemy.url", test_url.replace("%", "%%"))
    command.upgrade(config, "head")
    return test_url
