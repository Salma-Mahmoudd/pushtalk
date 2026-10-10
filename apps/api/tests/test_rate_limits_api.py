"""The per-user limits on uploads, channel creation and WebSocket events."""

import uuid
from collections.abc import Callable

import pytest
from fastapi import FastAPI
from httpx import AsyncClient

from pushtalk.core.security import ACCESS_COOKIE
from tests.helpers import create_channel, signup
from tests.ws import WsClient

pytestmark = pytest.mark.integration


def _limits(app: FastAPI, **limits: str) -> None:
    app.state.settings = app.state.settings.model_copy(update=limits)


async def _upload(client: AsyncClient, channel_id: str) -> int:
    response = await client.post(
        f"/api/channels/{channel_id}/messages",
        files={"file": ("x.webm", b"not audio", "audio/webm")},
        data={"client_msg_id": str(uuid.uuid4())},
    )
    return response.status_code


async def test_uploads_are_limited_per_user(
    db_app: FastAPI, db_client: AsyncClient, make_client: Callable[[], AsyncClient]
) -> None:
    _limits(db_app, rate_limit_upload_user="2/60")
    await signup(db_client, "alice")
    channel_id = str((await create_channel(db_client, "general"))["id"])
    bob = make_client()
    await signup(bob, "bob")
    await bob.post(f"/api/channels/{channel_id}/join")

    # Counted before validation: rejected recordings use up the allowance too.
    assert [await _upload(db_client, channel_id) for _ in range(2)] == [415, 415]
    refused = await db_client.post(
        f"/api/channels/{channel_id}/messages",
        files={"file": ("x.webm", b"not audio", "audio/webm")},
        data={"client_msg_id": str(uuid.uuid4())},
    )
    assert refused.status_code == 429
    assert refused.json()["error"]["code"] == "rate_limited"
    assert 1 <= int(refused.headers["Retry-After"]) <= 60
    # Another user has their own allowance.
    assert await _upload(bob, channel_id) == 415


async def test_daily_upload_limit_applies_too(db_app: FastAPI, db_client: AsyncClient) -> None:
    _limits(db_app, rate_limit_upload_user_daily="1/86400")
    await signup(db_client, "alice")
    channel_id = str((await create_channel(db_client, "general"))["id"])

    assert [await _upload(db_client, channel_id) for _ in range(2)] == [415, 429]


async def test_channel_creation_is_limited_per_user(
    db_app: FastAPI, db_client: AsyncClient
) -> None:
    _limits(db_app, rate_limit_channel_create_user="2/3600")
    await signup(db_client, "alice")
    statuses = [
        (await db_client.post("/api/channels", json={"name": f"room {n}"})).status_code
        for n in range(3)
    ]

    assert statuses == [201, 201, 429]


async def test_websocket_events_over_the_limit_are_dropped(
    db_app: FastAPI, db_client: AsyncClient
) -> None:
    _limits(db_app, rate_limit_ws_events="2/60")
    await signup(db_client, "alice")
    channel_id = (await create_channel(db_client, "general"))["id"]
    cookies = {ACCESS_COOKIE: db_client.cookies[ACCESS_COOKIE]}

    async with WsClient(db_app, f"/ws/channels/{channel_id}", cookies) as ws:
        await ws.accepted()
        for _ in range(3):
            await ws.send_json({"type": "ping"})
        await ws.next_event("pong")
        await ws.next_event("pong")
        error = await ws.next_event("error")

    assert error["data"]["code"] == "rate_limited"
