"""The worker's job: turn an accepted upload into a ready message, or a failed one."""

import tempfile
import uuid
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

import structlog
from sqlalchemy import update
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from pushtalk.auth.models import User
from pushtalk.channels.repository import ChannelRepository
from pushtalk.infra import audio
from pushtalk.infra.storage import FileStorage
from pushtalk.messages.models import Message, MessageStatus, TranscriptStatus
from pushtalk.messages.repository import MessageRepository, to_out
from pushtalk.realtime.bus import EventBus, channel_topic, event, user_topic
from pushtalk.transcription.job import fail_transcription

log = structlog.get_logger(__name__)


@dataclass(frozen=True)
class ProcessingContext:
    sessionmaker: async_sessionmaker[AsyncSession]
    storage: FileStorage
    bus: EventBus
    # Queues the transcription step; None when transcription is off.
    enqueue_transcription: Callable[[uuid.UUID], Awaitable[None]] | None = None


async def process_message(message_id: uuid.UUID, ctx: ProcessingContext) -> None:
    """Normalise to Opus, measure, number and broadcast. Safe to run twice for one message."""
    async with ctx.sessionmaker() as session:
        message = await session.get(Message, message_id)
        if message is None or message.status is not MessageStatus.processing:
            log.info("processing.skipped", message_id=str(message_id))
            return
        original_key = message.original_key

    audio_key = f"processed/{message_id}.ogg"
    with tempfile.TemporaryDirectory(dir=ctx.storage.temp_path().parent) as workdir:
        target = Path(workdir) / "audio.ogg"
        try:
            await audio.transcode_to_opus(ctx.storage.path(original_key), target)
            duration_ms = await audio.duration_ms(target)
            waveform = await audio.waveform_peaks(target)
        except audio.AudioToolError as exc:
            log.warning(
                "processing.invalid_audio", message_id=str(message_id), detail=str(exc)[:200]
            )
            await fail_message(message_id, "invalid_audio", ctx)
            return
        await ctx.storage.move_in(target, audio_key)

    async with ctx.sessionmaker() as session, session.begin():
        message = await MessageRepository(session).lock(message_id)
        if message is None or message.status is not MessageStatus.processing:
            return  # Another worker finished it meanwhile.
        # Numbered in the same transaction that makes it ready: gapless among ready messages.
        message.seq = await ChannelRepository(session).next_seq(message.channel_id)
        message.status = MessageStatus.ready
        message.duration_ms = duration_ms
        message.waveform = waveform
        message.audio_key = audio_key
        message.ready_at = datetime.now(UTC)
        if ctx.enqueue_transcription is not None:
            message.transcript_status = TranscriptStatus.pending
        sender = await session.get(User, message.sender_id)
        assert sender is not None  # The foreign key guarantees it.
        out = to_out(message, sender.username)

    await ctx.storage.delete(original_key)  # The processed file is the only copy kept.
    await ctx.bus.publish(
        channel_topic(out.channel_id), event("message.ready", **out.model_dump(mode="json"))
    )
    log.info("processing.ready", message_id=str(message_id), seq=out.seq, duration_ms=duration_ms)
    # After the broadcast, so delivery never waits for speech to text.
    if ctx.enqueue_transcription is not None:
        await _queue_transcription(message_id, ctx.enqueue_transcription, ctx)


async def _queue_transcription(
    message_id: uuid.UUID,
    enqueue: Callable[[uuid.UUID], Awaitable[None]],
    ctx: ProcessingContext,
) -> None:
    try:
        await enqueue(message_id)
    except Exception:
        # The message is delivered already; without a queued job its transcript never comes.
        log.exception("transcription.enqueue_failed", message_id=str(message_id))
        await fail_transcription(message_id, ctx)


async def fail_message(message_id: uuid.UUID, reason: str, ctx: ProcessingContext) -> None:
    """Marks a processing message failed and tells its sender; the original stays for debugging."""
    async with ctx.sessionmaker() as session, session.begin():
        message = await session.scalar(
            update(Message)
            .where(Message.id == message_id, Message.status == MessageStatus.processing)
            .values(status=MessageStatus.failed, failure_reason=reason)
            .returning(Message)
        )
    if message is None:
        return
    await ctx.bus.publish(
        user_topic(message.sender_id),
        event(
            "message.failed",
            id=str(message.id),
            channel_id=str(message.channel_id),
            client_msg_id=str(message.client_msg_id),
            reason=reason,
        ),
    )
    log.warning("processing.failed", message_id=str(message_id), reason=reason)
