import uuid

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import aliased

from pushtalk.auth.models import User
from pushtalk.channels.models import Channel, ChannelKind, ChannelMember

SEARCH_LIMIT = 20


def dm_key(first: uuid.UUID, second: uuid.UUID) -> str:
    """The same key whoever starts the conversation."""
    low, high = sorted((str(first), str(second)))
    return f"{low}:{high}"


class DirectRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get_or_create(self, user_id: uuid.UUID, peer_id: uuid.UUID) -> tuple[Channel, bool]:
        """The pair's channel and whether it was created now. Two users opening it at the same
        moment both get the one row: the unique dm_key decides, the loser reads the winner's."""
        key = dm_key(user_id, peer_id)
        created_id = await self._session.scalar(
            insert(Channel)
            .values(id=uuid.uuid4(), kind=ChannelKind.direct, dm_key=key, created_by=user_id)
            .on_conflict_do_nothing(index_elements=[Channel.dm_key])
            .returning(Channel.id)
        )
        if created_id is not None:
            for member in (user_id, peer_id):
                self._session.add(ChannelMember(channel_id=created_id, user_id=member))
            await self._session.flush()
        channel = await self._session.scalar(select(Channel).where(Channel.dm_key == key))
        assert channel is not None
        return channel, created_id is not None

    async def list_for(self, user_id: uuid.UUID) -> list[tuple[Channel, User]]:
        """The user's direct channels with the other participant, newest activity first."""
        mine = aliased(ChannelMember)
        theirs = aliased(ChannelMember)
        rows = await self._session.execute(
            select(Channel, User)
            .join(mine, (mine.channel_id == Channel.id) & (mine.user_id == user_id))
            .join(theirs, (theirs.channel_id == Channel.id) & (theirs.user_id != user_id))
            .join(User, User.id == theirs.user_id)
            .where(Channel.kind == ChannelKind.direct)
            .order_by(Channel.last_seq.desc(), Channel.created_at.desc())
        )
        return [(channel, user) for channel, user in rows]

    async def search_users(self, prefix: str, exclude: uuid.UUID) -> list[User]:
        # "_" is a LIKE wildcard and allowed in usernames, so it is escaped.
        pattern = prefix.lower().replace("\\", "\\\\").replace("_", "\\_").replace("%", "\\%")
        rows = await self._session.scalars(
            select(User)
            .where(User.username.like(f"{pattern}%", escape="\\"), User.id != exclude)
            .order_by(User.username)
            .limit(SEARCH_LIMIT)
        )
        return list(rows)
