import hashlib
import secrets
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

import jwt
from fastapi import Response
from pwdlib import PasswordHash

ACCESS_COOKIE = "pt_access"
REFRESH_COOKIE = "pt_refresh"
REFRESH_COOKIE_PATH = "/api/auth"
_ALGORITHM = "HS256"

# argon2id with the library's recommended parameters.
_password_hash = PasswordHash.recommended()
# Verified when a username does not exist, so both failure cases take the same time.
_DUMMY_HASH = _password_hash.hash("timing-equaliser")


def hash_password(password: str) -> str:
    return _password_hash.hash(password)


def verify_password(password: str, password_hash: str | None) -> bool:
    if password_hash is None:
        _password_hash.verify(password, _DUMMY_HASH)
        return False
    return _password_hash.verify(password, password_hash)


@dataclass(frozen=True)
class AccessClaims:
    user_id: uuid.UUID
    session_id: uuid.UUID
    expires_at: datetime


class InvalidAccessToken(Exception):
    pass


def create_access_token(
    user_id: uuid.UUID, session_id: uuid.UUID, *, secret: str, ttl: timedelta, now: datetime
) -> tuple[str, datetime]:
    expires_at = now + ttl
    claims = {"sub": str(user_id), "sid": str(session_id), "iat": now, "exp": expires_at}
    return jwt.encode(claims, secret, algorithm=_ALGORITHM), expires_at


def decode_access_token(token: str, *, secret: str) -> AccessClaims:
    """Checks signature and expiry; raises InvalidAccessToken for anything unusable."""
    try:
        claims = jwt.decode(
            token, secret, algorithms=[_ALGORITHM], options={"require": ["sub", "sid", "exp"]}
        )
        return AccessClaims(
            user_id=uuid.UUID(claims["sub"]),
            session_id=uuid.UUID(claims["sid"]),
            expires_at=datetime.fromtimestamp(claims["exp"], tz=UTC),
        )
    except (jwt.PyJWTError, ValueError, KeyError) as exc:
        raise InvalidAccessToken from exc


def new_refresh_token() -> str:
    return secrets.token_urlsafe(32)


def hash_refresh_token(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def set_auth_cookies(
    response: Response,
    *,
    access_token: str,
    access_expires_at: datetime,
    refresh_token: str,
    refresh_expires_at: datetime,
    secure: bool,
) -> None:
    # httpOnly: never readable by JavaScript. SameSite=Strict: never sent by other sites.
    response.set_cookie(
        ACCESS_COOKIE,
        access_token,
        expires=access_expires_at,
        path="/",
        secure=secure,
        httponly=True,
        samesite="strict",
    )
    # The refresh token only travels to the auth endpoints that use it.
    response.set_cookie(
        REFRESH_COOKIE,
        refresh_token,
        expires=refresh_expires_at,
        path=REFRESH_COOKIE_PATH,
        secure=secure,
        httponly=True,
        samesite="strict",
    )


def clear_auth_cookies(response: Response, *, secure: bool) -> None:
    response.delete_cookie(ACCESS_COOKIE, path="/", secure=secure, httponly=True, samesite="strict")
    response.delete_cookie(
        REFRESH_COOKIE, path=REFRESH_COOKIE_PATH, secure=secure, httponly=True, samesite="strict"
    )
