from __future__ import annotations

import asyncio
import functools
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
from pushtalk.transcription.job import fail_transcription, transcribe_message
from pushtalk.transcription.transcribers import Transcriber, get_transcriber
from pushtalk.worker.celery_app import (
    PROCESS_MESSAGE,
    TRANSCRIBE_MESSAGE,
    celery_app,
    enqueue_transcription,
)

log = structlog.get_logger(__name__)

MAX_RETRIES = 3
TRANSCRIBE_RETRIES = 2
# Seconds; a minute of speech takes far less on the base model.
TRANSCRIBE_TIME_LIMIT = 120


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
                enqueue_transcription=(
                    None if settings.transcribe_provider == "off" else enqueue_transcription
                ),
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


@functools.cache
def _transcriber() -> Transcriber | None:
    return get_transcriber(get_settings())


@celery_app.task(
    bind=True,
    name=TRANSCRIBE_MESSAGE,
    max_retries=TRANSCRIBE_RETRIES,
    time_limit=TRANSCRIBE_TIME_LIMIT,
    soft_time_limit=TRANSCRIBE_TIME_LIMIT - 10,
)
def transcribe_message_task(self: Task[[str], None], message_id: str) -> None:
    target = uuid.UUID(message_id)
    transcriber = _transcriber()
    try:
        if transcriber is None:
            raise RuntimeError("transcription is off, yet a transcription job arrived")
        asyncio.run(_with_context(lambda ctx: transcribe_message(target, ctx, transcriber)))
    except Exception as exc:
        if self.request.retries >= TRANSCRIBE_RETRIES or transcriber is None:
            log.error("transcription.gave_up", message_id=message_id, error_type=type(exc).__name__)
            asyncio.run(_with_context(lambda ctx: fail_transcription(target, ctx)))
            return
        raise self.retry(exc=exc, countdown=2 ** (self.request.retries + 1)) from exc
