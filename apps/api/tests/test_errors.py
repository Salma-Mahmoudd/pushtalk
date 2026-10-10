import re

from httpx import AsyncClient


async def test_validation_error_has_field_details(client: AsyncClient) -> None:
    response = await client.post("/api/test/items", json={"name": "mic"})

    assert response.status_code == 422
    body = response.json()
    assert body["error"]["code"] == "validation_error"
    assert body["error"]["details"] == [{"field": "size", "message": "Field required"}]
    assert body["request_id"] == response.headers["X-Request-ID"]


async def test_app_error_uses_its_status_code_and_headers(client: AsyncClient) -> None:
    response = await client.get("/api/test/teapot")

    assert response.status_code == 418
    assert response.json()["error"] == {
        "code": "teapot",
        "message": "Short and stout.",
        "details": [],
    }
    assert response.headers["Retry-After"] == "5"


async def test_unknown_route_is_not_found(client: AsyncClient) -> None:
    response = await client.get("/api/nothing-here")

    assert response.status_code == 404
    assert response.json()["error"]["code"] == "not_found"


async def test_wrong_method_is_method_not_allowed(client: AsyncClient) -> None:
    response = await client.get("/api/test/items")

    assert response.status_code == 405
    assert response.json()["error"]["code"] == "method_not_allowed"


async def test_unhandled_error_hides_internals(client: AsyncClient) -> None:
    response = await client.get("/api/test/crash")

    assert response.status_code == 500
    body = response.json()
    assert body["error"] == {
        "code": "internal_error",
        "message": "Something went wrong.",
        "details": [],
    }
    assert "hunter2" not in response.text
    assert body["request_id"] == response.headers["X-Request-ID"]


async def test_valid_incoming_request_id_is_kept(client: AsyncClient) -> None:
    response = await client.get("/api/health", headers={"X-Request-ID": "trace-123"})

    assert response.headers["X-Request-ID"] == "trace-123"


async def test_invalid_incoming_request_id_is_replaced(client: AsyncClient) -> None:
    response = await client.get("/api/health", headers={"X-Request-ID": "bad id <script>"})

    assert re.fullmatch(r"[0-9a-f]{32}", response.headers["X-Request-ID"])
