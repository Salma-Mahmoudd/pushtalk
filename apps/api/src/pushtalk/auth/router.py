from fastapi import APIRouter, FastAPI, Request, Response, status
from fastapi.responses import JSONResponse

from pushtalk.auth.deps import AuthServiceDep, CurrentUserDep
from pushtalk.auth.errors import RefreshInvalid
from pushtalk.auth.schemas import LoginIn, SessionOut, SignupIn, UserOut
from pushtalk.auth.service import ClientInfo, IssuedSession
from pushtalk.core.config import Settings
from pushtalk.core.deps import RateLimiterDep, SettingsDep
from pushtalk.core.errors import error_response, request_id_of
from pushtalk.core.security import REFRESH_COOKIE, clear_auth_cookies, set_auth_cookies
from pushtalk.infra.rate_limit import RateLimitRule

router = APIRouter(prefix="/api/auth", tags=["auth"])


def _client(request: Request) -> ClientInfo:
    user_agent = request.headers.get("user-agent")
    return ClientInfo(
        user_agent=user_agent[:255] if user_agent else None,
        ip=request.client.host if request.client else None,
    )


def _start_session(response: Response, issued: IssuedSession, settings: Settings) -> SessionOut:
    set_auth_cookies(
        response,
        access_token=issued.access_token,
        access_expires_at=issued.access_expires_at,
        refresh_token=issued.refresh_token,
        refresh_expires_at=issued.refresh_expires_at,
        secure=settings.cookie_secure,
    )
    return SessionOut(
        user=UserOut.model_validate(issued.user), access_expires_at=issued.access_expires_at
    )


@router.post("/signup", status_code=status.HTTP_201_CREATED)
async def signup(
    body: SignupIn,
    request: Request,
    response: Response,
    service: AuthServiceDep,
    limiter: RateLimiterDep,
    settings: SettingsDep,
) -> SessionOut:
    client = _client(request)
    rule = RateLimitRule.parse("signup_ip", settings.rate_limit_signup_ip)
    await limiter.hit(rule, client.ip or "unknown")
    return _start_session(response, await service.signup(body, client), settings)


@router.post("/login")
async def login(
    body: LoginIn,
    request: Request,
    response: Response,
    service: AuthServiceDep,
    limiter: RateLimiterDep,
    settings: SettingsDep,
) -> SessionOut:
    client = _client(request)
    # Per username stops guessing one account; per IP stops spraying many accounts.
    username_rule = RateLimitRule.parse("login_username", settings.rate_limit_login_username)
    ip_rule = RateLimitRule.parse("login_ip", settings.rate_limit_login_ip)
    await limiter.hit(username_rule, body.username.lower())
    await limiter.hit(ip_rule, client.ip or "unknown")
    return _start_session(response, await service.login(body, client), settings)


@router.post("/refresh")
async def refresh(
    request: Request, response: Response, service: AuthServiceDep, settings: SettingsDep
) -> SessionOut:
    raw_token = request.cookies.get(REFRESH_COOKIE)
    if raw_token is None:
        raise RefreshInvalid()
    return _start_session(response, await service.refresh(raw_token, _client(request)), settings)


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
async def logout(request: Request, service: AuthServiceDep, settings: SettingsDep) -> Response:
    await service.logout(request.cookies.get(REFRESH_COOKIE))
    response = Response(status_code=status.HTTP_204_NO_CONTENT)
    clear_auth_cookies(response, secure=settings.cookie_secure)
    return response


@router.get("/me")
async def me(current: CurrentUserDep) -> SessionOut:
    return SessionOut(
        user=UserOut.model_validate(current.user), access_expires_at=current.claims.expires_at
    )


async def _refresh_invalid(request: Request, exc: Exception) -> JSONResponse:
    """A failed refresh also clears both cookies, so the browser drops the dead session."""
    assert isinstance(exc, RefreshInvalid)
    response = error_response(
        exc.status_code, exc.code, exc.message, request_id=request_id_of(request)
    )
    settings: Settings = request.app.state.settings
    clear_auth_cookies(response, secure=settings.cookie_secure)
    return response


def register_auth_error_handlers(app: FastAPI) -> None:
    app.add_exception_handler(RefreshInvalid, _refresh_invalid)
