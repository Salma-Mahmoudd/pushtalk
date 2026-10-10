"""Real PostgreSQL and Redis, as started by docker-compose.dev.yml (see apps/api/README.md)."""

import socket
from urllib.parse import urlsplit

import pytest
from httpx import ASGITransport, AsyncClient

from pushtalk.core.config import Settings
from pushtalk.main import create_app

pytestmark = pytest.mark.integration


def _reachable(url: str) -> bool:
    parts = urlsplit(url)
    try:
        with socket.create_connection((parts.hostname or "localhost", parts.port or 0), timeout=1):
            return True
    except OSError:
        return False


@pytest.fixture
def settings() -> Settings:
    settings = Settings()
    for name, url in (("PostgreSQL", settings.database_url), ("Redis", settings.redis_url)):
        if not _reachable(str(url)):
            pytest.skip(f"{name} is not running at {url}; start it with docker compose")
    return settings


async def test_health_reaches_real_database_and_redis(settings: Settings) -> None:
    app = create_app(settings)
    async with (
        app.router.lifespan_context(app),
        AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client,
    ):
        response = await client.get("/api/health")

    assert response.status_code == 200
    assert response.json()["checks"] == {"database": "ok", "redis": "ok"}
