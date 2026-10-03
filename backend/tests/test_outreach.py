"""Phase 12: Gmail, contacts (LinkedIn posts + manual), drafts, approval, safe sending."""

import asyncio
import email
import uuid
from datetime import UTC, datetime, timedelta
from email import policy
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, urlparse
from zoneinfo import ZoneInfo

import httpx
import pytest
import respx
from cryptography.fernet import Fernet
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.core.config import Settings
from app.db.session import create_engine, create_session_factory
from app.domain.contacts import Blocklist, excerpt, find_emails
from app.domain.outreach import (
    IDEMPOTENCY_HEADER,
    Attachment,
    SendingDisabledError,
    SendRules,
    build_message,
    idempotency_key,
    next_slot,
)
from app.integrations.apify import LinkedInPost, hiring_query, parse_post
from app.models.enums import EmailType
from app.services.contacts import verify_address
from app.services.outreach import dispatch_outbox
from app.services.tasks import RecordingDispatcher
from app.workers.runner import Outcome, run_task
from tests.fakes import FakeJobSource, chat_response, fake_services, make_job
from tests.helpers import db, make_user
from tests.test_analysis import JD, _resume
from tests.test_jobs import _search_and_run

API = "/api/v1"
AI_URL = "https://ai.test/v1/chat/completions"
OAUTH = "https://oauth.test"
GMAIL = "https://gmail.test"
SENT_URL = f"{GMAIL}/upload/gmail/v1/users/me/messages/send"
SEARCH_URL = f"{GMAIL}/gmail/v1/users/me/messages"

EMAIL_PARAGRAPHS = [
    "I am writing to apply for the React Native Developer 1 role at Company 1, which I found "
    "in the job posting. I have 4 years of experience building React Native apps.",
    "At Acme Apps I built a payments app used by 50000 customers and cut the crash rate by "
    "30% with better error handling. At Blue Labs I shipped 6 apps to the Play Store and "
    "App Store. I work every day with TypeScript, Redux, Jest and Firebase.",
    "My resume is attached. I would be glad to talk about how I can help your mobile team "
    "ship reliable releases.",
]


def paragraphs(n: int) -> list[str]:
    return [
        p.replace("Developer 1", f"Developer {n}").replace("Company 1", f"Company {n}")
        for p in EMAIL_PARAGRAPHS
    ]


class FakePosts:
    def __init__(self, posts: list[LinkedInPost]) -> None:
        self.posts = posts
        self.queries: list[str] = []

    async def search(self, query: str, *, max_posts: int, posted_limit: str) -> list[LinkedInPost]:
        self.queries.append(query)
        return list(self.posts)


class FakeDomains:
    def __init__(self, dead: set[str] | None = None) -> None:
        self.dead = dead or set()

    async def accepts_mail(self, domain: str) -> bool | None:
        return domain not in self.dead


def _post(n: int, text: str) -> LinkedInPost:
    return LinkedInPost(
        post_id=f"post-{n}",
        url=f"https://www.linkedin.com/posts/p{n}",
        text=text,
        author_name="Priya Sharma",
        author_headline="HR Manager at ABC Technologies",
        author_url=None,
        posted_at=None,
    )


HIRING = (
    "We are hiring! ABC Technologies is looking for a React Native Developer in Pune with 3+ "
    "years of experience in TypeScript, Redux and Firebase. You will build and ship our "
    "customer apps, write tests with Jest and work with designers on new features. "
    "Share your resume at priya.hr@gmail.com with the subject 'React Native'. #hiring"
)
SEEKER = "I am looking for a React Native role, open to work. Reach me at seeker@gmail.com #hiring"


# ---------- rules ----------


def test_find_emails_excerpt_and_blocklist() -> None:
    text = "Mail HR@Acme.com or careers@acme.com, not logo@2x.png nor noreply@acme.com. hr@acme.com"

    assert find_emails(text) == ["hr@acme.com", "careers@acme.com"]
    assert "careers@acme.com" in excerpt(text, "careers@acme.com")
    blocked = Blocklist(emails=frozenset({"hr@acme.com"}), domains=frozenset({"spam.io"}))
    assert blocked.blocks("HR@acme.com") and blocked.blocks("x@spam.io")
    assert not blocked.blocks("careers@acme.com")
    assert hiring_query('React "Native"') == '"Hiring" AND "React Native" AND "gmail.com"'
    assert parse_post({"content": "x", "linkedinUrl": "u", "author": None}) is not None
    assert parse_post({"content": "", "linkedinUrl": "u"}) is None


def test_greeting_skips_titles_and_abbreviations() -> None:
    from app.services.outreach import _first_name

    assert _first_name("Md Ehtesham") == "Ehtesham"  # seen live: "Dear Md,"
    assert _first_name("Dr. Priya Sharma") == "Priya"
    assert _first_name("Priya") == "Priya"
    assert _first_name("J") is None and _first_name(None) is None


def test_misspelt_free_mail_is_risky() -> None:
    async def check(address: str) -> str:
        return (await verify_address(address, FakeDomains())).value

    assert asyncio.run(check("hr@gamil.com")) == "risky"  # seen in a live post
    assert asyncio.run(check("hr@gmail.com")) == "valid"
    assert asyncio.run(check("hr@dead.example")) == "valid"  # FakeDomains: all alive here


def test_send_slots_keep_the_gap_and_the_daily_cap() -> None:
    tz = ZoneInfo("Asia/Kolkata")
    rules = SendRules(daily_cap=2, interval_seconds=90, window_start_hour=9, tz=tz)
    now = datetime(2026, 10, 3, 10, 0, tzinfo=tz)

    first = next_slot(now, [], rules)
    second = next_slot(now, [first], rules, jitter_seconds=10)
    third = next_slot(now, [first, second], rules)

    assert first == now
    assert second == now + timedelta(seconds=100)
    assert third.astimezone(tz) == datetime(2026, 10, 4, 9, 0, tzinfo=tz)  # cap: tomorrow 9:00
    with pytest.raises(SendingDisabledError):
        next_slot(now, [], SendRules(0, 90, 9, tz))


def test_message_has_ids_and_attachments() -> None:
    user_id, app_id = uuid.uuid4(), uuid.uuid4()
    key = idempotency_key(user_id, app_id, EmailType.APPLICATION)

    raw, message_id = build_message(
        from_address="asha@gmail.com",
        from_name="Asha Verma",
        to_address="hr@acme.com",
        subject="Application for React Native Developer – Asha Verma",
        body="Dear Priya,\n\nHello.",
        attachments=[Attachment("Asha Verma - Resume.pdf", "application/pdf", b"%PDF")],
        idempotency=key,
    )

    parsed = email.message_from_bytes(raw, policy=policy.default)
    assert key == idempotency_key(user_id, app_id, EmailType.APPLICATION)  # deterministic
    assert key != idempotency_key(user_id, app_id, EmailType.FOLLOW_UP_1)
    assert parsed["Message-ID"] == message_id and parsed[IDEMPOTENCY_HEADER] == key
    assert parsed["From"] == "Asha Verma <asha@gmail.com>"
    files = [part.get_filename() for part in parsed.iter_attachments()]
    assert files == ["Asha Verma - Resume.pdf"]


# ---------- helpers ----------


@pytest.fixture
def gmail_settings(settings: Settings) -> Settings:
    return settings.model_copy(
        update={
            "google_client_id": "client-id",
            "google_client_secret": "client-secret",
            "token_encryption_key": Fernet.generate_key().decode(),
            "google_oauth_url": OAUTH,
            "gmail_api_url": GMAIL,
            "send_jitter_seconds": 0,
        }
    )


def _work(
    app: FastAPI, settings: Settings, task_id: str, tmp_path: Path, **overrides: Any
) -> Outcome:
    async def go() -> Outcome:
        engine = create_engine(settings)
        services = fake_services(settings, tmp_path, storage=app.state.storage, **overrides)
        result = await run_task(
            uuid.UUID(task_id),
            settings,
            services=services,
            session_factory=create_session_factory(engine),
        )
        await engine.dispose()
        return result.outcome

    return asyncio.run(go())


def _pending_tasks(app: FastAPI, task_type: str) -> list[str]:
    dispatcher: RecordingDispatcher = app.state.dispatcher
    return [str(task_id) for task_id, kind in dispatcher.sent if kind == task_type]


def _connect_gmail(
    client: TestClient, headers: dict[str, str], address: str = "asha@gmail.com"
) -> str:
    started = client.post(f"{API}/integrations/gmail/connect", headers=headers).json()
    state = parse_qs(urlparse(started["auth_url"]).query)["state"][0]
    respx.post(f"{OAUTH}/token").mock(
        return_value=httpx.Response(
            200,
            json={
                "access_token": "access-1",
                "refresh_token": "refresh-1",
                "expires_in": 3600,
                "scope": "https://www.googleapis.com/auth/gmail.send "
                "https://www.googleapis.com/auth/gmail.readonly",
            },
        )
    )
    respx.get(f"{GMAIL}/gmail/v1/users/me/profile").mock(
        return_value=httpx.Response(200, json={"emailAddress": address})
    )
    done = client.get(
        f"{API}/integrations/gmail/callback",
        params={"code": "auth-code", "state": state},
        follow_redirects=False,
    )
    assert done.status_code == 302 and "gmail=connected" in done.headers["location"]
    return state


def _email_application(app, client, url, settings, tmp_path, headers, user_id, n=1):  # type: ignore[no-untyped-def]
    """A job, an approved manual contact, an email application (resume file in storage)."""
    run = _search_and_run(
        app, client, settings, tmp_path, headers, FakeJobSource([make_job(n, description=JD)])
    )
    job_id = run["jobs"][0]["id"]
    contact = client.post(
        f"{API}/contacts",
        json={"email": f"priya{n}@acme.com", "name": "Priya Sharma", "job_id": job_id},
        headers=headers,
    ).json()
    application = client.post(
        f"{API}/jobs/{job_id}/applications",
        json={"channel": "email", "contact_id": contact["id"]},
        headers=headers,
    ).json()
    return application, contact


def _draft(app, client, settings, tmp_path, headers, application_id):  # type: ignore[no-untyped-def]
    started = client.post(f"{API}/applications/{application_id}/email/draft", headers=headers)
    assert started.status_code == 202, started.text
    assert _work(app, settings, started.json()["task_id"], tmp_path) is Outcome.SUCCEEDED
    return client.get(f"{API}/applications/{application_id}/email", headers=headers).json()


def _setup(app, client, url, settings, tmp_path, email="a@example.com"):  # type: ignore[no-untyped-def]
    app.state.settings = settings
    app.state.domain_checker = FakeDomains({"dead.example"})
    user_id, headers = make_user(client, url, email)
    _resume(url, user_id)
    asyncio.run(app.state.storage.save("k", b"%PDF-1.4 resume", "application/pdf"))
    return user_id, headers


# ---------- Gmail connection ----------


@respx.mock
def test_connect_gmail_stores_encrypted_tokens_once(
    app: FastAPI,
    client: TestClient,
    migrated_database: str,
    gmail_settings: Settings,
    tmp_path: Path,
) -> None:
    _, user = _setup(app, client, migrated_database, gmail_settings, tmp_path)
    started = client.post(f"{API}/integrations/gmail/connect", headers=user).json()
    query = parse_qs(urlparse(started["auth_url"]).query)

    used_state = _connect_gmail(client, user)
    replay = client.get(
        f"{API}/integrations/gmail/callback",
        params={"code": "again", "state": used_state},
        follow_redirects=False,
    )
    status = client.get(f"{API}/integrations/gmail", headers=user).json()

    assert "gmail.send" in query["scope"][0] and query["access_type"] == ["offline"]
    assert "gmail=error" in replay.headers["location"]  # the state was already used
    assert status["connected"] and status["account_email"] == "asha@gmail.com"
    assert status["can_send"] and status["can_read"]
    ((access, refresh),) = db(
        migrated_database, "SELECT access_token_enc, refresh_token_enc FROM oauth_accounts"
    )
    assert b"access-1" not in bytes(access) and b"refresh-1" not in bytes(refresh)

    revoke = respx.post(f"{OAUTH}/revoke").mock(return_value=httpx.Response(200))
    assert client.delete(f"{API}/integrations/gmail", headers=user).status_code == 204
    assert revoke.called
    assert client.get(f"{API}/integrations/gmail", headers=user).json()["connected"] is False


@respx.mock
def test_connect_without_send_permission_is_refused(
    app: FastAPI,
    client: TestClient,
    migrated_database: str,
    gmail_settings: Settings,
    tmp_path: Path,
) -> None:
    _, user = _setup(app, client, migrated_database, gmail_settings, tmp_path)
    started = client.post(f"{API}/integrations/gmail/connect", headers=user).json()
    state = parse_qs(urlparse(started["auth_url"]).query)["state"][0]
    respx.post(f"{OAUTH}/token").mock(
        return_value=httpx.Response(
            200,
            json={"access_token": "a", "expires_in": 3600, "scope": "openid"},
        )
    )
    respx.post(f"{OAUTH}/revoke").mock(return_value=httpx.Response(200))

    done = client.get(
        f"{API}/integrations/gmail/callback",
        params={"code": "c", "state": state},
        follow_redirects=False,
    )

    assert "gmail=error" in done.headers["location"]
    assert db(migrated_database, "SELECT count(*) FROM oauth_accounts")[0][0] == 0


# ---------- contacts ----------


@respx.mock
def test_linkedin_posts_become_private_jobs_with_pending_contacts(
    app: FastAPI, client: TestClient, migrated_database: str, settings: Settings, tmp_path: Path
) -> None:
    _, user = _setup(app, client, migrated_database, settings, tmp_path)
    off = client.post(f"{API}/contacts/discover", json={"keyword": "React Native"}, headers=user)
    client.patch(f"{API}/users/me/settings", json={"linkedin_source_enabled": True}, headers=user)
    client.post(f"{API}/do-not-contact", json={"email": "blocked@gmail.com"}, headers=user)
    respx.post(AI_URL).side_effect = [
        chat_response(
            {
                "is_hiring": True,
                "job_title": "React Native Developer",
                "company": "ABC Technologies",
                "location": "Pune",
                "contact_name": "Priya",
            }
        ),
        chat_response(
            {"is_hiring": False, "job_title": "", "company": "", "location": "", "contact_name": ""}
        ),
        chat_response(
            {"is_hiring": True, "job_title": "", "company": "", "location": "", "contact_name": ""}
        ),
    ]
    posts = FakePosts(
        [
            _post(1, HIRING),
            _post(2, SEEKER),
            _post(3, "Hiring a mobile dev, write to blocked@gmail.com"),
            _post(4, "Hiring React Native devs, DM me"),  # no email: no AI call
        ]
    )

    task_id = client.post(
        f"{API}/contacts/discover", json={"keyword": "React Native", "max_posts": 20}, headers=user
    ).json()["task_id"]
    assert (
        _work(app, settings, task_id, tmp_path, post_source=posts, domain_checker=FakeDomains())
        is Outcome.SUCCEEDED
    )
    result = client.get(f"{API}/tasks/{task_id}", headers=user).json()["result"]
    contacts = client.get(f"{API}/contacts", headers=user).json()["items"]
    jobs = client.get(f"{API}/jobs", headers=user).json()["items"]

    assert off.status_code == 409 and off.json()["error"]["code"] == "LINKEDIN_DISABLED"
    assert posts.queries == ['"Hiring" AND "React Native" AND "gmail.com"']
    assert (result["posts"], result["without_email"], result["not_hiring"]) == (4, 1, 1)
    assert (result["new_contacts"], result["blocked"], result["jobs"]) == (1, 1, 2)
    (contact,) = contacts
    assert contact["email"] == "priya.hr@gmail.com" and contact["approval"] == "pending"
    assert contact["source"] == "linkedin_post" and contact["verification"] == "valid"
    assert "priya.hr@gmail.com" in contact["source_excerpt"]
    assert contact["source_url"] == "https://www.linkedin.com/posts/p1"
    assert contact["name"] == "Priya" and contact["job"]["company"] == "ABC Technologies"
    titles = sorted((j["title"], j["company"]) for j in jobs)
    assert titles == [
        ("React Native", "Company not stated"),
        ("React Native Developer", "ABC Technologies"),
    ]
    (visibility,) = db(
        migrated_database, "SELECT DISTINCT visibility FROM jobs WHERE source = 'linkedin_post'"
    )[0]
    assert visibility == "private"

    # Running it again adds nothing new (same posts, same addresses).
    respx.post(AI_URL).side_effect = [
        chat_response(
            {
                "is_hiring": True,
                "job_title": "React Native Developer",
                "company": "ABC Technologies",
                "location": "Pune",
                "contact_name": "Priya",
            }
        ),
        chat_response(
            {"is_hiring": False, "job_title": "", "company": "", "location": "", "contact_name": ""}
        ),
        chat_response(
            {"is_hiring": True, "job_title": "", "company": "", "location": "", "contact_name": ""}
        ),
    ]
    again = client.post(
        f"{API}/contacts/discover", json={"keyword": "React Native"}, headers=user
    ).json()
    _work(
        app, settings, again["task_id"], tmp_path, post_source=posts, domain_checker=FakeDomains()
    )
    assert client.get(f"{API}/contacts", headers=user).json()["total"] == 1
    assert (
        db(migrated_database, "SELECT count(*) FROM jobs WHERE source = 'linkedin_post'")[0][0] == 2
    )


def test_manual_contacts_verification_and_do_not_contact(
    app: FastAPI, client: TestClient, migrated_database: str, settings: Settings, tmp_path: Path
) -> None:
    _, user = _setup(app, client, migrated_database, settings, tmp_path)

    added = client.post(
        f"{API}/contacts", json={"email": " HR@Acme.com ", "name": "Ravi"}, headers=user
    )
    duplicate = client.post(f"{API}/contacts", json={"email": "hr@acme.com"}, headers=user)
    dead = client.post(f"{API}/contacts", json={"email": "x@dead.example"}, headers=user)
    bad = client.post(f"{API}/contacts", json={"email": "not-an-email"}, headers=user)
    client.post(
        f"{API}/do-not-contact", json={"domain": "@ACME.com", "reason": "Asked"}, headers=user
    )
    after_block = client.get(f"{API}/contacts", headers=user).json()["items"][0]
    approve = client.patch(
        f"{API}/contacts/{added.json()['id']}", json={"approval": "approved"}, headers=user
    )
    blocked_add = client.post(f"{API}/contacts", json={"email": "jobs@acme.com"}, headers=user)

    assert added.status_code == 201
    assert (added.json()["email"], added.json()["approval"], added.json()["source"]) == (
        "hr@acme.com",
        "approved",
        "user",
    )
    assert duplicate.json()["error"]["code"] == "CONTACT_EXISTS"
    assert dead.json()["error"]["code"] == "EMAIL_UNDELIVERABLE"
    assert bad.json()["error"]["code"] == "BAD_EMAIL"
    assert after_block["approval"] == "rejected" and after_block["blocked"] is True
    assert approve.json()["error"]["code"] == "DO_NOT_CONTACT"
    assert blocked_add.json()["error"]["code"] == "DO_NOT_CONTACT"
    entries = client.get(f"{API}/do-not-contact", headers=user).json()
    assert [(e["email"], e["domain"]) for e in entries] == [(None, "acme.com")]


# ---------- email flow ----------


@respx.mock
def test_draft_approve_send_once_and_mark_applied(
    app: FastAPI,
    client: TestClient,
    migrated_database: str,
    gmail_settings: Settings,
    tmp_path: Path,
) -> None:
    user_id, user = _setup(app, client, migrated_database, gmail_settings, tmp_path)
    _connect_gmail(client, user)
    application, contact = _email_application(
        app, client, migrated_database, gmail_settings, tmp_path, user, user_id
    )
    no_closing = [p.replace("My resume is attached. ", "") for p in EMAIL_PARAGRAPHS]
    respx.post(AI_URL).side_effect = [
        chat_response(
            {"subject": "Application", "paragraphs": no_closing}
        ),  # retried: no attachment
        chat_response(
            {
                "subject": "Application for React Native Developer 1 – Asha Verma",
                "paragraphs": EMAIL_PARAGRAPHS,
            }
        ),
    ]

    draft = _draft(app, client, gmail_settings, tmp_path, user, application["id"])
    detail = client.get(f"{API}/applications/{application['id']}", headers=user).json()

    assert draft["status"] == "draft" and draft["warnings"] == []
    assert draft["to_address"] == contact["email"] and draft["from_address"] == "asha@gmail.com"
    assert draft["body_text"].startswith("Dear Priya,")
    assert draft["body_text"].endswith("Best regards,\nAsha Verma\n+91 98765 43210")
    assert [a["file_name"] for a in draft["attachments"]] == ["Asha Verma - Resume.pdf"]
    assert detail["status"] == "waiting_for_approval" and detail["allowed_next"] == []
    assert detail["contact"]["email"] == contact["email"]

    edited = client.put(
        f"{API}/emails/{draft['id']}",
        json={"subject": "Application – React Native Developer 1"},
        headers=user,
    ).json()
    approved = client.post(f"{API}/emails/{draft['id']}/approve", headers=user).json()
    twice = client.post(f"{API}/emails/{draft['id']}/approve", headers=user).json()
    locked = client.put(f"{API}/emails/{draft['id']}", json={"subject": "x"}, headers=user)

    assert edited["subject"] == "Application – React Native Developer 1"
    assert approved["status"] == "queued" and approved["scheduled_for"] is not None
    assert twice["status"] == "queued"
    assert locked.json()["error"]["code"] == "EMAIL_LOCKED"
    sends = _pending_tasks(app, "email_send")
    assert len(sends) == 1  # approving twice queued one send

    route = respx.post(SENT_URL).mock(
        return_value=httpx.Response(200, json={"id": "msg-1", "threadId": "thread-1"})
    )
    assert _work(app, gmail_settings, sends[0], tmp_path) is Outcome.SUCCEEDED
    # A duplicate delivery / retry of the same email does nothing.
    db(migrated_database, "UPDATE tasks SET status = 'queued' WHERE id = :t", t=sends[0])
    _work(app, gmail_settings, sends[0], tmp_path)

    assert route.call_count == 1
    sent = email.message_from_bytes(route.calls[0].request.content, policy=policy.default)
    assert (
        sent["To"] == contact["email"]
        and sent["Subject"] == "Application – React Native Developer 1"
    )
    assert sent[IDEMPOTENCY_HEADER] == idempotency_key(
        uuid.UUID(user_id), uuid.UUID(application["id"]), EmailType.APPLICATION
    )
    assert [p.get_filename() for p in sent.iter_attachments()] == ["Asha Verma - Resume.pdf"]
    final = client.get(f"{API}/applications/{application['id']}/email", headers=user).json()
    detail = client.get(f"{API}/applications/{application['id']}", headers=user).json()
    assert final["status"] == "sent" and final["gmail_thread_id"] == "thread-1"
    assert detail["status"] == "applied" and detail["applied_at"] is not None
    assert [(h["to_status"], h["source"]) for h in detail["history"]] == [
        ("ready_to_apply", "user"),
        ("waiting_for_approval", "user"),
        ("approved", "user"),
        ("sending", "system"),
        ("applied", "system"),
    ]
    summary = client.get(f"{API}/outbox/summary", headers=user).json()
    assert summary["sent_today"] == 1 and summary["counts"]["sent"] == 1


@respx.mock
def test_send_is_blocked_by_do_not_contact_and_retry_goes_back_to_draft(
    app: FastAPI,
    client: TestClient,
    migrated_database: str,
    gmail_settings: Settings,
    tmp_path: Path,
) -> None:
    user_id, user = _setup(app, client, migrated_database, gmail_settings, tmp_path)
    _connect_gmail(client, user)
    application, contact = _email_application(
        app, client, migrated_database, gmail_settings, tmp_path, user, user_id
    )
    respx.post(AI_URL).mock(
        return_value=chat_response({"subject": "Application", "paragraphs": EMAIL_PARAGRAPHS})
    )
    draft = _draft(app, client, gmail_settings, tmp_path, user, application["id"])
    client.post(f"{API}/emails/{draft['id']}/approve", headers=user)
    # Blocked after approval: the pre-send check catches it.
    db(
        migrated_database,
        "INSERT INTO do_not_contact (user_id, email, source) VALUES (:u, :e, 'user')",
        u=user_id,
        e=contact["email"],
    )
    route = respx.post(SENT_URL)

    _work(app, gmail_settings, _pending_tasks(app, "email_send")[0], tmp_path)
    failed = client.get(f"{API}/applications/{application['id']}/email", headers=user).json()
    retried = client.post(f"{API}/emails/{draft['id']}/retry", headers=user).json()
    approve_again = client.post(f"{API}/emails/{draft['id']}/approve", headers=user)
    detail = client.get(f"{API}/applications/{application['id']}", headers=user).json()

    assert not route.called
    assert failed["status"] == "failed" and "do-not-contact" in failed["error"]
    assert retried["status"] == "draft"
    assert approve_again.json()["error"]["code"] == "DO_NOT_CONTACT"
    assert detail["status"] == "waiting_for_approval"


@respx.mock
def test_daily_cap_moves_the_next_email_to_tomorrow(
    app: FastAPI,
    client: TestClient,
    migrated_database: str,
    gmail_settings: Settings,
    tmp_path: Path,
) -> None:
    user_id, user = _setup(app, client, migrated_database, gmail_settings, tmp_path)
    client.patch(f"{API}/users/me/settings", json={"daily_send_cap": 1}, headers=user)
    _connect_gmail(client, user)
    first, _ = _email_application(
        app, client, migrated_database, gmail_settings, tmp_path, user, user_id, n=1
    )
    second, _ = _email_application(
        app, client, migrated_database, gmail_settings, tmp_path, user, user_id, n=2
    )
    respx.post(AI_URL).side_effect = [
        chat_response({"subject": "Application", "paragraphs": paragraphs(1)}),
        chat_response({"subject": "Application", "paragraphs": paragraphs(2)}),
    ]
    drafts = [_draft(app, client, gmail_settings, tmp_path, user, a["id"]) for a in (first, second)]

    batch = client.post(
        f"{API}/emails/approve-batch", json={"email_ids": [d["id"] for d in drafts]}, headers=user
    ).json()
    queued = client.get(f"{API}/outbox?status=queued", headers=user).json()["items"]

    assert len(batch["approved"]) == 2 and batch["errors"] == {}
    slots = sorted(datetime.fromisoformat(e["scheduled_for"]) for e in queued)
    assert slots[1] - slots[0] > timedelta(hours=1)  # cap 1/day: the second waits for tomorrow
    assert _pending_tasks(app, "email_send") and len(_pending_tasks(app, "email_send")) == 1


@respx.mock
def test_an_unanswered_send_is_reconciled_from_gmail(
    app: FastAPI,
    client: TestClient,
    migrated_database: str,
    gmail_settings: Settings,
    tmp_path: Path,
) -> None:
    user_id, user = _setup(app, client, migrated_database, gmail_settings, tmp_path)
    _connect_gmail(client, user)
    application, _ = _email_application(
        app, client, migrated_database, gmail_settings, tmp_path, user, user_id
    )
    respx.post(AI_URL).mock(
        return_value=chat_response({"subject": "Application", "paragraphs": EMAIL_PARAGRAPHS})
    )
    draft = _draft(app, client, gmail_settings, tmp_path, user, application["id"])
    client.post(f"{API}/emails/{draft['id']}/approve", headers=user)
    respx.post(SENT_URL).mock(side_effect=httpx.ReadTimeout("no answer"))

    _work(app, gmail_settings, _pending_tasks(app, "email_send")[0], tmp_path)
    stuck = client.get(f"{API}/applications/{application['id']}/email", headers=user).json()
    db(migrated_database, "UPDATE emails SET updated_at = now() - interval '10 minutes'")
    key = idempotency_key(uuid.UUID(user_id), uuid.UUID(application["id"]), EmailType.APPLICATION)
    search = respx.get(SEARCH_URL).mock(
        return_value=httpx.Response(
            200,
            json={
                "messages": [{"id": "other", "threadId": "t-1"}, {"id": "msg-9", "threadId": "t-9"}]
            },
        )
    )
    # Gmail rewrites the Message-ID (seen live) but keeps our header: match on that.
    respx.get(f"{SEARCH_URL}/other").mock(
        return_value=httpx.Response(
            200, json={"payload": {"headers": [{"name": IDEMPOTENCY_HEADER, "value": "x"}]}}
        )
    )
    respx.get(f"{SEARCH_URL}/msg-9").mock(
        return_value=httpx.Response(
            200, json={"payload": {"headers": [{"name": IDEMPOTENCY_HEADER, "value": key}]}}
        )
    )

    async def sweep() -> dict[str, int]:
        engine = create_engine(gmail_settings)
        async with create_session_factory(engine)() as session:
            result = await dispatch_outbox(
                session, gmail_settings, RecordingDispatcher(), app.state.storage, datetime.now(UTC)
            )
        await engine.dispose()
        return result

    result = asyncio.run(sweep())
    repaired = client.get(f"{API}/applications/{application['id']}/email", headers=user).json()

    assert stuck["status"] == "sending"
    assert search.calls[0].request.url.params["q"].startswith(f"in:sent to:{draft['to_address']}")
    assert result["reconciled"] == 1
    assert repaired["status"] == "sent" and repaired["gmail_thread_id"] == "t-9"
    assert (
        client.get(f"{API}/applications/{application['id']}", headers=user).json()["status"]
        == "applied"
    )


@respx.mock
def test_reject_then_draft_again_reuses_the_same_email(
    app: FastAPI,
    client: TestClient,
    migrated_database: str,
    gmail_settings: Settings,
    tmp_path: Path,
) -> None:
    user_id, user = _setup(app, client, migrated_database, gmail_settings, tmp_path)
    _connect_gmail(client, user)
    application, _ = _email_application(
        app, client, migrated_database, gmail_settings, tmp_path, user, user_id
    )
    respx.post(AI_URL).mock(
        return_value=chat_response({"subject": "Application", "paragraphs": EMAIL_PARAGRAPHS})
    )
    first = _draft(app, client, gmail_settings, tmp_path, user, application["id"])

    rejected = client.post(f"{API}/emails/{first['id']}/reject", headers=user).json()
    status_after_reject = client.get(
        f"{API}/applications/{application['id']}", headers=user
    ).json()["status"]
    second = _draft(app, client, gmail_settings, tmp_path, user, application["id"])

    assert rejected["status"] == "rejected" and status_after_reject == "rejected_by_user"
    assert second["id"] == first["id"] and second["status"] == "draft"
    assert db(migrated_database, "SELECT count(*) FROM emails")[0][0] == 1


def test_drafting_needs_gmail_an_email_channel_and_an_approved_contact(
    app: FastAPI,
    client: TestClient,
    migrated_database: str,
    gmail_settings: Settings,
    tmp_path: Path,
) -> None:
    user_id, user = _setup(app, client, migrated_database, gmail_settings, tmp_path)
    application, contact = _email_application(
        app, client, migrated_database, gmail_settings, tmp_path, user, user_id
    )

    no_gmail = client.post(f"{API}/applications/{application['id']}/email/draft", headers=user)
    client.patch(
        f"{API}/applications/{application['id']}", json={"channel": "portal"}, headers=user
    )
    portal = client.post(f"{API}/applications/{application['id']}/email/draft", headers=user)

    assert no_gmail.json()["error"]["code"] == "GMAIL_NOT_CONNECTED"
    assert portal.json()["error"]["code"] == "NOT_EMAIL_CHANNEL"


def test_contacts_and_emails_are_private(
    app: FastAPI, client: TestClient, migrated_database: str, settings: Settings, tmp_path: Path
) -> None:
    _, alice = _setup(app, client, migrated_database, settings, tmp_path)
    _, bob = make_user(client, migrated_database, "bob@example.com")
    contact = client.post(f"{API}/contacts", json={"email": "hr@acme.com"}, headers=alice).json()
    entry = client.post(f"{API}/do-not-contact", json={"domain": "spam.io"}, headers=alice).json()

    assert client.get(f"{API}/contacts", headers=bob).json()["total"] == 0
    assert (
        client.patch(f"{API}/contacts/{contact['id']}", json={"name": "x"}, headers=bob).status_code
        == 404
    )
    assert client.delete(f"{API}/contacts/{contact['id']}", headers=bob).status_code == 404
    assert client.get(f"{API}/do-not-contact", headers=bob).json() == []
    assert client.delete(f"{API}/do-not-contact/{entry['id']}", headers=bob).status_code == 404
    assert client.get(f"{API}/emails/{uuid.uuid4()}", headers=bob).status_code == 404
    assert client.get(f"{API}/outbox", headers=bob).json()["total"] == 0
    assert (
        client.post(f"{API}/contacts", json={"email": "hr@acme.com"}, headers=bob).status_code
        == 201
    )
