from collections.abc import AsyncIterator, Callable
from http import HTTPStatus

import pytest
from fakeredis import FakeAsyncRedis
from fastapi import FastAPI, WebSocket
from httpx import ASGITransport, AsyncClient
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool

from pushtalk.core.config import Settings
from pushtalk.core.errors import AppError
from pushtalk.main import attach_redis, create_app
from tests.db import prepare_test_database

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
    # The test client talks plain http://test, which never sends Secure cookies.
    return Settings(allowed_origins=[allowed_origin], cookie_secure=False)


async def _passing_check() -> None:
    return None


def _build_app(settings: Settings) -> FastAPI:
    """The real app plus test-only routes that trigger each error path.

    Health checks are replaced with passing fakes, so unit tests never need PostgreSQL or Redis;
    tests/integration/ covers the real connections.
    """
    application = create_app(settings)
    application.state.health_checks = {"database": _passing_check, "redis": _passing_check}

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


@pytest.fixture(scope="session")
def test_database_url() -> str:
    url = prepare_test_database(Settings())
    if url is None:
        pytest.skip("PostgreSQL is not running; start it with `make services`")
    return url


@pytest.fixture
async def db_sessionmaker(
    test_database_url: str,
) -> AsyncIterator[async_sessionmaker[AsyncSession]]:
    """Sessions inside one outer transaction that is rolled back after the test.

    Commits in the code under test only release savepoints, so every test starts clean.
    """
    engine = create_async_engine(test_database_url, poolclass=NullPool)
    async with engine.connect() as connection:
        transaction = await connection.begin()
        yield async_sessionmaker(
            bind=connection, expire_on_commit=False, join_transaction_mode="create_savepoint"
        )
        await transaction.rollback()
    await engine.dispose()


@pytest.fixture
def fake_redis() -> FakeAsyncRedis:
    return FakeAsyncRedis(decode_responses=True)


@pytest.fixture
async def db_app(
    app: FastAPI, db_sessionmaker: async_sessionmaker[AsyncSession], fake_redis: FakeAsyncRedis
) -> AsyncIterator[FastAPI]:
    """The test app on the test database, with an in-memory Redis."""
    app.state.sessionmaker = db_sessionmaker
    attach_redis(app, fake_redis)
    yield app
    await app.state.connections.close()


@pytest.fixture
async def db_client(db_app: FastAPI) -> AsyncIterator[AsyncClient]:
    transport = ASGITransport(app=db_app, raise_app_exceptions=False)
    async with AsyncClient(transport=transport, base_url="http://test") as http_client:
        yield http_client


@pytest.fixture
async def make_client(db_app: FastAPI) -> AsyncIterator[Callable[[], AsyncClient]]:
    """Extra clients on the same app, each with its own cookies (one per user)."""
    clients: list[AsyncClient] = []

    def factory() -> AsyncClient:
        transport = ASGITransport(app=db_app, raise_app_exceptions=False)
        client = AsyncClient(transport=transport, base_url="http://test")
        clients.append(client)
        return client

    yield factory
    for client in clients:
        await client.aclose()
