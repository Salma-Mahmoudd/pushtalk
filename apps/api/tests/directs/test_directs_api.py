import uuid
from collections.abc import Callable
from typing import Any

import pytest
from fastapi import FastAPI
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from pushtalk.channels.models import Channel, ChannelKind
from pushtalk.core.security import ACCESS_COOKIE
from pushtalk.directs.repository import DirectRepository, dm_key
from tests.helpers import create_channel, signup
from tests.ws import WsClient

pytestmark = pytest.mark.integration


@pytest.fixture
async def people(db_client: AsyncClient, make_client: Callable[[], AsyncClient]) -> dict[str, Any]:
    """alice (db_client), bob and carol, each signed in on their own client."""
    alice = await signup(db_client, "alice")
    bob_client, carol_client = make_client(), make_client()
    bob = await signup(bob_client, "bob")
    carol = await signup(carol_client, "carol")
    return {
        "alice": alice,
        "bob": bob,
        "carol": carol,
        "bob_client": bob_client,
        "carol_client": carol_client,
    }


async def test_opening_twice_from_either_side_gives_one_conversation(
    db_client: AsyncClient, people: dict[str, Any]
) -> None:
    first = await db_client.post("/api/dms", json={"user_id": people["bob"]["id"]})
    again = await db_client.post("/api/dms", json={"user_id": people["bob"]["id"]})
    from_bob = await people["bob_client"].post("/api/dms", json={"user_id": people["alice"]["id"]})

    assert (first.status_code, again.status_code, from_bob.status_code) == (201, 200, 200)
    assert first.json()["id"] == again.json()["id"] == from_bob.json()["id"]
    assert first.json()["peer"] == {"id": people["bob"]["id"], "username": "bob"}
    assert from_bob.json()["peer"]["username"] == "alice"


async def test_a_lost_race_reads_the_winners_channel(
    db_sessionmaker: async_sessionmaker[AsyncSession], people: dict[str, Any]
) -> None:
    alice, bob = uuid.UUID(people["alice"]["id"]), uuid.UUID(people["bob"]["id"])
    async with db_sessionmaker() as session:
        # Another request inserted the pair's channel a moment earlier.
        winner = Channel(kind=ChannelKind.direct, dm_key=dm_key(bob, alice), created_by=bob)
        session.add(winner)
        await session.flush()

        channel, created = await DirectRepository(session).get_or_create(alice, bob)

    assert (channel.id, created) == (winner.id, False)


async def test_cannot_open_a_conversation_with_yourself_or_nobody(
    db_client: AsyncClient, people: dict[str, Any]
) -> None:
    yourself = await db_client.post("/api/dms", json={"user_id": people["alice"]["id"]})
    nobody = await db_client.post("/api/dms", json={"user_id": str(uuid.uuid4())})

    assert (yourself.status_code, yourself.json()["error"]["code"]) == (
        422,
        "cannot_message_yourself",
    )
    assert (nobody.status_code, nobody.json()["error"]["code"]) == (404, "user_not_found")


async def test_conversations_stay_private(db_client: AsyncClient, people: dict[str, Any]) -> None:
    await create_channel(db_client, "general")
    dm = (await db_client.post("/api/dms", json={"user_id": people["bob"]["id"]})).json()
    carol = people["carol_client"]

    listed = (await carol.get("/api/channels")).json()
    assert [channel["name"] for channel in listed] == ["general"]  # Groups only.
    assert (await carol.get(f"/api/channels/{dm['id']}")).status_code == 404
    assert (await carol.get(f"/api/channels/{dm['id']}/messages")).status_code == 404
    join = await carol.post(f"/api/channels/{dm['id']}/join")
    assert (join.status_code, join.json()["error"]["code"]) == (403, "cannot_join_direct")
    assert (await carol.get("/api/dms")).json() == []


async def test_list_and_channel_details_name_the_other_person(
    db_client: AsyncClient, people: dict[str, Any]
) -> None:
    dm = (await db_client.post("/api/dms", json={"user_id": people["bob"]["id"]})).json()

    listed = (await people["bob_client"].get("/api/dms")).json()
    details = (await people["bob_client"].get(f"/api/channels/{dm['id']}")).json()

    assert [(d["id"], d["peer"]["username"], d["online"]) for d in listed] == [
        (dm["id"], "alice", False)
    ]
    assert (details["kind"], details["name"], details["peer"]["username"]) == (
        "direct",
        None,
        "alice",
    )


async def test_user_search_matches_prefixes_and_skips_yourself(
    db_client: AsyncClient, make_client: Callable[[], AsyncClient], people: dict[str, Any]
) -> None:
    await signup(make_client(), "al_x")
    await signup(make_client(), "alxy")

    async def names(query: str) -> list[str]:
        response = await db_client.get("/api/users", params={"query": query})
        return [user["username"] for user in response.json()]

    assert await names("AL") == ["al_x", "alxy"]  # Not alice herself.
    assert await names("al_") == ["al_x"]  # "_" is a literal, not a wildcard.
    assert await names("b") == ["bob"]
    assert (await db_client.get("/api/users", params={"query": "a%"})).status_code == 422


async def test_opening_is_rate_limited(
    db_app: FastAPI, db_client: AsyncClient, people: dict[str, Any]
) -> None:
    db_app.state.settings = db_app.state.settings.model_copy(
        update={"rate_limit_dm_create_user": "1/60"}
    )
    await db_client.post("/api/dms", json={"user_id": people["bob"]["id"]})
    refused = await db_client.post("/api/dms", json={"user_id": people["carol"]["id"]})

    assert refused.status_code == 429


async def test_user_socket_announces_new_conversations_and_presence(
    db_app: FastAPI, db_client: AsyncClient, people: dict[str, Any]
) -> None:
    cookies = {ACCESS_COOKIE: people["bob_client"].cookies[ACCESS_COOKIE]}
    async with WsClient(db_app, "/ws/me", cookies) as bob_ws:
        await bob_ws.accepted()
        await bob_ws.next_event("hello")
        dm = (await db_client.post("/api/dms", json={"user_id": people["bob"]["id"]})).json()
        created = await bob_ws.next_event("dm.created")
        listed = (await db_client.get("/api/dms")).json()

    assert created["data"] == {"channel_id": dm["id"]}
    assert dm["online"] is True  # bob had PushTalk open.
    assert listed[0]["online"] is True
    assert (await db_client.get("/api/dms")).json()[0]["online"] is False


async def test_user_socket_needs_a_session(db_app: FastAPI) -> None:
    async with WsClient(db_app, "/ws/me") as ws:
        await ws.accepted()
        assert await ws.closed_with() == 4401
