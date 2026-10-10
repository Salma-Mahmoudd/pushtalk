from fastapi import FastAPI
from httpx import AsyncClient
from starlette.types import Message

ITEM = {"name": "mic", "size": 1}


async def _websocket_handshake(app: FastAPI, origin: str) -> list[Message]:
    """Opens /ws/test with raw ASGI messages and returns everything the app sent back."""
    scope = {
        "type": "websocket",
        "asgi": {"version": "3.0"},
        "scheme": "ws",
        "server": ("test", 80),
        "client": ("127.0.0.1", 50000),
        "root_path": "",
        "path": "/ws/test",
        "raw_path": b"/ws/test",
        "query_string": b"",
        "headers": [(b"origin", origin.encode())],
        "subprotocols": [],
    }
    inbox: list[Message] = [{"type": "websocket.connect"}]
    sent: list[Message] = []

    async def receive() -> Message:
        return inbox.pop(0) if inbox else {"type": "websocket.disconnect", "code": 1000}

    async def send(message: Message) -> None:
        sent.append(message)

    await app(scope, receive, send)
    return sent


async def test_post_from_foreign_origin_is_refused(client: AsyncClient) -> None:
    response = await client.post(
        "/api/test/items", json=ITEM, headers={"Origin": "https://evil.example"}
    )

    assert response.status_code == 403
    assert response.json()["error"]["code"] == "csrf_failed"
    assert response.json()["request_id"] == response.headers["X-Request-ID"]


async def test_post_from_foreign_referer_is_refused(client: AsyncClient) -> None:
    response = await client.post(
        "/api/test/items", json=ITEM, headers={"Referer": "https://evil.example/page"}
    )

    assert response.status_code == 403


async def test_post_from_allowed_origin_passes(client: AsyncClient, allowed_origin: str) -> None:
    response = await client.post("/api/test/items", json=ITEM, headers={"Origin": allowed_origin})

    assert response.status_code == 200


async def test_post_without_origin_passes(client: AsyncClient) -> None:
    """Non-browser clients send no Origin and cannot carry a victim's cookies."""
    response = await client.post("/api/test/items", json=ITEM)

    assert response.status_code == 200


async def test_safe_method_from_foreign_origin_passes(client: AsyncClient) -> None:
    response = await client.get("/api/health", headers={"Origin": "https://evil.example"})

    assert response.status_code == 200


async def test_websocket_from_foreign_origin_is_refused(app: FastAPI) -> None:
    sent = await _websocket_handshake(app, "https://evil.example")

    # Closing before accepting makes the server reject the handshake.
    assert [message["type"] for message in sent] == ["websocket.close"]


async def test_websocket_from_allowed_origin_connects(app: FastAPI, allowed_origin: str) -> None:
    sent = await _websocket_handshake(app, allowed_origin)

    assert sent[0]["type"] == "websocket.accept"
    assert {"type": "websocket.send", "text": "hello"} in sent
