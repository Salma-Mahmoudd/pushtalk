import asyncio

import pytest
from fastapi import FastAPI
from httpx import AsyncClient

from pushtalk import health


async def _ok() -> None:
    return None


async def _down() -> None:
    raise ConnectionRefusedError


async def _hangs() -> None:
    await asyncio.sleep(1)


async def test_all_dependencies_up_returns_ok(client: AsyncClient) -> None:
    response = await client.get("/api/health")

    assert response.status_code == 200
    assert response.json() == {"status": "ok", "checks": {"database": "ok", "redis": "ok"}}


async def test_dependency_down_returns_503_with_details(client: AsyncClient, app: FastAPI) -> None:
    app.state.health_checks = {"database": _ok, "redis": _down}

    response = await client.get("/api/health")

    assert response.status_code == 503
    body = response.json()
    assert body["error"]["code"] == "service_unavailable"
    assert body["error"]["details"] == [{"field": "redis", "message": "unavailable"}]


async def test_hanging_dependency_times_out(
    client: AsyncClient, app: FastAPI, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(health, "CHECK_TIMEOUT_S", 0.05)
    app.state.health_checks = {"database": _hangs, "redis": _ok}

    response = await client.get("/api/health")

    assert response.status_code == 503
    assert response.json()["error"]["details"] == [{"field": "database", "message": "unavailable"}]
