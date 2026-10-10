import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from pushtalk.auth.models import User
from pushtalk.channels.presence import PresenceService
from pushtalk.channels.schemas import UserOut
from pushtalk.directs.errors import CannotMessageYourself, UserNotFound
from pushtalk.directs.repository import DirectRepository
from pushtalk.directs.schemas import DirectOut
from pushtalk.realtime.bus import EventBus, event, user_topic

# Presence of the app-wide user socket (/ws/me), kept like a channel's under this id.
APP_PRESENCE = uuid.UUID(int=0)


class DirectService:
    def __init__(self, session: AsyncSession, presence: PresenceService, bus: EventBus) -> None:
        self._session = session
        self._directs = DirectRepository(session)
        self._presence = presence
        self._bus = bus

    async def open(self, user: User, peer_id: uuid.UUID) -> tuple[DirectOut, bool]:
        """The conversation with `peer_id`, created on first use; True when created now."""
        if peer_id == user.id:
            raise CannotMessageYourself()
        peer = await self._session.get(User, peer_id)
        if peer is None:
            raise UserNotFound()
        channel, created = await self._directs.get_or_create(user.id, peer_id)
        await self._session.commit()
        online = await self._presence.online(APP_PRESENCE)
        direct = DirectOut(
            id=channel.id,
            peer=UserOut(id=peer.id, username=peer.username),
            online=peer.id in online,
        )
        if created:
            # Both sides' sidebars (every tab) list the new conversation at once.
            for listener in (user.id, peer.id):
                await self._bus.publish(
                    user_topic(listener), event("dm.created", channel_id=str(channel.id))
                )
        return direct, created

    async def list_for(self, user: User) -> list[DirectOut]:
        online = await self._presence.online(APP_PRESENCE)
        return [
            DirectOut(
                id=channel.id,
                peer=UserOut(id=peer.id, username=peer.username),
                online=peer.id in online,
            )
            for channel, peer in await self._directs.list_for(user.id)
        ]

    async def search_users(self, user: User, prefix: str) -> list[UserOut]:
        return [
            UserOut(id=found.id, username=found.username)
            for found in await self._directs.search_users(prefix, exclude=user.id)
        ]
