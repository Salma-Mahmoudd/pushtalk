from collections.abc import Callable

import pytest
from httpx import AsyncClient

from tests.helpers import create_channel, signup

pytestmark = pytest.mark.integration


async def test_create_channel_makes_creator_a_member(db_client: AsyncClient) -> None:
    await signup(db_client, "alice")

    channel = await create_channel(db_client, "  Walkie Team  ")

    assert channel["name"] == "Walkie Team"  # surrounding spaces trimmed
    assert channel["is_member"] is True
    assert channel["member_count"] == 1


async def test_channel_names_are_unique_ignoring_case(db_client: AsyncClient) -> None:
    await signup(db_client, "alice")
    await create_channel(db_client, "General")

    response = await db_client.post("/api/channels", json={"name": "GENERAL"})

    assert response.status_code == 409
    assert response.json()["error"]["code"] == "channel_exists"


@pytest.mark.parametrize("name", ["", "   ", "x" * 51, "bad\nname"])
async def test_invalid_channel_names_are_rejected(db_client: AsyncClient, name: str) -> None:
    await signup(db_client, "alice")

    response = await db_client.post("/api/channels", json={"name": name})

    assert response.status_code == 422


async def test_list_shows_all_channels_with_membership(
    db_client: AsyncClient, make_client: Callable[[], AsyncClient]
) -> None:
    await signup(db_client, "alice")
    await create_channel(db_client, "general")
    bob = make_client()
    await signup(bob, "bob")
    await create_channel(bob, "random")

    channels = (await db_client.get("/api/channels")).json()

    assert [(c["name"], c["is_member"]) for c in channels] == [
        ("general", True),
        ("random", False),
    ]


async def test_join_is_idempotent_and_grants_access(
    db_client: AsyncClient, make_client: Callable[[], AsyncClient]
) -> None:
    await signup(db_client, "alice")
    channel = await create_channel(db_client, "general")
    bob = make_client()
    await signup(bob, "bob")
    path = f"/api/channels/{channel['id']}"

    assert (await bob.get(f"{path}/members")).status_code == 403
    assert (await bob.post(f"{path}/join")).status_code == 204
    assert (await bob.post(f"{path}/join")).status_code == 204

    members = (await bob.get(f"{path}/members")).json()
    assert [m["username"] for m in members] == ["alice", "bob"]
    assert (await bob.get(path)).json()["member_count"] == 2


async def test_members_endpoint_requires_membership(
    db_client: AsyncClient, make_client: Callable[[], AsyncClient]
) -> None:
    await signup(db_client, "alice")
    channel = await create_channel(db_client, "secret")
    bob = make_client()
    await signup(bob, "bob")

    response = await bob.get(f"/api/channels/{channel['id']}/members")

    assert response.status_code == 403
    assert response.json()["error"]["code"] == "not_a_member"


async def test_unknown_channel_is_404(db_client: AsyncClient) -> None:
    await signup(db_client, "alice")

    response = await db_client.post("/api/channels/00000000-0000-0000-0000-000000000000/join")

    assert response.status_code == 404


async def test_channels_require_login(db_client: AsyncClient) -> None:
    assert (await db_client.get("/api/channels")).status_code == 401
