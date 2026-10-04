"""Phase 14: dashboard, notification centre, admin insights, export/delete, legacy import,
hardening."""

import asyncio
import io
import json
import zipfile
from pathlib import Path

from fastapi import FastAPI
from fastapi.testclient import TestClient
from starlette.applications import Starlette
from starlette.responses import PlainTextResponse
from starlette.routing import Route

from app.core.config import Settings
from app.core.hardening import ApiRateLimitMiddleware
from app.core.rate_limit import SlidingWindowRateLimiter
from app.main import create_app
from tests.fakes import FakeJobSource, make_job
from tests.helpers import PASSWORD, db, make_user
from tests.test_analysis import JD, _resume
from tests.test_jobs import _search_and_run
from tests.test_outreach import FakeDomains

API = "/api/v1"


def _setup(app, client, url, email="a@example.com", role="user"):  # type: ignore[no-untyped-def]
    app.state.domain_checker = FakeDomains()
    return make_user(client, url, email, role=role)


def _application(client, user, job_id, channel="portal"):  # type: ignore[no-untyped-def]
    return client.post(
        f"{API}/jobs/{job_id}/applications", json={"channel": channel}, headers=user
    ).json()


# ---------- dashboard ----------


def test_dashboard_numbers_match_the_applications(
    app: FastAPI, client: TestClient, migrated_database: str, settings: Settings, tmp_path: Path
) -> None:
    user_id, user = _setup(app, client, migrated_database)
    _resume(migrated_database, user_id)
    run = _search_and_run(
        app,
        client,
        settings,
        tmp_path,
        user,
        FakeJobSource([make_job(n, description=JD) for n in (1, 2, 3)]),
    )
    a, b, c = (_application(client, user, job["id"])["id"] for job in run["jobs"])
    for app_id in (a, b):
        client.post(f"{API}/applications/{app_id}/mark-applied", headers=user)
    client.post(f"{API}/applications/{a}/status", json={"to_status": "interview"}, headers=user)
    client.post(f"{API}/applications/{a}/status", json={"to_status": "offer"}, headers=user)

    data = client.get(f"{API}/dashboard", headers=user).json()
    counts = client.get(f"{API}/applications/counts", headers=user).json()["counts"]

    assert data["jobs_found"] == 3 and data["jobs_new_this_week"] == 3
    assert data["stages"] == {
        "to_do": 1,
        "outbox": 0,
        "applied": 1,
        "in_process": 0,
        "offer": 1,
        "closed": 0,
    }
    assert data["statuses"] == counts  # same numbers as the Applications page
    assert (data["applied_total"], data["responses"]) == (2, 1)
    assert data["response_rate"] == 0.5
    assert (data["interviews"], data["offers"]) == (1, 1)  # interview reached, then offer
    assert data["by_source"] == [{"key": "jsearch", "applied": 2, "responded": 1, "rate": 0.5}]
    assert data["by_resume"][0]["key"] == "master"
    assert data["activity"][0]["to_status"] == "offer"
    assert c


def test_dashboard_is_private(
    app: FastAPI, client: TestClient, migrated_database: str, settings: Settings, tmp_path: Path
) -> None:
    _, alice = _setup(app, client, migrated_database)
    _, bob = make_user(client, migrated_database, "bob@example.com")
    run = _search_and_run(
        app, client, settings, tmp_path, alice, FakeJobSource([make_job(1, description=JD)])
    )
    _application(client, alice, run["jobs"][0]["id"])

    mine = client.get(f"{API}/dashboard", headers=bob).json()

    assert mine["jobs_found"] == 0 and sum(mine["statuses"].values()) == 0
    assert mine["activity"] == []


# ---------- notification centre ----------


def test_notification_categories(client: TestClient, migrated_database: str) -> None:
    user_id, user = make_user(client, migrated_database, "a@example.com")
    for kind in ("email_sent", "reply_status", "task_failed", "contacts_found", "welcome"):
        db(
            migrated_database,
            "INSERT INTO notifications (user_id, type, title) VALUES (:u, :t, :t)",
            u=user_id,
            t=kind,
        )

    def titles(category: str) -> list[str]:
        items = client.get(f"{API}/notifications?category={category}", headers=user).json()["items"]
        return sorted(n["title"] for n in items)

    assert titles("email") == ["email_sent"]
    assert titles("replies") == ["reply_status"]
    assert titles("tasks") == ["task_failed"]
    assert titles("jobs") == ["contacts_found"]
    assert titles("other") == ["welcome"]
    assert client.get(f"{API}/notifications?category=nope", headers=user).status_code == 422


# ---------- admin ----------


def test_admin_audit_analytics_and_errors_are_admin_only(
    app: FastAPI, client: TestClient, migrated_database: str
) -> None:
    user_id, user = _setup(app, client, migrated_database)
    _, admin = _setup(app, client, migrated_database, "admin@example.com", role="admin")
    client.patch(f"{API}/admin/platform", json={"automation_fetch_enabled": True}, headers=admin)
    db(
        migrated_database,
        "INSERT INTO tasks (user_id, type, status, error)"
        " VALUES (:u, 'job_search', 'failed', 'boom')",
        u=user_id,
    )
    db(
        migrated_database,
        "INSERT INTO ai_calls (user_id, task_type, model, prompt_version, input_tokens,"
        " output_tokens, cost_usd, latency_ms, cached, success)"
        " VALUES (:u, 'job_analyze', 'm', 'v', 10, 5, 0.0125, 100, false, true)",
        u=user_id,
    )

    audit = client.get(f"{API}/admin/audit?action=platform.", headers=admin).json()
    analytics = client.get(f"{API}/admin/analytics", headers=admin).json()
    errors = client.get(f"{API}/admin/errors", headers=admin).json()

    assert [e["action"] for e in audit["items"]] == ["platform.automation_fetch"]
    assert audit["items"][0]["user_email"] == "admin@example.com"
    assert analytics["users_by_status"]["approved"] == 2
    assert analytics["ai_cost_by_feature"] == [
        {"feature": "job_analyze", "cost_usd": "0.012500", "calls": 1}
    ]
    assert [u["email"] for u in analytics["users"]][0] == "a@example.com"  # highest cost first
    assert [(e["type"], e["error"], e["user_email"]) for e in errors] == [
        ("job_search", "boom", "a@example.com")
    ]
    for path in ("/admin/audit", "/admin/analytics", "/admin/errors"):
        assert client.get(f"{API}{path}", headers=user).status_code == 403


# ---------- export / delete ----------


def test_export_my_data_is_a_zip_with_only_my_rows_and_files(
    app: FastAPI, client: TestClient, migrated_database: str, settings: Settings, tmp_path: Path
) -> None:
    user_id, user = _setup(app, client, migrated_database)
    _, bob = _setup(app, client, migrated_database, "bob@example.com")
    _resume(migrated_database, user_id)
    asyncio.run(
        app.state.storage.save(f"users/{user_id}/resumes/cv.pdf", b"%PDF", "application/pdf")
    )
    client.post(f"{API}/contacts", json={"email": "hr@acme.com"}, headers=user)
    client.post(f"{API}/contacts", json={"email": "bob-only@acme.com"}, headers=bob)

    response = client.get(f"{API}/users/me/export", headers=user)
    archive = zipfile.ZipFile(io.BytesIO(response.content))
    names = archive.namelist()
    contacts = json.loads(archive.read("data/contacts.json"))
    account = json.loads(archive.read("account.json"))

    assert response.headers["content-type"] == "application/zip"
    assert "files/resumes/cv.pdf" in names and "data/resume_versions.json" in names
    assert [c["email"] for c in contacts] == ["hr@acme.com"]  # not Bob's
    assert account["user"]["email"] == "a@example.com"
    assert "hashed_password" not in account["user"]


def test_delete_account_needs_password_and_email_and_removes_everything(
    app: FastAPI, client: TestClient, migrated_database: str
) -> None:
    user_id, user = _setup(app, client, migrated_database)
    asyncio.run(
        app.state.storage.save(f"users/{user_id}/resumes/cv.pdf", b"%PDF", "application/pdf")
    )
    client.post(f"{API}/contacts", json={"email": "hr@acme.com"}, headers=user)

    wrong_password = client.post(
        f"{API}/users/me/delete",
        json={"password": "nope", "confirm_email": "a@example.com"},
        headers=user,
    )
    wrong_email = client.post(
        f"{API}/users/me/delete",
        json={"password": PASSWORD, "confirm_email": "x@example.com"},
        headers=user,
    )
    deleted = client.post(
        f"{API}/users/me/delete",
        json={"password": PASSWORD, "confirm_email": "A@example.com"},
        headers=user,
    )

    assert wrong_password.json()["error"]["code"] == "WRONG_PASSWORD"
    assert wrong_email.json()["error"]["code"] == "CONFIRM_MISMATCH"
    assert deleted.status_code == 204
    assert db(migrated_database, "SELECT count(*) FROM users WHERE id = :u", u=user_id)[0][0] == 0
    assert db(migrated_database, "SELECT count(*) FROM contacts")[0][0] == 0
    assert asyncio.run(app.state.storage.list_prefix(f"users/{user_id}/")) == []
    (action,) = db(
        migrated_database, "SELECT action FROM audit_logs WHERE action = 'user.self_delete'"
    )[0]
    assert action == "user.self_delete"
    login = client.post(f"{API}/auth/login", json={"email": "a@example.com", "password": PASSWORD})
    assert login.status_code == 401


def test_the_only_admin_cannot_delete_their_account(
    app: FastAPI, client: TestClient, migrated_database: str
) -> None:
    _, admin = _setup(app, client, migrated_database, "admin@example.com", role="admin")

    response = client.post(
        f"{API}/users/me/delete",
        json={"password": PASSWORD, "confirm_email": "admin@example.com"},
        headers=admin,
    )

    assert response.json()["error"]["code"] == "LAST_ADMIN"


# ---------- legacy import ----------

JOB_SHEET = (
    "Search Date,Job Title,Company,Location,Best Fit Role,Apply Link,Match Score,"
    "Matching Skills,Missing Skills\r\n"
    "2026-09-20,React Native Developer,Acme,Pune,Mobile,https://acme.example/jobs/1,78,"
    '"React Native, Redux",GraphQL\r\n'
    "2026-09-21,,,,,,,,\r\n"
)
LEADS_SHEET = (
    "lead_id,found_at,keyword,email,author_name,author_headline,post_url,posted_at,job_title,"
    "company,location,experience,skills,jd_summary,post_text,status,email_subject,sent_at,error\r\n"
    "p1_hr@gmail.com,2026-09-30T10:00:00Z,React Native,hr@gmail.com,Priya,HR at ABC,"
    "https://www.linkedin.com/posts/p1,2026-09-29T09:00:00Z,React Native Developer,ABC,Remote,,,,"
    '"We are hiring a React Native developer. Send your CV to hr@gmail.com",SENT,Hi,'
    "2026-09-30T11:00:00Z,\r\n"
    "p2_bad,2026-09-30T10:00:00Z,React Native,not-an-email,X,,https://www.linkedin.com/posts/p2,,"
    "Dev,,,,,,text,NEW,,,\r\n"
)


def _upload(client, user, name, text):  # type: ignore[no-untyped-def]
    return client.post(
        f"{API}/imports/legacy",
        files={"file": (name, text.encode("utf-8"), "text/csv")},
        headers=user,
    )


def test_import_the_legacy_job_list(
    client: TestClient, app: FastAPI, migrated_database: str
) -> None:
    _, user = _setup(app, client, migrated_database)

    first = _upload(client, user, "jobs.csv", JOB_SHEET).json()
    again = _upload(client, user, "jobs.csv", JOB_SHEET).json()
    jobs = client.get(f"{API}/jobs?state=saved", headers=user).json()["items"]
    not_csv = _upload(client, user, "jobs.xlsx", JOB_SHEET)

    assert (first["kind"], first["rows"], first["jobs_created"], first["skipped_count"]) == (
        "jobs",
        2,
        1,
        1,
    )
    assert (again["jobs_created"], again["jobs_existing"]) == (0, 1)  # idempotent
    (job,) = jobs
    assert (job["title"], job["company"], job["location"]) == (
        "React Native Developer",
        "Acme",
        "Pune",
    )
    assert not_csv.status_code == 422


def test_import_legacy_leads_creates_pending_contacts_with_evidence(
    client: TestClient, app: FastAPI, migrated_database: str
) -> None:
    _, user = _setup(app, client, migrated_database)

    result = _upload(client, user, "leads.csv", LEADS_SHEET).json()
    (contact,) = client.get(f"{API}/contacts", headers=user).json()["items"]

    assert (result["kind"], result["jobs_created"], result["contacts_created"]) == ("leads", 1, 1)
    assert result["already_emailed"] == 1 and result["skipped_count"] == 1
    assert contact["email"] == "hr@gmail.com" and contact["approval"] == "pending"
    assert contact["source"] == "legacy_import"
    assert contact["source_excerpt"].startswith("Already emailed by the old system on 2026-09-30")
    assert contact["job"]["title"] == "React Native Developer"


# ---------- hardening ----------


def test_security_headers_and_body_limit(
    client: TestClient, app: FastAPI, migrated_database: str, settings: Settings
) -> None:
    health = client.get(f"{API}/health")
    docs = client.get(f"{API}/docs")
    small = create_app(settings.model_copy(update={"max_request_bytes": 100}))
    with TestClient(small, raise_server_exceptions=False) as tiny:
        too_big = tiny.post(
            f"{API}/auth/login", content=b"x" * 500, headers={"content-type": "application/json"}
        )

    assert health.headers["x-content-type-options"] == "nosniff"
    assert health.headers["x-frame-options"] == "DENY"
    assert "default-src 'none'" in health.headers["content-security-policy"]
    assert "content-security-policy" not in docs.headers  # Swagger needs its assets
    assert "strict-transport-security" not in health.headers  # only in production
    assert too_big.status_code == 413


def test_api_rate_limit_per_client() -> None:
    async def ok(_request):  # type: ignore[no-untyped-def]
        return PlainTextResponse("ok")

    inner = Starlette(routes=[Route("/", ok)])
    limited = ApiRateLimitMiddleware(inner, per_minute=3, limiter=SlidingWindowRateLimiter())
    with TestClient(limited) as c:
        codes = [c.get("/").status_code for _ in range(4)]
        other = c.get("/", headers={"x-real-ip": "203.0.113.9"}).status_code

    assert codes == [200, 200, 200, 429] and other == 200


def test_monitoring_test_error_is_admin_only(
    client: TestClient, app: FastAPI, migrated_database: str
) -> None:
    _, user = _setup(app, client, migrated_database)
    _, admin = _setup(app, client, migrated_database, "admin@example.com", role="admin")

    assert client.post(f"{API}/admin/system/test-error", headers=user).status_code == 403
    response = client.post(f"{API}/admin/system/test-error", headers=admin)
    assert response.status_code == 500 and response.json()["error"]["code"] == "INTERNAL_ERROR"


def test_cli_rejects_addresses_that_cannot_sign_in() -> None:
    from app.cli import _check_email

    assert _check_email("admin@local.test") is None  # reserved domain: sign-in rejects it
    assert _check_email("not-an-email") is None
    assert _check_email("Admin@Example.com") == "Admin@example.com"
