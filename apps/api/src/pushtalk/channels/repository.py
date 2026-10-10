import uuid

from sqlalchemy import exists, func, select, update
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from pushtalk.auth.models import User
from pushtalk.channels.models import Channel, ChannelKind, ChannelMember


class ChannelRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get(self, channel_id: uuid.UUID) -> Channel | None:
        return await self._session.get(Channel, channel_id)

    async def add(self, channel: Channel) -> None:
        self._session.add(channel)
        await self._session.flush()

    async def add_member(self, channel_id: uuid.UUID, user_id: uuid.UUID) -> bool:
        """Idempotent: joining twice is not an error. True if the user was not a member yet."""
        added = await self._session.scalar(
            insert(ChannelMember)
            .values(channel_id=channel_id, user_id=user_id)
            .on_conflict_do_nothing()
            .returning(ChannelMember.user_id)
        )
        return added is not None

    async def is_member(self, channel_id: uuid.UUID, user_id: uuid.UUID) -> bool:
        return bool(
            await self._session.scalar(
                select(
                    exists().where(
                        ChannelMember.channel_id == channel_id, ChannelMember.user_id == user_id
                    )
                )
            )
        )

    async def list_groups(self, user_id: uuid.UUID) -> list[tuple[Channel, bool, int]]:
        """Every group channel with whether `user_id` belongs to it and its member count."""
        member_count = (
            select(func.count())
            .where(ChannelMember.channel_id == Channel.id)
            .correlate(Channel)
            .scalar_subquery()
        )
        is_member = exists().where(
            ChannelMember.channel_id == Channel.id, ChannelMember.user_id == user_id
        )
        rows = await self._session.execute(
            select(Channel, is_member, member_count)
            .where(Channel.kind == ChannelKind.group)
            .order_by(func.lower(Channel.name))
        )
        return [(channel, bool(member), int(count)) for channel, member, count in rows]

    async def members(self, channel_id: uuid.UUID) -> list[User]:
        rows = await self._session.scalars(
            select(User)
            .join(ChannelMember, ChannelMember.user_id == User.id)
            .where(ChannelMember.channel_id == channel_id)
            .order_by(User.username)
        )
        return list(rows)

    async def next_seq(self, channel_id: uuid.UUID) -> int:
        """Takes the channel's next message number; the row lock serialises concurrent workers."""
        seq = await self._session.scalar(
            update(Channel)
            .where(Channel.id == channel_id)
            .values(last_seq=Channel.last_seq + 1)
            .returning(Channel.last_seq)
        )
        assert seq is not None
        return int(seq)
