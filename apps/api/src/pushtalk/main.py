from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

import structlog
from fastapi import FastAPI
from sqlalchemy.ext.asyncio import async_sessionmaker

from pushtalk import health
from pushtalk.auth.router import register_auth_error_handlers
from pushtalk.auth.router import router as auth_router
from pushtalk.core.config import DEV_JWT_SECRET, Settings, get_settings
from pushtalk.core.errors import register_error_handlers
from pushtalk.core.logging import configure_logging
from pushtalk.core.middleware import OriginCheckMiddleware, RequestContextMiddleware
from pushtalk.db.session import create_engine
from pushtalk.infra.rate_limit import RateLimiter
from pushtalk.infra.redis import create_redis

log = structlog.get_logger(__name__)


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or get_settings()
    configure_logging(settings.log_level, settings.log_format)
    if settings.jwt_secret.get_secret_value() == DEV_JWT_SECRET:
        log.warning("security.dev_jwt_secret", hint="set JWT_SECRET outside local development")

    # Both connect lazily on first use; the lifespan closes them on shutdown.
    engine = create_engine(str(settings.database_url))
    redis = create_redis(str(settings.redis_url))

    @asynccontextmanager
    async def lifespan(_: FastAPI) -> AsyncIterator[None]:
        yield
        await redis.aclose()
        await engine.dispose()

    application = FastAPI(
        title="PushTalk API",
        docs_url="/api/docs",
        openapi_url="/api/openapi.json",
        lifespan=lifespan,
    )
    application.state.settings = settings
    application.state.redis = redis
    # expire_on_commit=False: objects stay readable after commit, e.g. to build a response.
    application.state.sessionmaker = async_sessionmaker(engine, expire_on_commit=False)
    application.state.rate_limiter = RateLimiter(redis)
    application.state.health_checks = health.dependency_checks(engine, redis)

    register_error_handlers(application)
    register_auth_error_handlers(application)
    # The last middleware added runs first: the request id exists before the origin check.
    application.add_middleware(OriginCheckMiddleware, allowed_origins=settings.allowed_origins)
    application.add_middleware(RequestContextMiddleware)
    application.include_router(health.router)
    application.include_router(auth_router)
    return application


app = create_app()
