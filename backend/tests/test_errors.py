from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.core.errors import ConflictError, NotFoundError


def _add_test_routes(app: FastAPI) -> None:
    @app.get("/test/not-found")
    async def not_found() -> None:
        raise NotFoundError()

    @app.get("/test/conflict")
    async def conflict() -> None:
        raise ConflictError("Cannot do that.", code="TEST_CONFLICT", details={"x": 1})

    @app.get("/test/crash")
    async def crash() -> None:
        raise RuntimeError("boom")

    @app.get("/test/items/{item_id}")
    async def item(item_id: int) -> dict[str, int]:
        return {"item_id": item_id}


def _assert_error_shape(body: dict, code: str) -> None:
    error = body["error"]
    assert error["code"] == code
    assert isinstance(error["message"], str)
    assert isinstance(error["details"], dict)
    assert error["request_id"]


def test_unknown_route_uses_standard_error(client: TestClient) -> None:
    response = client.get("/api/v1/does-not-exist")

    assert response.status_code == 404
    _assert_error_shape(response.json(), "NOT_FOUND")


def test_app_error_maps_to_status_and_code(app: FastAPI, client: TestClient) -> None:
    _add_test_routes(app)

    assert client.get("/test/not-found").status_code == 404

    response = client.get("/test/conflict")
    assert response.status_code == 409
    body = response.json()
    _assert_error_shape(body, "TEST_CONFLICT")
    assert body["error"]["details"] == {"x": 1}


def test_validation_error_lists_fields(app: FastAPI, client: TestClient) -> None:
    _add_test_routes(app)

    response = client.get("/test/items/not-a-number")

    assert response.status_code == 422
    body = response.json()
    _assert_error_shape(body, "VALIDATION_ERROR")
    assert body["error"]["details"]["fields"][0]["loc"] == ["path", "item_id"]


def test_unhandled_error_hides_internals(app: FastAPI, client: TestClient) -> None:
    _add_test_routes(app)

    response = client.get("/test/crash")

    assert response.status_code == 500
    body = response.json()
    _assert_error_shape(body, "INTERNAL_ERROR")
    assert "boom" not in response.text
    assert response.headers["X-Request-ID"] == body["error"]["request_id"]
