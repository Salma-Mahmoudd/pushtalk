import asyncio
import uuid
from collections.abc import Awaitable, Callable
from pathlib import Path

import structlog
from fastapi import UploadFile
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from pushtalk.auth.models import User
from pushtalk.channels.models import ChannelMember
from pushtalk.channels.service import ChannelService
from pushtalk.core.config import Settings
from pushtalk.infra import audio
from pushtalk.infra.storage import FileStorage
from pushtalk.messages.errors import (
    InvalidAudio,
    MessageNotFound,
    PayloadTooLarge,
    ProcessingUnavailable,
    UnsupportedMedia,
)
from pushtalk.messages.models import Message, MessageStatus
from pushtalk.messages.repository import MessageRepository, to_out
from pushtalk.messages.schemas import MessageOut, MessagePage
from pushtalk.realtime.bus import EventBus, event, user_topic

log = structlog.get_logger(__name__)

Enqueue = Callable[[uuid.UUID], Awaitable[None]]
_COPY_CHUNK = 64 * 1024


class MessageService:
    def __init__(
        self,
        session: AsyncSession,
        channels: ChannelService,
        storage: FileStorage,
        bus: EventBus,
        settings: Settings,
        enqueue: Enqueue,
    ) -> None:
        self._session = session
        self._messages = MessageRepository(session)
        self._channels = channels
        self._storage = storage
        self._bus = bus
        self._settings = settings
        self._enqueue = enqueue

    async def create_voice_message(
        self, user: User, channel_id: uuid.UUID, upload: UploadFile, client_msg_id: uuid.UUID
    ) -> MessageOut:
        await self._channels.require_member(user.id, channel_id)
        # A retried upload (lost response) returns the message created the first time.
        existing = await self._messages.get_by_client_id(user.id, client_msg_id)
        if existing is not None:
            return to_out(existing, user.username)

        if upload.size is not None and upload.size > self._settings.max_upload_bytes:
            raise PayloadTooLarge()
        container = audio.sniff(await upload.read(12))
        if container is None:
            raise UnsupportedMedia()
        await upload.seek(0)
        temp = self._storage.temp_path(container.extension)
        try:
            await asyncio.to_thread(self._copy_limited, upload, temp)
            await self._check_duration(temp)
            message = Message(
                id=uuid.uuid4(),
                channel_id=channel_id,
                sender_id=user.id,
                client_msg_id=client_msg_id,
                status=MessageStatus.processing,
                original_key=f"originals/{uuid.uuid4().hex}{container.extension}",
            )
            await self._storage.move_in(temp, message.original_key)
        finally:
            temp.unlink(missing_ok=True)

        try:
            await self._messages.add(message)
            await self._session.commit()
        except IntegrityError:  # The same upload arrived twice at the same moment.
            await self._session.rollback()
            await self._storage.delete(message.original_key)
            existing = await self._messages.get_by_client_id(user.id, client_msg_id)
            assert existing is not None
            return to_out(existing, user.username)

        try:
            await self._enqueue(message.id)
        except Exception as exc:
            log.error(
                "messages.enqueue_failed", message_id=str(message.id), error_type=type(exc).__name__
            )
            message.status = MessageStatus.failed
            message.failure_reason = "queue_unavailable"
            await self._session.commit()
            raise ProcessingUnavailable() from exc

        out = to_out(message, user.username)
        # The sender's other tabs show the "sending" bubble too.
        await self._bus.publish(
            user_topic(user.id), event("message.processing", **out.model_dump(mode="json"))
        )
        log.info("messages.accepted", message_id=str(message.id), channel_id=str(channel_id))
        return out

    async def history(
        self,
        user: User,
        channel_id: uuid.UUID,
        *,
        after_seq: int | None = None,
        before_seq: int | None = None,
        limit: int = 50,
    ) -> MessagePage:
        await self._channels.require_member(user.id, channel_id)
        messages, has_more = await self._messages.list_ready(
            channel_id, after_seq=after_seq, before_seq=before_seq, limit=limit
        )
        pending = await self._messages.list_pending(channel_id, user.id)
        return MessagePage(messages=messages, pending=pending, has_more=has_more)

    async def audio_path(self, user: User, message_id: uuid.UUID) -> Path:
        """The processed file, for members only; anything else looks like a missing message."""
        message = await self._messages.get(message_id)
        if (
            message is None
            or message.status is not MessageStatus.ready
            or message.audio_key is None
            or await self._session.get(ChannelMember, (message.channel_id, user.id)) is None
        ):
            raise MessageNotFound()
        return self._storage.path(message.audio_key)

    def _copy_limited(self, upload: UploadFile, target: Path) -> None:
        """Copies the upload to disk, refusing it once it passes the size limit."""
        copied = 0
        with target.open("wb") as out:
            while chunk := upload.file.read(_COPY_CHUNK):
                copied += len(chunk)
                if copied > self._settings.max_upload_bytes:
                    raise PayloadTooLarge()
                out.write(chunk)

    async def _check_duration(self, path: Path) -> None:
        try:
            duration = await audio.duration_ms(path)
        except audio.AudioToolError:
            raise InvalidAudio() from None
        if not self._settings.min_duration_ms <= duration <= self._settings.max_duration_ms:
            raise InvalidAudio(
                f"Recordings must be {self._settings.min_duration_ms / 1000:g}"
                f" to {self._settings.max_duration_ms / 1000:g} seconds long."
            )
