import uuid

from sqlalchemy import Select, select
from sqlalchemy.ext.asyncio import AsyncSession

from pushtalk.auth.models import User
from pushtalk.messages.models import Message, MessageStatus
from pushtalk.messages.schemas import MessageOut, SenderOut


def to_out(message: Message, username: str) -> MessageOut:
    return MessageOut(
        id=message.id,
        channel_id=message.channel_id,
        client_msg_id=message.client_msg_id,
        sender=SenderOut(id=message.sender_id, username=username),
        status=message.status,
        seq=message.seq,
        duration_ms=message.duration_ms,
        waveform=message.waveform,
        failure_reason=message.failure_reason,
        created_at=message.created_at,
        transcript_status=message.transcript_status,
        transcript=message.transcript,
        transcript_lang=message.transcript_lang,
    )


def _with_sender() -> Select[Message, str]:
    return select(Message, User.username).join(User, User.id == Message.sender_id)


class MessageRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def add(self, message: Message) -> None:
        self._session.add(message)
        await self._session.flush()

    async def get(self, message_id: uuid.UUID) -> Message | None:
        return await self._session.get(Message, message_id)

    async def get_by_client_id(
        self, sender_id: uuid.UUID, client_msg_id: uuid.UUID
    ) -> Message | None:
        return await self._session.scalar(
            select(Message).where(
                Message.sender_id == sender_id, Message.client_msg_id == client_msg_id
            )
        )

    async def lock(self, message_id: uuid.UUID) -> Message | None:
        """Locks the row: one worker at a time finishes a message."""
        return await self._session.get(Message, message_id, with_for_update=True)

    async def list_ready(
        self,
        channel_id: uuid.UUID,
        *,
        after_seq: int | None,
        before_seq: int | None,
        limit: int,
    ) -> tuple[list[MessageOut], bool]:
        """Ready messages in seq order, one page; the flag tells whether more exist."""
        query = _with_sender().where(
            Message.channel_id == channel_id, Message.status == MessageStatus.ready
        )
        if after_seq is not None:
            query = query.where(Message.seq > after_seq).order_by(Message.seq)
        else:
            # Newest page by default, or the page before `before_seq` (scrolling back).
            if before_seq is not None:
                query = query.where(Message.seq < before_seq)
            query = query.order_by(Message.seq.desc())
        rows = (await self._session.execute(query.limit(limit + 1))).all()
        page = [to_out(message, username) for message, username in rows[:limit]]
        if after_seq is None:
            page.reverse()
        return page, len(rows) > limit

    async def list_pending(self, channel_id: uuid.UUID, sender_id: uuid.UUID) -> list[MessageOut]:
        rows = (
            await self._session.execute(
                _with_sender()
                .where(
                    Message.channel_id == channel_id,
                    Message.sender_id == sender_id,
                    Message.status != MessageStatus.ready,
                )
                .order_by(Message.created_at)
            )
        ).all()
        return [to_out(message, username) for message, username in rows]
