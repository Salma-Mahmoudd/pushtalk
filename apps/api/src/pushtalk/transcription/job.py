"""The transcriber's job: add text to a ready message, then tell the channel."""

import asyncio
import uuid
from typing import TYPE_CHECKING

import structlog
from sqlalchemy import update

from pushtalk.messages.models import Message, TranscriptStatus
from pushtalk.realtime.bus import channel_topic, event
from pushtalk.transcription.transcribers import Transcriber

if TYPE_CHECKING:
    # Type only: processing imports this module to fail a transcription it could not queue.
    from pushtalk.messages.processing import ProcessingContext

log = structlog.get_logger(__name__)


async def transcribe_message(
    message_id: uuid.UUID, ctx: "ProcessingContext", transcriber: Transcriber
) -> None:
    """Transcribes a message whose transcript is pending. Safe to run twice."""
    async with ctx.sessionmaker() as session:
        message = await session.get(Message, message_id)
        if (
            message is None
            or message.transcript_status is not TranscriptStatus.pending
            or message.audio_key is None
        ):
            log.info("transcription.skipped", message_id=str(message_id))
            return
        audio_key = message.audio_key

    transcript = await asyncio.to_thread(transcriber.transcribe, ctx.storage.path(audio_key))
    await _finish(message_id, ctx, TranscriptStatus.done, transcript.text, transcript.language)
    log.info("transcription.done", message_id=str(message_id), language=transcript.language)


async def fail_transcription(message_id: uuid.UUID, ctx: "ProcessingContext") -> None:
    """The message stays playable; its transcript is shown as unavailable."""
    await _finish(message_id, ctx, TranscriptStatus.failed, None, None)
    log.warning("transcription.failed", message_id=str(message_id))


async def _finish(
    message_id: uuid.UUID,
    ctx: "ProcessingContext",
    status: TranscriptStatus,
    text: str | None,
    language: str | None,
) -> None:
    async with ctx.sessionmaker() as session, session.begin():
        message = await session.scalar(
            update(Message)
            .where(Message.id == message_id, Message.transcript_status == TranscriptStatus.pending)
            .values(transcript_status=status, transcript=text, transcript_lang=language)
            .returning(Message)
        )
    if message is None:
        return  # Finished by another run meanwhile.
    await ctx.bus.publish(
        channel_topic(message.channel_id),
        event(
            "message.transcribed",
            id=str(message.id),
            channel_id=str(message.channel_id),
            transcript_status=status.value,
            transcript=text,
            transcript_lang=language,
        ),
    )
