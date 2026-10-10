import re
import time
import uuid
from collections.abc import Iterable
from urllib.parse import urlsplit

import structlog
from starlette.datastructures import Headers, MutableHeaders
from starlette.types import ASGIApp, Message, Receive, Scope, Send

from pushtalk.core.errors import CsrfFailed, error_response

log = structlog.get_logger(__name__)

REQUEST_ID_HEADER = "X-Request-ID"
_VALID_REQUEST_ID = re.compile(r"[A-Za-z0-9._-]{1,64}")
_UNSAFE_METHODS = frozenset({"POST", "PUT", "PATCH", "DELETE"})


class RequestContextMiddleware:
    """Gives every request an id (logs, error bodies, X-Request-ID header) and logs its outcome."""

    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] not in ("http", "websocket"):
            await self.app(scope, receive, send)
            return

        incoming = Headers(scope=scope).get(REQUEST_ID_HEADER, "")
        request_id = incoming if _VALID_REQUEST_ID.fullmatch(incoming) else uuid.uuid4().hex
        scope.setdefault("state", {})["request_id"] = request_id
        structlog.contextvars.clear_contextvars()
        structlog.contextvars.bind_contextvars(request_id=request_id)

        if scope["type"] == "websocket":
            await self.app(scope, receive, send)
            return

        started = time.perf_counter()
        status = 500

        async def send_with_request_id(message: Message) -> None:
            nonlocal status
            if message["type"] == "http.response.start":
                status = message["status"]
                MutableHeaders(scope=message).append(REQUEST_ID_HEADER, request_id)
            await send(message)

        try:
            await self.app(scope, receive, send_with_request_id)
        finally:
            log.info(
                "request.completed",
                method=scope["method"],
                path=scope["path"],
                status=status,
                duration_ms=round((time.perf_counter() - started) * 1000, 1),
            )


class OriginCheckMiddleware:
    """CSRF protection: refuses state-changing requests and WebSocket handshakes from other sites.

    Browsers always send Origin (or Referer) on these requests, so a missing header means a
    non-browser client, which cannot carry a victim's cookies and is let through.
    """

    def __init__(self, app: ASGIApp, allowed_origins: Iterable[str]) -> None:
        self.app = app
        self.allowed_origins = frozenset(origin.rstrip("/") for origin in allowed_origins)

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        checked = scope["type"] == "websocket" or (
            scope["type"] == "http" and scope["method"] in _UNSAFE_METHODS
        )
        origin = _origin_of(scope) if checked else None
        if origin is None or origin in self.allowed_origins:
            await self.app(scope, receive, send)
            return

        log.warning("origin.rejected", origin=origin, path=scope["path"])
        if scope["type"] == "websocket":
            await receive()  # websocket.connect
            await send({"type": "websocket.close", "code": 4401})
            return
        error = CsrfFailed()
        response = error_response(
            error.status_code,
            error.code,
            error.message,
            request_id=scope.get("state", {}).get("request_id"),
        )
        await response(scope, receive, send)


def _origin_of(scope: Scope) -> str | None:
    headers = Headers(scope=scope)
    if (origin := headers.get("origin")) is not None:
        return origin.rstrip("/")
    if referer := headers.get("referer"):
        parts = urlsplit(referer)
        return f"{parts.scheme}://{parts.netloc}"
    return None
