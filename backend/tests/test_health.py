from fastapi.testclient import TestClient

import app.models  # noqa: F401  (registers all tables)
from app.core.config import Settings
from app.db.base import Base
from app.main import create_app
from app.services.health import expected_migration_head


def test_health_reports_api_and_database(client: TestClient) -> None:
    response = client.get("/api/v1/health")

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "ok"
    assert body["environment"] == "test"
    assert body["version"] == "0.1.0"
    assert body["checks"]["api"] == {"status": "ok", "details": {}}

    database = body["checks"]["database"]
    assert database["status"] == "ok"
    assert database["details"]["revision"] == expected_migration_head()
    assert database["details"]["head"] == expected_migration_head()
    assert database["details"]["up_to_date"] is True
    assert database["details"]["tables"] == len(Base.metadata.tables)
    assert database["details"]["latency_ms"] >= 0


def test_health_is_degraded_when_database_is_unreachable(settings: Settings) -> None:
    broken = settings.model_copy(
        update={"database_url": "postgresql+asyncpg://app:secret-pw@127.0.0.1:1/nowhere_test"}
    )
    with TestClient(create_app(broken)) as client:
        response = client.get("/api/v1/health")

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "degraded"
    assert body["checks"]["database"] == {
        "status": "error",
        "details": {"error": "Database unreachable"},
    }
    assert "secret-pw" not in response.text


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
