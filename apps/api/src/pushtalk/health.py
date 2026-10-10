import asyncio
from collections.abc import Awaitable, Callable
from http import HTTPStatus
from typing import Any

import structlog
from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse
from redis.asyncio import Redis
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine

from pushtalk.core.errors import ErrorDetail, error_response, request_id_of

log = structlog.get_logger(__name__)
router = APIRouter(prefix="/api/health", tags=["health"])

HealthCheck = Callable[[], Awaitable[Any]]
CHECK_TIMEOUT_S = 2.0


def dependency_checks(engine: AsyncEngine, redis: Redis) -> dict[str, HealthCheck]:
    """One check per dependency; each must finish without raising within the timeout."""

    async def database() -> None:
        async with engine.connect() as connection:
            await connection.execute(text("SELECT 1"))

    async def cache() -> None:
        await redis.ping()

    return {"database": database, "redis": cache}


async def _run(name: str, check: HealthCheck) -> bool:
    try:
        async with asyncio.timeout(CHECK_TIMEOUT_S):
            await check()
    except Exception as exc:
        log.warning("health.check_failed", check=name, error_type=type(exc).__name__)
        return False
    return True


@router.get("", responses={503: {"description": "A dependency is unavailable"}})
async def health(request: Request) -> JSONResponse:
    checks: dict[str, HealthCheck] = request.app.state.health_checks
    results = await asyncio.gather(*(_run(name, check) for name, check in checks.items()))
    status = dict(zip(checks, results, strict=True))

    if all(results):
        return JSONResponse({"status": "ok", "checks": {name: "ok" for name in status}})
    return error_response(
        HTTPStatus.SERVICE_UNAVAILABLE,
        "service_unavailable",
        "A dependency is unavailable.",
        request_id=request_id_of(request),
        details=[
            ErrorDetail(field=name, message="unavailable") for name, ok in status.items() if not ok
        ],
    )
