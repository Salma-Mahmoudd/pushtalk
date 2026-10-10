"""Small helpers shared by API tests."""

from typing import Any

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
