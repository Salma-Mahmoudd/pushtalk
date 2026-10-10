from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI

from pushtalk import health
from pushtalk.core.config import Settings, get_settings
from pushtalk.core.errors import register_error_handlers
from pushtalk.core.logging import configure_logging
from pushtalk.core.middleware import OriginCheckMiddleware, RequestContextMiddleware
from pushtalk.db.session import create_engine
from pushtalk.infra.redis import create_redis


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or get_settings()
    configure_logging(settings.log_level, settings.log_format)

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
    application.state.health_checks = health.dependency_checks(engine, redis)

    register_error_handlers(application)
    # The last middleware added runs first: the request id exists before the origin check.
    application.add_middleware(OriginCheckMiddleware, allowed_origins=settings.allowed_origins)
    application.add_middleware(RequestContextMiddleware)
    application.include_router(health.router)
    return application


app = create_app()
