import json
from collections.abc import Callable
from typing import Any

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

# Each test builds its app itself, so the log handler writes to the stdout capsys captures.


def _log_lines(output: str) -> list[dict[str, Any]]:
    return [json.loads(line) for line in output.splitlines() if line.startswith("{")]


async def test_request_is_logged_as_json_with_request_id(
    capsys: pytest.CaptureFixture[str], app_factory: Callable[[], FastAPI]
) -> None:
    transport = ASGITransport(app=app_factory())
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get("/api/health")

    lines = _log_lines(capsys.readouterr().out)
    completed = next(line for line in lines if line["event"] == "request.completed")
    assert completed["request_id"] == response.headers["X-Request-ID"]
    assert completed["method"] == "GET"
    assert completed["path"] == "/api/health"
    assert completed["status"] == 200
    assert completed["level"] == "info"
    assert "timestamp" in completed


async def test_unhandled_error_is_logged_with_traceback(
    capsys: pytest.CaptureFixture[str], app_factory: Callable[[], FastAPI]
) -> None:
    transport = ASGITransport(app=app_factory(), raise_app_exceptions=False)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get("/api/test/crash")

    lines = _log_lines(capsys.readouterr().out)
    failed = next(line for line in lines if line["event"] == "request.failed")
    assert failed["request_id"] == response.headers["X-Request-ID"]
    assert failed["error_type"] == "RuntimeError"
    assert failed["exception"][0]["exc_type"] == "RuntimeError"
