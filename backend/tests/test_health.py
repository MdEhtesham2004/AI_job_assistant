from fastapi.testclient import TestClient


def test_health_returns_ok(client: TestClient) -> None:
    response = client.get("/api/v1/health")

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "ok"
    assert body["environment"] == "test"
    assert body["version"] == "0.1.0"
    assert body["checks"] == {"api": "ok"}
    assert "timestamp" in body


def test_every_response_has_request_id(client: TestClient) -> None:
    response = client.get("/api/v1/health")

    assert len(response.headers["X-Request-ID"]) == 32


def test_valid_incoming_request_id_is_echoed(client: TestClient) -> None:
    response = client.get("/api/v1/health", headers={"X-Request-ID": "abc-123"})

    assert response.headers["X-Request-ID"] == "abc-123"


def test_invalid_incoming_request_id_is_replaced(client: TestClient) -> None:
    response = client.get("/api/v1/health", headers={"X-Request-ID": "bad id <script>"})

    assert response.headers["X-Request-ID"] != "bad id <script>"


def test_openapi_docs_are_served_under_prefix(client: TestClient) -> None:
    assert client.get("/api/v1/docs").status_code == 200
    assert client.get("/api/v1/openapi.json").status_code == 200
