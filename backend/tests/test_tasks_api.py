"""Tasks, notifications, file downloads and Admin › System over HTTP."""

import asyncio
import uuid
from datetime import UTC, datetime
from pathlib import Path

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.core.config import Settings
from app.core.security import FileTokenClaims, create_file_token
from app.db.session import create_engine, create_session_factory
from app.workers.runner import run_task
from tests.fakes import FAKE_PDF, FakeGotenberg, fake_services
from tests.helpers import db, make_user


def _run_worker(app: FastAPI, settings: Settings, task_id: str, tmp_path: Path) -> None:
    """Run the queued task the way the worker would, sharing the app's storage."""

    async def go() -> None:
        engine = create_engine(settings)
        services = fake_services(settings, tmp_path, storage=app.state.storage)
        await run_task(
            uuid.UUID(task_id),
            settings,
            services=services,
            session_factory=create_session_factory(engine),
        )
        await engine.dispose()

    asyncio.run(go())


# ---------- tasks ----------


def test_test_pdf_is_queued_and_dispatched(
    app: FastAPI, client: TestClient, migrated_database: str
) -> None:
    _, user = make_user(client, migrated_database, "a@example.com")

    response = client.post("/api/v1/tasks/test-pdf", headers=user)

    assert response.status_code == 202
    task_id = response.json()["task_id"]
    task = client.get(f"/api/v1/tasks/{task_id}", headers=user).json()
    assert task["status"] == "queued"
    assert task["type"] == "test_pdf"
    assert app.state.dispatcher.sent == [(uuid.UUID(task_id), "test_pdf")]


def test_finished_task_offers_a_working_download_link(
    app: FastAPI, client: TestClient, migrated_database: str, settings: Settings, tmp_path: Path
) -> None:
    _, user = make_user(client, migrated_database, "a@example.com")
    task_id = client.post("/api/v1/tasks/test-pdf", headers=user).json()["task_id"]

    _run_worker(app, settings, task_id, tmp_path)
    task = client.get(f"/api/v1/tasks/{task_id}", headers=user).json()

    assert task["status"] == "succeeded"
    assert task["progress"] == 100
    file_info = task["result"]["file"]
    assert "key" not in file_info  # storage keys are never exposed
    download = client.get(file_info["download_url"])
    assert download.status_code == 200
    assert download.content == FAKE_PDF
    assert download.headers["content-type"] == "application/pdf"


def test_tasks_are_private(client: TestClient, migrated_database: str) -> None:
    _, alice = make_user(client, migrated_database, "alice@example.com")
    _, bob = make_user(client, migrated_database, "bob@example.com")
    task_id = client.post("/api/v1/tasks/test-pdf", headers=alice).json()["task_id"]

    assert client.get(f"/api/v1/tasks/{task_id}", headers=bob).status_code == 404
    assert client.get("/api/v1/tasks", headers=bob).json()["total"] == 0
    assert client.get("/api/v1/tasks", headers=alice).json()["total"] == 1


def test_pending_accounts_cannot_start_tasks(client: TestClient, migrated_database: str) -> None:
    _, pending = make_user(client, migrated_database, "p@example.com", approval="pending")

    assert client.post("/api/v1/tasks/test-pdf", headers=pending).status_code == 403


# ---------- file links ----------


def test_invalid_or_expired_file_links_are_404(client: TestClient, settings: Settings) -> None:
    claims = FileTokenClaims(uuid.uuid4(), "users/x/file.pdf", "file.pdf", "application/pdf")
    expired = create_file_token(claims, settings.secret_key, minutes=-1)

    assert client.get("/api/v1/files/not-a-token").status_code == 404
    assert client.get(f"/api/v1/files/{expired}").status_code == 404


# ---------- notifications ----------


def _add_notification(url: str, user_id: str, title: str, read: bool = False) -> None:
    db(
        url,
        "INSERT INTO notifications (user_id, type, title, severity, read_at) "
        "VALUES (:u, 'test', :t, 'info', :r)",
        u=user_id,
        t=title,
        r=datetime.now(UTC) if read else None,
    )


def test_notifications_list_count_and_mark_read(client: TestClient, migrated_database: str) -> None:
    user_id, user = make_user(client, migrated_database, "a@example.com")
    _add_notification(migrated_database, user_id, "First")
    _add_notification(migrated_database, user_id, "Second")
    _add_notification(migrated_database, user_id, "Old", read=True)

    assert client.get("/api/v1/notifications/unread-count", headers=user).json() == {"unread": 2}
    unread = client.get("/api/v1/notifications?unread_only=true", headers=user).json()
    assert unread["total"] == 2

    first_id = unread["items"][0]["id"]
    marked = client.post(f"/api/v1/notifications/{first_id}/read", headers=user).json()
    assert marked["read_at"] is not None
    assert client.get("/api/v1/notifications/unread-count", headers=user).json() == {"unread": 1}

    assert client.post("/api/v1/notifications/read-all", headers=user).status_code == 204
    assert client.get("/api/v1/notifications/unread-count", headers=user).json() == {"unread": 0}


def test_notifications_are_private(client: TestClient, migrated_database: str) -> None:
    alice_id, _ = make_user(client, migrated_database, "alice@example.com")
    _, bob = make_user(client, migrated_database, "bob@example.com")
    _add_notification(migrated_database, alice_id, "Alice only")
    (alice_note,) = db(migrated_database, "SELECT id FROM notifications")[0]

    assert client.get("/api/v1/notifications", headers=bob).json()["total"] == 0
    assert client.post(f"/api/v1/notifications/{alice_note}/read", headers=bob).status_code == 404


# ---------- admin › system ----------


def test_admin_system_reports_every_service(
    app: FastAPI, client: TestClient, migrated_database: str
) -> None:
    app.state.gotenberg = FakeGotenberg()
    _, admin = make_user(client, migrated_database, "admin@example.com", role="admin")

    body = client.get("/api/v1/admin/system", headers=admin).json()

    services = body["services"]
    assert set(services) == {"api", "database", "redis", "worker", "storage", "gotenberg", "ai"}
    assert services["database"]["status"] == "ok"
    assert services["redis"]["status"] == "ok"
    assert services["storage"]["status"] == "ok"
    assert services["gotenberg"]["status"] == "ok"
    assert services["worker"]["status"] == "disabled"  # Celery off in tests
    assert services["ai"]["details"]["model"] == "test/model"
    assert body["status"] == "ok"
    assert body["tasks"]["queued"] == 0


def test_admin_system_marks_broken_services(
    app: FastAPI, client: TestClient, migrated_database: str
) -> None:
    app.state.gotenberg = FakeGotenberg(fail=True)
    _, admin = make_user(client, migrated_database, "admin@example.com", role="admin")

    body = client.get("/api/v1/admin/system", headers=admin).json()

    assert body["services"]["gotenberg"]["status"] == "error"
    assert body["status"] == "degraded"


def test_admin_diagnostic_tasks(app: FastAPI, client: TestClient, migrated_database: str) -> None:
    _, admin = make_user(client, migrated_database, "admin@example.com", role="admin")
    _, user = make_user(client, migrated_database, "user@example.com")

    failure = client.post("/api/v1/admin/system/test-failure", headers=admin)
    ai = client.post("/api/v1/admin/system/test-ai", headers=admin)

    assert failure.status_code == ai.status_code == 202
    assert [kind for _, kind in app.state.dispatcher.sent] == ["test_failure", "ai_test"]
    assert client.get("/api/v1/admin/system", headers=user).status_code == 403
    assert client.post("/api/v1/admin/system/test-ai", headers=user).status_code == 403
