import asyncio
import contextlib
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

import structlog
from fastapi import FastAPI
from redis.asyncio import Redis
from sqlalchemy.ext.asyncio import async_sessionmaker

from pushtalk import health
from pushtalk.auth.router import register_auth_error_handlers
from pushtalk.auth.router import router as auth_router
from pushtalk.channels.presence import PresenceService
from pushtalk.channels.router import router as channels_router
from pushtalk.core.config import DEV_JWT_SECRET, Settings, get_settings
from pushtalk.core.errors import register_error_handlers
from pushtalk.core.logging import configure_logging
from pushtalk.core.middleware import OriginCheckMiddleware, RequestContextMiddleware
from pushtalk.db.session import create_engine
from pushtalk.infra.rate_limit import RateLimiter
from pushtalk.infra.redis import create_redis
from pushtalk.realtime.manager import ConnectionManager
from pushtalk.realtime.router import router as realtime_router
from pushtalk.realtime.sweeper import sweep_presence_forever

log = structlog.get_logger(__name__)


def attach_redis(app: FastAPI, redis: Redis) -> None:
    """Everything built on Redis; tests call this with an in-memory Redis."""
    app.state.redis = redis
    app.state.rate_limiter = RateLimiter(redis)
    app.state.presence = PresenceService(redis)
    app.state.connections = ConnectionManager(redis)


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or get_settings()
    configure_logging(settings.log_level, settings.log_format)
    if settings.jwt_secret.get_secret_value() == DEV_JWT_SECRET:
        log.warning("security.dev_jwt_secret", hint="set JWT_SECRET outside local development")

    # Both connect lazily on first use; the lifespan closes them on shutdown.
    engine = create_engine(str(settings.database_url))
    redis = create_redis(str(settings.redis_url))

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        sweeper = asyncio.create_task(sweep_presence_forever(redis, app.state.presence))
        yield
        sweeper.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await sweeper
        await app.state.connections.close()
        await redis.aclose()
        await engine.dispose()

    application = FastAPI(
        title="PushTalk API",
        docs_url="/api/docs",
        openapi_url="/api/openapi.json",
        lifespan=lifespan,
    )
    application.state.settings = settings
    # expire_on_commit=False: objects stay readable after commit, e.g. to build a response.
    application.state.sessionmaker = async_sessionmaker(engine, expire_on_commit=False)
    attach_redis(application, redis)
    application.state.health_checks = health.dependency_checks(engine, redis)

    register_error_handlers(application)
    register_auth_error_handlers(application)
    # The last middleware added runs first: the request id exists before the origin check.
    application.add_middleware(OriginCheckMiddleware, allowed_origins=settings.allowed_origins)
    application.add_middleware(RequestContextMiddleware)
    application.include_router(health.router)
    application.include_router(auth_router)
    application.include_router(channels_router)
    application.include_router(realtime_router)
    return application


app = create_app()
