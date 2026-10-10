"""Small helpers shared by API tests."""

import asyncio
import json
from collections.abc import Awaitable, Callable
from typing import Any

from fakeredis import FakeAsyncRedis
from httpx import AsyncClient

PASSWORD = "correct horse"


async def signup(client: AsyncClient, username: str) -> dict[str, Any]:
    """Signs `client` up as `username`; its cookie jar then holds the session."""
    response = await client.post(
        "/api/auth/signup", json={"username": username, "password": PASSWORD}
    )
    assert response.status_code == 201, response.text
    user: dict[str, Any] = response.json()["user"]
    return user


async def create_channel(client: AsyncClient, name: str) -> dict[str, Any]:
    response = await client.post("/api/channels", json={"name": name})
    assert response.status_code == 201, response.text
    channel: dict[str, Any] = response.json()
    return channel


async def published_events(
    fake_redis: FakeAsyncRedis, topic: str, run: Callable[[], Awaitable[None]]
) -> list[dict[str, Any]]:
    """Events published on `topic` while `run` runs."""
    pubsub = fake_redis.pubsub(ignore_subscribe_messages=True)
    await pubsub.subscribe(topic)
    await run()
    events = []
    # Read for a short window: subscription confirmations come back as None too.
    deadline = asyncio.get_running_loop().time() + 0.5
    while asyncio.get_running_loop().time() < deadline:
        message = await pubsub.get_message(timeout=0.05)
        if message is not None:
            events.append(json.loads(message["data"]))
    await pubsub.aclose()  # type: ignore[no-untyped-call]
    return events
