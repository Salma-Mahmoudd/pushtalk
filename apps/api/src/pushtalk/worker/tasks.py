from __future__ import annotations

import asyncio
import uuid
from collections.abc import Awaitable, Callable

import structlog
from celery import Task
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool

from pushtalk.core.config import get_settings
from pushtalk.infra.redis import create_redis
from pushtalk.infra.storage import FileStorage
from pushtalk.messages.processing import ProcessingContext, fail_message, process_message
from pushtalk.realtime.bus import EventBus
from pushtalk.worker.celery_app import PROCESS_MESSAGE, celery_app

log = structlog.get_logger(__name__)

MAX_RETRIES = 3


async def _with_context(job: Callable[[ProcessingContext], Awaitable[None]]) -> None:
    """Fresh connections per task: Celery runs each task in its own event loop (asyncio.run),
    and asyncpg connections cannot move between loops; NullPool keeps none around."""
    settings = get_settings()
    engine = create_async_engine(str(settings.database_url), poolclass=NullPool)
    redis = create_redis(str(settings.redis_url))
    try:
        await job(
            ProcessingContext(
                sessionmaker=async_sessionmaker(engine, expire_on_commit=False),
                storage=FileStorage(settings.media_dir),
                bus=EventBus(redis),
            )
        )
    finally:
        await redis.aclose()
        await engine.dispose()


@celery_app.task(bind=True, name=PROCESS_MESSAGE, max_retries=MAX_RETRIES)
def process_message_task(self: Task[[str], None], message_id: str) -> None:
    target = uuid.UUID(message_id)
    try:
        asyncio.run(_with_context(lambda ctx: process_message(target, ctx)))
    except Exception as exc:
        # Unreadable audio is handled inside; anything raised here is infrastructure
        # (database, Redis, disk) and may work on a later try.
        if self.request.retries >= MAX_RETRIES:
            log.error("processing.gave_up", message_id=message_id, error_type=type(exc).__name__)
            asyncio.run(
                _with_context(lambda ctx: fail_message(target, "processing_unavailable", ctx))
            )
            return
        raise self.retry(exc=exc, countdown=2 ** (self.request.retries + 1)) from exc
