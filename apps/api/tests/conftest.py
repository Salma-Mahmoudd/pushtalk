from collections.abc import AsyncIterator, Callable
from http import HTTPStatus

import pytest
from fastapi import FastAPI, WebSocket
from httpx import ASGITransport, AsyncClient
from pydantic import BaseModel

from pushtalk.core.config import Settings
from pushtalk.core.errors import AppError
from pushtalk.main import create_app

ALLOWED_ORIGIN = "http://app.test"


class Item(BaseModel):
    name: str
    size: int


class Teapot(AppError):
    status_code = HTTPStatus.IM_A_TEAPOT
    code = "teapot"
    message = "Short and stout."


@pytest.fixture
def allowed_origin() -> str:
    return ALLOWED_ORIGIN


@pytest.fixture
def settings(allowed_origin: str) -> Settings:
    return Settings(allowed_origins=[allowed_origin])


def _build_app(settings: Settings) -> FastAPI:
    """The real app plus test-only routes that trigger each error path."""
    application = create_app(settings)

    @application.post("/api/test/items")
    async def create_item(item: Item) -> Item:
        return item

    @application.get("/api/test/teapot")
    async def teapot() -> None:
        raise Teapot(headers={"Retry-After": "5"})

    @application.get("/api/test/crash")
    async def crash() -> None:
        raise RuntimeError("database password is hunter2")

    @application.websocket("/ws/test")
    async def echo(websocket: WebSocket) -> None:
        await websocket.accept()
        await websocket.send_text("hello")
        await websocket.close()

    return application


@pytest.fixture
def app_factory(settings: Settings) -> Callable[[], FastAPI]:
    """Builds the test app on demand, e.g. after pytest starts capturing stdout."""
    return lambda: _build_app(settings)


@pytest.fixture
def app(app_factory: Callable[[], FastAPI]) -> FastAPI:
    return app_factory()


@pytest.fixture
async def client(app: FastAPI) -> AsyncIterator[AsyncClient]:
    # raise_app_exceptions=False: return the 500 response instead of re-raising the crash.
    transport = ASGITransport(app=app, raise_app_exceptions=False)
    async with AsyncClient(transport=transport, base_url="http://test") as http_client:
        yield http_client
