import uuid
from datetime import UTC, datetime, timedelta
from typing import Any

import pytest
from fakeredis import FakeAsyncRedis
from fastapi import FastAPI
from httpx import AsyncClient

from pushtalk.core.config import Settings
from pushtalk.core.security import ACCESS_COOKIE, REFRESH_COOKIE, create_access_token

pytestmark = pytest.mark.integration

ALICE = {"username": "Alice", "password": "correct horse"}


async def _signup(client: AsyncClient, **overrides: str) -> dict[str, Any]:
    response = await client.post("/api/auth/signup", json={**ALICE, **overrides})
    assert response.status_code == 201, response.text
    body: dict[str, Any] = response.json()
    return body


def _set_cookie_headers(response_headers: list[str], name: str) -> list[str]:
    return [header for header in response_headers if header.startswith(f"{name}=")]


# --- signup -------------------------------------------------------------------------------


async def test_signup_sets_httponly_cookies_and_returns_user(db_client: AsyncClient) -> None:
    response = await db_client.post("/api/auth/signup", json=ALICE)

    assert response.status_code == 201
    body = response.json()
    assert body["user"]["username"] == "alice"  # stored lower-cased
    assert "access_expires_at" in body
    assert "token" not in response.text  # tokens never appear in the body
    cookies = response.headers.get_list("set-cookie")
    (access,) = _set_cookie_headers(cookies, ACCESS_COOKIE)
    (refresh,) = _set_cookie_headers(cookies, REFRESH_COOKIE)
    for cookie in (access, refresh):
        assert "HttpOnly" in cookie
        assert "SameSite=strict" in cookie
    assert "Path=/api/auth" in refresh


async def test_signup_duplicate_username_case_insensitive_409(db_client: AsyncClient) -> None:
    await _signup(db_client)

    response = await db_client.post("/api/auth/signup", json={**ALICE, "username": "ALICE"})

    assert response.status_code == 409
    assert response.json()["error"]["code"] == "username_taken"


async def test_signup_validation_errors_shape(db_client: AsyncClient) -> None:
    response = await db_client.post(
        "/api/auth/signup", json={"username": "a b", "password": "short"}
    )

    assert response.status_code == 422
    fields = {detail["field"] for detail in response.json()["error"]["details"]}
    assert fields == {"username", "password"}


# --- login --------------------------------------------------------------------------------


async def test_login_success(db_client: AsyncClient) -> None:
    await _signup(db_client)
    db_client.cookies.clear()

    response = await db_client.post("/api/auth/login", json={**ALICE, "username": "ALICE"})

    assert response.status_code == 200
    assert response.json()["user"]["username"] == "alice"
    assert db_client.cookies.get(ACCESS_COOKIE)


async def test_login_wrong_password_and_unknown_user_look_the_same(db_client: AsyncClient) -> None:
    await _signup(db_client)

    wrong_password = await db_client.post(
        "/api/auth/login", json={**ALICE, "password": "wrong password"}
    )
    unknown_user = await db_client.post(
        "/api/auth/login", json={"username": "nobody", "password": "whatever1"}
    )

    for response in (wrong_password, unknown_user):
        assert response.status_code == 401
        assert response.json()["error"]["code"] == "invalid_credentials"
    assert wrong_password.json()["error"]["message"] == unknown_user.json()["error"]["message"]


# --- protected routes -----------------------------------------------------------------------


async def test_me_returns_the_logged_in_user(db_client: AsyncClient) -> None:
    await _signup(db_client)

    response = await db_client.get("/api/auth/me")

    assert response.status_code == 200
    assert response.json()["user"]["username"] == "alice"


async def test_protected_route_requires_cookie(db_client: AsyncClient) -> None:
    response = await db_client.get("/api/auth/me")

    assert response.status_code == 401
    assert response.json()["error"]["code"] == "unauthorized"


async def test_protected_route_rejects_expired_token(
    db_client: AsyncClient, settings: Settings
) -> None:
    body = await _signup(db_client)
    user_id = uuid.UUID(body["user"]["id"])
    expired, _ = create_access_token(
        user_id,
        uuid.uuid4(),
        secret=settings.jwt_secret.get_secret_value(),
        ttl=timedelta(minutes=15),
        now=datetime.now(UTC) - timedelta(hours=1),
    )
    db_client.cookies.set(ACCESS_COOKIE, expired)

    response = await db_client.get("/api/auth/me")

    assert response.status_code == 401


async def test_protected_route_rejects_tampered_token(db_client: AsyncClient) -> None:
    await _signup(db_client)
    token = db_client.cookies[ACCESS_COOKIE]
    db_client.cookies.set(ACCESS_COOKIE, token[:-4] + ("AAAA" if token[-4:] != "AAAA" else "BBBB"))

    response = await db_client.get("/api/auth/me")

    assert response.status_code == 401


async def test_token_signed_with_another_secret_is_rejected(db_client: AsyncClient) -> None:
    body = await _signup(db_client)
    forged, _ = create_access_token(
        uuid.UUID(body["user"]["id"]),
        uuid.uuid4(),
        secret="another-secret-of-at-least-thirty-two-bytes",
        ttl=timedelta(minutes=15),
        now=datetime.now(UTC),
    )
    db_client.cookies.set(ACCESS_COOKIE, forged)

    response = await db_client.get("/api/auth/me")

    assert response.status_code == 401


# --- refresh rotation -------------------------------------------------------------------------


async def test_refresh_rotates_both_cookies(db_client: AsyncClient) -> None:
    await _signup(db_client)
    old_refresh = db_client.cookies[REFRESH_COOKIE]

    response = await db_client.post("/api/auth/refresh")

    assert response.status_code == 200
    assert db_client.cookies[REFRESH_COOKIE] != old_refresh
    assert (await db_client.get("/api/auth/me")).status_code == 200


async def test_refresh_without_cookie_is_refused(db_client: AsyncClient) -> None:
    response = await db_client.post("/api/auth/refresh")

    assert response.status_code == 401
    assert response.json()["error"]["code"] == "refresh_invalid"


async def test_refresh_reuse_within_grace_is_a_retry(db_client: AsyncClient) -> None:
    """A lost response followed by a retry with the same token keeps the session."""
    await _signup(db_client)
    old_refresh = db_client.cookies[REFRESH_COOKIE]
    await db_client.post("/api/auth/refresh")

    db_client.cookies.set(REFRESH_COOKIE, old_refresh, path="/api/auth")
    retry = await db_client.post("/api/auth/refresh")

    assert retry.status_code == 200
    assert (await db_client.get("/api/auth/me")).status_code == 200


async def test_refresh_reuse_after_grace_revokes_the_session(
    db_client: AsyncClient, db_app: FastAPI
) -> None:
    db_app.state.settings = db_app.state.settings.model_copy(update={"refresh_reuse_grace_s": 0})
    await _signup(db_client)
    stolen = db_client.cookies[REFRESH_COOKIE]
    await db_client.post("/api/auth/refresh")  # the legitimate owner rotates
    current = db_client.cookies[REFRESH_COOKIE]

    db_client.cookies.set(REFRESH_COOKIE, stolen, path="/api/auth")
    reuse = await db_client.post("/api/auth/refresh")

    assert reuse.status_code == 401
    assert reuse.json()["error"]["code"] == "refresh_invalid"
    # The whole session ends: the owner's current refresh token stops working too…
    db_client.cookies.set(REFRESH_COOKIE, current, path="/api/auth")
    assert (await db_client.post("/api/auth/refresh")).status_code == 401


async def test_failed_refresh_clears_both_cookies(db_client: AsyncClient) -> None:
    db_client.cookies.set(REFRESH_COOKIE, "made-up", path="/api/auth")

    response = await db_client.post("/api/auth/refresh")

    cleared = response.headers.get_list("set-cookie")
    assert _set_cookie_headers(cleared, ACCESS_COOKIE)
    assert _set_cookie_headers(cleared, REFRESH_COOKIE)
    assert all("Max-Age=0" in cookie for cookie in cleared)


# --- logout -------------------------------------------------------------------------------


async def test_logout_ends_the_session_immediately(db_client: AsyncClient) -> None:
    await _signup(db_client)
    access = db_client.cookies[ACCESS_COOKIE]
    refresh = db_client.cookies[REFRESH_COOKIE]

    response = await db_client.post("/api/auth/logout")

    assert response.status_code == 204
    # Even a copy of the still-unexpired access token is refused after logout.
    db_client.cookies.set(ACCESS_COOKIE, access)
    assert (await db_client.get("/api/auth/me")).status_code == 401
    db_client.cookies.set(REFRESH_COOKIE, refresh, path="/api/auth")
    assert (await db_client.post("/api/auth/refresh")).status_code == 401


# --- CSRF ---------------------------------------------------------------------------------


async def test_login_from_foreign_origin_is_refused(db_client: AsyncClient) -> None:
    response = await db_client.post(
        "/api/auth/login", json=ALICE, headers={"Origin": "https://evil.example"}
    )

    assert response.status_code == 403
    assert response.json()["error"]["code"] == "csrf_failed"


# --- rate limits --------------------------------------------------------------------------


async def test_login_rate_limited_per_username(db_client: AsyncClient, db_app: FastAPI) -> None:
    db_app.state.settings = db_app.state.settings.model_copy(
        update={"rate_limit_login_username": "3/900"}
    )
    for _ in range(3):
        await db_client.post("/api/auth/login", json={"username": "bob", "password": "nope1234"})

    response = await db_client.post(
        "/api/auth/login", json={"username": "BOB", "password": "nope1234"}
    )

    assert response.status_code == 429
    assert response.json()["error"]["code"] == "rate_limited"
    assert int(response.headers["Retry-After"]) > 0


async def test_login_rate_limit_per_ip_spans_usernames(
    db_client: AsyncClient, db_app: FastAPI
) -> None:
    db_app.state.settings = db_app.state.settings.model_copy(
        update={"rate_limit_login_ip": "3/900"}
    )
    for name in ("u1", "u2", "u3"):
        await db_client.post("/api/auth/login", json={"username": name, "password": "nope1234"})

    response = await db_client.post(
        "/api/auth/login", json={"username": "u4", "password": "nope1234"}
    )

    assert response.status_code == 429


async def test_signup_rate_limited_per_ip(db_client: AsyncClient, db_app: FastAPI) -> None:
    db_app.state.settings = db_app.state.settings.model_copy(
        update={"rate_limit_signup_ip": "2/3600"}
    )
    await _signup(db_client, username="first")
    await _signup(db_client, username="second")

    response = await db_client.post("/api/auth/signup", json={**ALICE, "username": "third"})

    assert response.status_code == 429


async def test_revoked_session_marker_expires_with_access_tokens(
    db_client: AsyncClient, fake_redis: FakeAsyncRedis, settings: Settings
) -> None:
    await _signup(db_client)
    await db_client.post("/api/auth/logout")

    keys = await fake_redis.keys("session:revoked:*")
    assert len(keys) == 1
    assert 0 < await fake_redis.ttl(keys[0]) <= settings.access_token_ttl_min * 60
