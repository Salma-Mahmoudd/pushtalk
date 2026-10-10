import uuid
from datetime import UTC, datetime
from typing import Literal

import structlog
from sqlalchemy import func, select, update
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from pushtalk.auth.models import User
from pushtalk.channels.models import ChannelMember
from pushtalk.messages.errors import MessageNotFound, NotTheSender
from pushtalk.messages.models import Message, MessageReceipt, MessageStatus
from pushtalk.messages.schemas import ReceiptSummary, RecipientReceipt
from pushtalk.realtime.bus import EventBus, event, user_topic

log = structlog.get_logger(__name__)

ReceiptStatus = Literal["delivered", "played"]


class ReceiptService:
    """Delivered/played reports from recipients' apps, and what senders see of them."""

    def __init__(self, session: AsyncSession, bus: EventBus) -> None:
        self._session = session
        self._bus = bus

    async def record(
        self,
        user_id: uuid.UUID,
        channel_id: uuid.UUID,
        message_id: uuid.UUID,
        status: ReceiptStatus,
    ) -> None:
        """Stores one report and tells the sender; repeats and invalid reports are ignored."""
        message = await self._session.get(Message, message_id)
        if (
            message is None
            or message.channel_id != channel_id
            or message.status is not MessageStatus.ready
            or message.sender_id == user_id
        ):
            return
        now = datetime.now(UTC)
        # Atomic, because two tabs of one user report the same message at the same moment:
        # a read-then-insert would let both insert and one would fail on the primary key.
        receipt = await self._session.scalar(
            insert(MessageReceipt)
            .values(
                message_id=message_id,
                user_id=user_id,
                delivered_at=now,
                played_at=now if status == "played" else None,
            )
            .on_conflict_do_nothing()
            .returning(MessageReceipt)
        )
        if receipt is None and status == "played":
            receipt = await self._session.scalar(
                update(MessageReceipt)
                .where(
                    MessageReceipt.message_id == message_id,
                    MessageReceipt.user_id == user_id,
                    MessageReceipt.played_at.is_(None),
                )
                .values(played_at=now)
                .returning(MessageReceipt)
            )
        if receipt is None:
            return  # Nothing new (a repeat, or another tab was first): no event.
        await self._session.commit()

        if status == "played":
            # The user's other tabs and devices drop it from their queues: heard once is enough.
            await self._bus.publish(
                user_topic(user_id),
                event("message.played", message_id=str(message_id), channel_id=str(channel_id)),
            )
        summary = await self.summary(message)
        username = await self._session.scalar(select(User.username).where(User.id == user_id))
        await self._bus.publish(
            user_topic(message.sender_id),
            event(
                "receipt.updated",
                message_id=str(message_id),
                channel_id=str(channel_id),
                **summary.model_dump(),
                recipient=RecipientReceipt(
                    user_id=user_id,
                    username=username or "",
                    delivered_at=receipt.delivered_at,
                    played_at=receipt.played_at,
                ).model_dump(mode="json"),
            ),
        )

    async def summary(self, message: Message) -> ReceiptSummary:
        return (await self.summaries(message.channel_id, message.sender_id, [message.id]))[
            message.id
        ]

    async def summaries(
        self, channel_id: uuid.UUID, sender_id: uuid.UUID, message_ids: list[uuid.UUID]
    ) -> dict[uuid.UUID, ReceiptSummary]:
        """Aggregates for several messages of one sender in one channel."""
        members = await self._session.scalar(
            select(func.count()).where(ChannelMember.channel_id == channel_id)
        )
        rows = (
            await self._session.execute(
                select(
                    MessageReceipt.message_id,
                    func.count(),
                    func.count(MessageReceipt.played_at),
                )
                .where(MessageReceipt.message_id.in_(message_ids))
                .group_by(MessageReceipt.message_id)
            )
        ).all()
        counts = {message_id: (delivered, played) for message_id, delivered, played in rows}
        total = max(0, int(members or 0) - 1)
        return {
            message_id: ReceiptSummary(
                delivered=counts.get(message_id, (0, 0))[0],
                played=counts.get(message_id, (0, 0))[1],
                total=total,
            )
            for message_id in message_ids
        }

    async def details(self, user_id: uuid.UUID, message_id: uuid.UUID) -> list[RecipientReceipt]:
        """Every other member of the channel with their report times; for the sender only."""
        message = await self._session.get(Message, message_id)
        if (
            message is None
            or await self._session.get(ChannelMember, (message.channel_id, user_id)) is None
        ):
            raise MessageNotFound()
        if message.sender_id != user_id:
            raise NotTheSender()
        rows = (
            await self._session.execute(
                select(
                    User.id, User.username, MessageReceipt.delivered_at, MessageReceipt.played_at
                )
                .join(ChannelMember, ChannelMember.user_id == User.id)
                .outerjoin(
                    MessageReceipt,
                    (MessageReceipt.user_id == User.id) & (MessageReceipt.message_id == message_id),
                )
                .where(ChannelMember.channel_id == message.channel_id, User.id != user_id)
                .order_by(User.username)
            )
        ).all()
        return [
            RecipientReceipt(user_id=uid, username=name, delivered_at=delivered, played_at=played)
            for uid, name, delivered, played in rows
        ]
