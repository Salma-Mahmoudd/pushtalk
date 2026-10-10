from collections.abc import Callable

import pytest
from fastapi import FastAPI
from httpx import AsyncClient

from pushtalk.core.security import ACCESS_COOKIE
from tests.helpers import create_channel, signup
from tests.ws import WsClient

pytestmark = pytest.mark.integration


def _cookies(client: AsyncClient) -> dict[str, str]:
    return {ACCESS_COOKIE: client.cookies[ACCESS_COOKIE]}


async def test_socket_without_session_closes_4401(db_app: FastAPI, db_client: AsyncClient) -> None:
    await signup(db_client, "alice")
    channel = await create_channel(db_client, "general")

    async with WsClient(db_app, f"/ws/channels/{channel['id']}") as ws:
        await ws.accepted()
        assert await ws.closed_with() == 4401


async def test_socket_for_non_member_closes_4403(
    db_app: FastAPI, db_client: AsyncClient, make_client: Callable[[], AsyncClient]
) -> None:
    await signup(db_client, "alice")
    channel = await create_channel(db_client, "general")
    bob = make_client()
    await signup(bob, "bob")

    async with WsClient(db_app, f"/ws/channels/{channel['id']}", _cookies(bob)) as ws:
        await ws.accepted()
        assert await ws.closed_with() == 4403


async def test_member_gets_presence_snapshot_and_pong(
    db_app: FastAPI, db_client: AsyncClient
) -> None:
    alice = await signup(db_client, "alice")
    channel = await create_channel(db_client, "general")

    async with WsClient(db_app, f"/ws/channels/{channel['id']}", _cookies(db_client)) as ws:
        await ws.accepted()
        snapshot = await ws.next_event("presence.snapshot")
        assert snapshot["data"]["online_user_ids"] == [alice["id"]]

        await ws.send_json({"type": "ping"})
        await ws.next_event("pong")


async def test_bad_frames_get_an_error_and_keep_the_socket(
    db_app: FastAPI, db_client: AsyncClient
) -> None:
    await signup(db_client, "alice")
    channel = await create_channel(db_client, "general")

    async with WsClient(db_app, f"/ws/channels/{channel['id']}", _cookies(db_client)) as ws:
        await ws.accepted()
        await ws.send_text("not json")
        error = await ws.next_event("error")
        assert error["data"]["code"] == "unknown_event"

        await ws.send_json({"type": "ping"})
        await ws.next_event("pong")


async def test_members_see_each_other_come_online_and_leave(
    db_app: FastAPI, db_client: AsyncClient, make_client: Callable[[], AsyncClient]
) -> None:
    await signup(db_client, "alice")
    channel = await create_channel(db_client, "general")
    bob_client = make_client()
    bob = await signup(bob_client, "bob")
    await bob_client.post(f"/api/channels/{channel['id']}/join")
    path = f"/ws/channels/{channel['id']}"

    async with WsClient(db_app, path, _cookies(db_client)) as alice_ws:
        await alice_ws.accepted()
        await alice_ws.next_event("presence.snapshot")

        async with WsClient(db_app, path, _cookies(bob_client)) as bob_ws:
            await bob_ws.accepted()
            online = await alice_ws.next_event(
                "presence.update", lambda data: data["user_id"] == bob["id"]
            )
            assert online["data"] == {"user_id": bob["id"], "online": True}

            members = (await db_client.get(f"/api/channels/{channel['id']}/members")).json()
            assert {m["username"]: m["online"] for m in members} == {"alice": True, "bob": True}

        offline = await alice_ws.next_event(
            "presence.update", lambda data: data["user_id"] == bob["id"]
        )
        assert offline["data"] == {"user_id": bob["id"], "online": False}


async def test_logout_closes_that_sessions_sockets(db_app: FastAPI, db_client: AsyncClient) -> None:
    await signup(db_client, "alice")
    channel = await create_channel(db_client, "general")

    async with WsClient(db_app, f"/ws/channels/{channel['id']}", _cookies(db_client)) as ws:
        await ws.accepted()
        await ws.next_event("presence.snapshot")

        await db_client.post("/api/auth/logout")

        assert await ws.closed_with() == 4401


async def test_joining_announces_the_new_member(
    db_app: FastAPI, db_client: AsyncClient, make_client: Callable[[], AsyncClient]
) -> None:
    await signup(db_client, "alice")
    channel = await create_channel(db_client, "general")
    bob_client = make_client()
    bob = await signup(bob_client, "bob")

    async with WsClient(db_app, f"/ws/channels/{channel['id']}", _cookies(db_client)) as ws:
        await ws.accepted()
        await ws.next_event("presence.snapshot")

        await bob_client.post(f"/api/channels/{channel['id']}/join")
        joined = await ws.next_event("member.joined")
        assert joined["data"] == {"user_id": bob["id"], "username": "bob"}
