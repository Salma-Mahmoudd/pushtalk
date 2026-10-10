import uuid

import pytest
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from pushtalk.auth.models import User
from pushtalk.channels.models import Channel, ChannelKind
from pushtalk.channels.repository import ChannelRepository

pytestmark = pytest.mark.integration


async def test_add_member_reports_only_new_memberships(
    db_sessionmaker: async_sessionmaker[AsyncSession],
) -> None:
    async with db_sessionmaker() as session:
        user = User(username="alice", password_hash="x")
        session.add(user)
        await session.flush()
        channel = Channel(kind=ChannelKind.group, name="general", created_by=user.id)
        session.add(channel)
        await session.flush()
        channels = ChannelRepository(session)

        assert await channels.add_member(channel.id, user.id) is True
        assert await channels.add_member(channel.id, user.id) is False
        assert await channels.is_member(channel.id, user.id) is True
        assert await channels.is_member(channel.id, uuid.uuid4()) is False
