"""Drives the app's WebSocket endpoints with raw ASGI messages, several sockets at once."""

import asyncio
import json
from collections.abc import Callable
from types import TracebackType
from typing import Any, Self

from starlette.types import ASGIApp, Message


class WsClient:
    def __init__(
        self, app: ASGIApp, path: str, cookies: dict[str, str] | None = None, query: str = ""
    ) -> None:
        self._app = app
        cookie = "; ".join(f"{name}={value}" for name, value in (cookies or {}).items())
        self._scope = {
            "type": "websocket",
            "asgi": {"version": "3.0"},
            "scheme": "ws",
            "server": ("test", 80),
            "client": ("127.0.0.1", 50000),
            "root_path": "",
            "path": path,
            "raw_path": path.encode(),
            "query_string": query.encode(),
            "headers": [(b"cookie", cookie.encode())] if cookie else [],
            "subprotocols": [],
        }
        self._to_app: asyncio.Queue[Message] = asyncio.Queue()
        self._from_app: asyncio.Queue[Message] = asyncio.Queue()
        self._task: asyncio.Future[None] | None = None

    async def __aenter__(self) -> Self:
        await self._to_app.put({"type": "websocket.connect"})
        self._task = asyncio.ensure_future(
            self._app(self._scope, self._to_app.get, self._from_app.put)
        )
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        await self._to_app.put({"type": "websocket.disconnect", "code": 1000})
        assert self._task is not None
        await asyncio.wait_for(self._task, timeout=5)

    async def receive(self, wait_s: float = 3) -> Message:
        return await asyncio.wait_for(self._from_app.get(), wait_s)

    async def accepted(self) -> None:
        assert (await self.receive())["type"] == "websocket.accept"

    async def closed_with(self) -> int:
        message = await self.receive()
        while message["type"] == "websocket.send":  # skip events sent before the close
            message = await self.receive()
        assert message["type"] == "websocket.close", message
        code: int = message.get("code", 1000)
        return code

    async def send_json(self, payload: Any) -> None:
        await self._to_app.put({"type": "websocket.receive", "text": json.dumps(payload)})

    async def send_text(self, text: str) -> None:
        await self._to_app.put({"type": "websocket.receive", "text": text})

    async def events_until(self, type_: str, wait_s: float = 3) -> list[str]:
        """Types of all events received before the first `type_` event (which ends the list)."""
        types: list[str] = []
        while True:
            message = await self.receive(wait_s)
            assert message["type"] == "websocket.send", message
            current = json.loads(message["text"])["type"]
            if current == type_:
                return types
            types.append(current)

    async def next_event(
        self,
        type_: str,
        matching: Callable[[dict[str, Any]], bool] = lambda _: True,
        wait_s: float = 3,
    ) -> dict[str, Any]:
        """Waits for the next event of `type_` whose data matches; skips everything else."""
        deadline = asyncio.get_running_loop().time() + wait_s
        while True:
            remaining = deadline - asyncio.get_running_loop().time()
            message = await self.receive(wait_s=max(remaining, 0.01))
            assert message["type"] == "websocket.send", message
            payload: dict[str, Any] = json.loads(message["text"])
            if payload["type"] == type_ and matching(payload["data"]):
                return payload
