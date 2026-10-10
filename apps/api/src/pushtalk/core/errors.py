from collections.abc import Mapping
from http import HTTPStatus

import structlog
from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from starlette.exceptions import HTTPException as StarletteHTTPException

log = structlog.get_logger(__name__)


class ErrorDetail(BaseModel):
    field: str | None = None
    message: str


class ErrorInfo(BaseModel):
    code: str
    message: str
    details: list[ErrorDetail] = []


class ErrorResponse(BaseModel):
    """The one error shape used by every non-2xx response and WebSocket error event."""

    error: ErrorInfo
    request_id: str | None


class AppError(Exception):
    """Base for expected errors; subclasses set the status, code and default message."""

    status_code: int = HTTPStatus.BAD_REQUEST
    code: str = "bad_request"
    message: str = "The request could not be processed."

    def __init__(
        self,
        message: str | None = None,
        *,
        details: list[ErrorDetail] | None = None,
        headers: Mapping[str, str] | None = None,
    ) -> None:
        self.message = message or self.message
        self.details = details or []
        self.headers = dict(headers or {})
        super().__init__(self.message)


class CsrfFailed(AppError):
    status_code = HTTPStatus.FORBIDDEN
    code = "csrf_failed"
    message = "Request origin is not allowed."


_HTTP_CODES = {
    HTTPStatus.BAD_REQUEST: "bad_request",
    HTTPStatus.UNAUTHORIZED: "unauthorized",
    HTTPStatus.FORBIDDEN: "forbidden",
    HTTPStatus.NOT_FOUND: "not_found",
    HTTPStatus.METHOD_NOT_ALLOWED: "method_not_allowed",
    HTTPStatus.REQUEST_ENTITY_TOO_LARGE: "payload_too_large",
    HTTPStatus.UNSUPPORTED_MEDIA_TYPE: "unsupported_media_type",
    HTTPStatus.TOO_MANY_REQUESTS: "rate_limited",
}


def request_id_of(request: Request) -> str | None:
    request_id = getattr(request.state, "request_id", None)
    return request_id if isinstance(request_id, str) else None


def error_response(
    status_code: int,
    code: str,
    message: str,
    *,
    request_id: str | None,
    details: list[ErrorDetail] | None = None,
    headers: Mapping[str, str] | None = None,
) -> JSONResponse:
    body = ErrorResponse(
        error=ErrorInfo(code=code, message=message, details=details or []),
        request_id=request_id,
    )
    return JSONResponse(body.model_dump(), status_code=status_code, headers=headers)


async def _app_error(request: Request, exc: Exception) -> JSONResponse:
    assert isinstance(exc, AppError)
    return error_response(
        exc.status_code,
        exc.code,
        exc.message,
        request_id=request_id_of(request),
        details=exc.details,
        headers=exc.headers,
    )


async def _validation_error(request: Request, exc: Exception) -> JSONResponse:
    assert isinstance(exc, RequestValidationError)
    details = [
        # loc starts with the request part ("body", "query", …); the rest is the field path.
        ErrorDetail(
            field=".".join(str(part) for part in error["loc"][1:]) or None, message=error["msg"]
        )
        for error in exc.errors()
    ]
    return error_response(
        HTTPStatus.UNPROCESSABLE_ENTITY,
        "validation_error",
        "Some fields are invalid.",
        request_id=request_id_of(request),
        details=details,
    )


async def _http_error(request: Request, exc: Exception) -> JSONResponse:
    assert isinstance(exc, StarletteHTTPException)
    status = HTTPStatus(exc.status_code)
    message = exc.detail if isinstance(exc.detail, str) else status.phrase
    return error_response(
        exc.status_code,
        _HTTP_CODES.get(status, "http_error"),
        message,
        request_id=request_id_of(request),
        headers=exc.headers,
    )


async def _unhandled_error(request: Request, exc: Exception) -> JSONResponse:
    request_id = request_id_of(request)
    log.exception("request.failed", error_type=type(exc).__name__)
    # Internal details stay in the logs; the client only gets the request id to report.
    return error_response(
        HTTPStatus.INTERNAL_SERVER_ERROR,
        "internal_error",
        "Something went wrong.",
        request_id=request_id,
        headers={"X-Request-ID": request_id} if request_id else None,
    )


def register_error_handlers(app: FastAPI) -> None:
    app.add_exception_handler(AppError, _app_error)
    app.add_exception_handler(RequestValidationError, _validation_error)
    app.add_exception_handler(StarletteHTTPException, _http_error)
    app.add_exception_handler(Exception, _unhandled_error)
