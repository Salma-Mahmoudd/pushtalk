import uuid

from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from pushtalk.auth.models import User
from pushtalk.channels.errors import CannotJoinDirect, ChannelExists, ChannelNotFound, NotAMember
from pushtalk.channels.models import Channel, ChannelKind
from pushtalk.channels.presence import PresenceService
from pushtalk.channels.repository import ChannelRepository
from pushtalk.channels.schemas import ChannelOut, MemberOut
from pushtalk.realtime.bus import EventBus, channel_topic, event


class ChannelService:
    def __init__(
        self, session: AsyncSession, presence: PresenceService, bus: EventBus | None = None
    ) -> None:
        self._session = session
        self._channels = ChannelRepository(session)
        self._presence = presence
        self._bus = bus

    async def create(self, user: User, name: str) -> ChannelOut:
        channel = Channel(kind=ChannelKind.group, name=name, created_by=user.id)
        try:
            await self._channels.add(channel)
        except IntegrityError:  # The case-insensitive unique name index.
            await self._session.rollback()
            raise ChannelExists() from None
        await self._channels.add_member(channel.id, user.id)
        await self._session.commit()
        return ChannelOut(
            id=channel.id, kind=channel.kind, name=channel.name, is_member=True, member_count=1
        )

    async def list_all(self, user: User) -> list[ChannelOut]:
        return [
            ChannelOut(
                id=channel.id,
                kind=channel.kind,
                name=channel.name,
                is_member=is_member,
                member_count=count,
            )
            for channel, is_member, count in await self._channels.list_groups(user.id)
        ]

    async def join(self, user: User, channel_id: uuid.UUID) -> None:
        channel = await self._channels.get(channel_id)
        if channel is None:
            raise ChannelNotFound()
        if channel.kind is ChannelKind.direct:
            raise CannotJoinDirect()
        joined = await self._channels.add_member(channel_id, user.id)
        await self._session.commit()
        if joined and self._bus is not None:
            # Open rooms refresh their member list.
            await self._bus.publish(
                channel_topic(channel_id),
                event("member.joined", user_id=str(user.id), username=user.username),
            )

    async def require_member(self, user_id: uuid.UUID, channel_id: uuid.UUID) -> Channel:
        channel = await self._channels.get(channel_id)
        if channel is None:
            raise ChannelNotFound()
        if not await self._channels.is_member(channel_id, user_id):
            raise NotAMember()
        return channel

    async def get(self, user: User, channel_id: uuid.UUID) -> ChannelOut:
        channel = await self.require_member(user.id, channel_id)
        members = await self._channels.members(channel_id)
        return ChannelOut(
            id=channel.id,
            kind=channel.kind,
            name=channel.name,
            is_member=True,
            member_count=len(members),
        )

    async def members(self, user: User, channel_id: uuid.UUID) -> list[MemberOut]:
        await self.require_member(user.id, channel_id)
        online = await self._presence.online(channel_id)
        return [
            MemberOut(id=member.id, username=member.username, online=member.id in online)
            for member in await self._channels.members(channel_id)
        ]
