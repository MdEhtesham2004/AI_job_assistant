"""Phase 13: reply tracking, bounces, confirmations, follow-ups, no-response, automation."""

import asyncio
import base64
import email
import uuid
from datetime import UTC, datetime
from email import policy
from pathlib import Path
from typing import Any

import httpx
import respx
from fakeredis.aioredis import FakeRedis
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.core.config import Settings
from app.db.session import create_engine, create_session_factory
from app.domain.outreach import asks_not_to_be_contacted, is_bounce, reply_subject
from app.integrations.ai import AiClient
from app.integrations.gmail import parse_message
from app.services.replies import PollResult, ReplyTracker
from app.workers.runner import Outcome
from tests.fakes import FakeJobSource, chat_response, make_job
from tests.helpers import db, make_user
from tests.test_analysis import JD, MATCH
from tests.test_jobs import _search_and_run
from tests.test_outreach import (
    AI_URL,
    API,
    EMAIL_PARAGRAPHS,
    GMAIL,
    HIRING,
    SENT_URL,
    FakeDomains,
    FakePosts,
    _connect_gmail,
    _draft,
    _email_application,
    _pending_tasks,
    _post,
    _setup,
    _work,
)

MESSAGES = f"{GMAIL}/gmail/v1/users/me/messages"
THREADS = f"{GMAIL}/gmail/v1/users/me/threads"
HISTORY = f"{GMAIL}/gmail/v1/users/me/history"
RECRUITER = "priya1@acme.com"


def _b64(text: str) -> str:
    return base64.urlsafe_b64encode(text.encode()).decode().rstrip("=")


def gmail_message(
    message_id: str,
    *,
    sender: str = f"Priya Sharma <{RECRUITER}>",
    to: str = "asha@gmail.com",
    subject: str = "Re: Application",
    text: str = "Thanks!",
    thread: str = "thread-1",
    html: bool = False,
) -> dict[str, Any]:
    part = {"mimeType": "text/html" if html else "text/plain", "body": {"data": _b64(text)}}
    return {
        "id": message_id,
        "threadId": thread,
        "labelIds": ["INBOX", "UNREAD"],
        "internalDate": str(int(datetime.now(UTC).timestamp() * 1000)),
        "payload": {
            "mimeType": "multipart/alternative",
            "headers": [
                {"name": "From", "value": sender},
                {"name": "To", "value": to},
                {"name": "Subject", "value": subject},
                {"name": "Message-Id", "value": f"<{message_id}@mail.gmail.com>"},
            ],
            "parts": [part],
        },
    }


# ---------- rules ----------


def test_bounce_no_contact_and_message_parsing() -> None:
    assert is_bounce("mailer-daemon@googlemail.com", "Delivery Status Notification (Failure)")
    assert is_bounce("postmaster@acme.com", "anything")
    assert not is_bounce("priya@acme.com", "Re: Application")
    assert asks_not_to_be_contacted("Please stop emailing me.")
    assert asks_not_to_be_contacted("Do not contact me again")
    assert not asks_not_to_be_contacted("Please contact me on Monday")
    assert reply_subject("Application") == "Re: Application"
    assert reply_subject("RE: Application") == "RE: Application"
    parsed = parse_message(gmail_message("m1", text="<p>Hello <b>there</b></p><br>Bye", html=True))
    assert parsed.from_address == RECRUITER and parsed.from_name == "Priya Sharma"
    assert "Hello" in parsed.text and "<b>" not in parsed.text and "Bye" in parsed.text
    assert parsed.rfc822_message_id == "<m1@mail.gmail.com>"


# ---------- helpers ----------


def _poll(app: FastAPI, settings: Settings, user_id: str) -> PollResult:
    async def go() -> PollResult:
        engine = create_engine(settings)
        async with create_session_factory(engine)() as session:
            result = await ReplyTracker(
                session, uuid.UUID(user_id), settings, AiClient(settings, FakeRedis())
            ).poll()
        await engine.dispose()
        return result

    return asyncio.run(go())


def _sent_application(app, client, url, settings, tmp_path):  # type: ignore[no-untyped-def]
    """Gmail connected, one email application sent (Gmail ids msg-1 / thread-1)."""
    user_id, user = _setup(app, client, url, settings, tmp_path)
    _connect_gmail(client, user)
    application, contact = _email_application(app, client, url, settings, tmp_path, user, user_id)
    respx.post(AI_URL).mock(
        return_value=chat_response({"subject": "Application", "paragraphs": EMAIL_PARAGRAPHS})
    )
    draft = _draft(app, client, settings, tmp_path, user, application["id"])
    client.post(f"{API}/emails/{draft['id']}/approve", headers=user)
    respx.post(SENT_URL).mock(
        return_value=httpx.Response(200, json={"id": "msg-1", "threadId": "thread-1"})
    )
    # After sending we read the Message-ID Gmail really used.
    respx.get(f"{MESSAGES}/msg-1").mock(
        return_value=httpx.Response(
            200,
            json={
                "payload": {"headers": [{"name": "Message-Id", "value": "<real-1@mail.gmail.com>"}]}
            },
        )
    )
    assert _work(app, settings, _pending_tasks(app, "email_send")[0], tmp_path) is Outcome.SUCCEEDED
    return user_id, user, application, contact, draft


def _reply_in_thread(message: dict[str, Any]) -> None:
    """First poll (no history id yet): the tracked thread is read once."""
    respx.get(f"{THREADS}/thread-1").mock(
        return_value=httpx.Response(
            200,
            json={
                "messages": [
                    {"id": "msg-1", "threadId": "thread-1", "labelIds": ["SENT"]},
                    {"id": message["id"], "threadId": "thread-1", "labelIds": ["INBOX"]},
                ]
            },
        )
    )
    respx.get(f"{MESSAGES}/{message['id']}").mock(return_value=httpx.Response(200, json=message))


def _reading(
    category: str, confidence: float, action: str = "Reply with 2-3 time slots"
) -> httpx.Response:
    return chat_response(
        {
            "category": category,
            "confidence": confidence,
            "summary": "The recruiter asks for a call on Thursday.",
            "suggested_action": action,
        }
    )


# ---------- replies ----------


@respx.mock
def test_interview_invite_moves_the_application_and_is_shown_in_the_timeline(
    app: FastAPI,
    client: TestClient,
    migrated_database: str,
    gmail_settings: Settings,
    tmp_path: Path,
) -> None:
    user_id, user, application, _, _ = _sent_application(
        app, client, migrated_database, gmail_settings, tmp_path
    )
    _reply_in_thread(gmail_message("r-1", text="Can we schedule an interview on Thursday?"))
    respx.post(AI_URL).mock(return_value=_reading("interview_invite", 0.92))

    first = _poll(app, gmail_settings, user_id)
    respx.get(HISTORY).mock(
        return_value=httpx.Response(200, json={"historyId": "101", "history": []})
    )
    second = _poll(app, gmail_settings, user_id)

    detail = client.get(f"{API}/applications/{application['id']}", headers=user).json()
    replies = client.get(f"{API}/applications/{application['id']}/replies", headers=user).json()
    assert (first.replies, first.status_changes, second.replies) == (1, 1, 0)
    assert detail["status"] == "interview"
    assert detail["next_action"] == "Reply with 2-3 time slots"
    assert (detail["history"][-1]["source"], detail["history"][-1]["to_status"]) == (
        "email_reply",
        "interview",
    )
    (reply,) = replies
    assert reply["from_address"] == RECRUITER and "Thursday" in reply["body_text"]
    assert reply["classification"]["category"] == "interview_invite"
    assert reply["classification"]["applied_transition"] is True
    ((history_id,),) = db(migrated_database, "SELECT gmail_history_id FROM oauth_accounts")
    assert history_id == "101"


@respx.mock
def test_an_unsure_reading_asks_the_user_to_confirm(
    app: FastAPI,
    client: TestClient,
    migrated_database: str,
    gmail_settings: Settings,
    tmp_path: Path,
) -> None:
    user_id, user, application, _, _ = _sent_application(
        app, client, migrated_database, gmail_settings, tmp_path
    )
    _reply_in_thread(gmail_message("r-1", text="Hi, thanks. Let's talk at some point."))
    respx.post(AI_URL).mock(return_value=_reading("interview_invite", 0.55))

    result = _poll(app, gmail_settings, user_id)
    waiting = client.get(f"{API}/applications/{application['id']}", headers=user).json()
    (reply,) = client.get(f"{API}/applications/{application['id']}/replies", headers=user).json()
    confirmed = client.post(
        f"{API}/replies/{reply['classification']['id']}/confirm",
        json={"accept": True},
        headers=user,
    ).json()
    after = client.get(f"{API}/applications/{application['id']}", headers=user).json()
    notes = [n["title"] for n in client.get(f"{API}/notifications", headers=user).json()["items"]]

    assert result.to_confirm == 1 and waiting["status"] == "applied"
    assert reply["classification"]["user_confirmed"] is None
    assert confirmed["user_confirmed"] is True and confirmed["applied_transition"] is True
    assert after["status"] == "interview"
    assert any(title.startswith("Confirm: is this an interview invite?") for title in notes)


@respx.mock
def test_a_bounce_marks_the_contact_invalid_and_the_application_failed(
    app: FastAPI,
    client: TestClient,
    migrated_database: str,
    gmail_settings: Settings,
    tmp_path: Path,
) -> None:
    user_id, user, application, contact, draft = _sent_application(
        app, client, migrated_database, gmail_settings, tmp_path
    )
    _reply_in_thread(
        gmail_message(
            "b-1",
            sender="Mail Delivery Subsystem <mailer-daemon@googlemail.com>",
            subject="Delivery Status Notification (Failure)",
            text="Address not found",
        )
    )
    ai = respx.post(AI_URL)
    calls_before = ai.call_count  # the draft used the AI already

    result = _poll(app, gmail_settings, user_id)
    sent = client.get(f"{API}/applications/{application['id']}/email", headers=user).json()
    detail = client.get(f"{API}/applications/{application['id']}", headers=user).json()
    contacts = client.get(f"{API}/contacts", headers=user).json()["items"]

    assert result.bounces == 1 and ai.call_count == calls_before  # no AI for bounces
    assert sent["status"] == "bounced"
    assert detail["status"] == "failed"
    assert [c["verification"] for c in contacts if c["id"] == contact["id"]] == ["invalid"]


@respx.mock
def test_do_not_contact_reply_blocks_the_sender(
    app: FastAPI,
    client: TestClient,
    migrated_database: str,
    gmail_settings: Settings,
    tmp_path: Path,
) -> None:
    user_id, user, application, _, _ = _sent_application(
        app, client, migrated_database, gmail_settings, tmp_path
    )
    _reply_in_thread(gmail_message("r-1", text="Please stop emailing me. Not interested."))
    respx.post(AI_URL).mock(return_value=_reading("rejection", 0.9, ""))

    _poll(app, gmail_settings, user_id)
    blocked = client.get(f"{API}/do-not-contact", headers=user).json()
    detail = client.get(f"{API}/applications/{application['id']}", headers=user).json()

    assert [(b["email"], b["source"]) for b in blocked] == [(RECRUITER, "reply")]
    assert detail["status"] == "rejected"


# ---------- follow-ups and no-response ----------


@respx.mock
def test_follow_up_is_drafted_sent_in_the_thread_and_cancelled_by_a_reply(
    app: FastAPI,
    client: TestClient,
    migrated_database: str,
    gmail_settings: Settings,
    tmp_path: Path,
) -> None:
    user_id, user, application, _, _ = _sent_application(
        app, client, migrated_database, gmail_settings, tmp_path
    )
    db(migrated_database, "UPDATE emails SET sent_at = now() - interval '8 days'")
    respx.get(f"{THREADS}/thread-1").mock(
        return_value=httpx.Response(
            200, json={"messages": [{"id": "msg-1", "threadId": "thread-1", "labelIds": ["SENT"]}]}
        )
    )
    respx.post(AI_URL).mock(
        return_value=chat_response(
            {
                "paragraphs": [
                    "I wanted to follow up on my application for the React Native Developer 1 "
                    "role. I am still very interested and happy to share anything else you need."
                ]
            }
        )
    )

    result = _poll(app, gmail_settings, user_id)
    drafts = client.get(f"{API}/outbox?status=draft", headers=user).json()["items"]
    (follow_up,) = drafts
    approved = client.post(f"{API}/emails/{follow_up['id']}/approve", headers=user).json()
    sends = _pending_tasks(app, "email_send")
    route = respx.post(SENT_URL).mock(
        return_value=httpx.Response(200, json={"id": "msg-2", "threadId": "thread-1"})
    )
    respx.get(f"{MESSAGES}/msg-2").mock(
        return_value=httpx.Response(200, json={"payload": {"headers": []}})
    )
    assert _work(app, gmail_settings, sends[-1], tmp_path) is Outcome.SUCCEEDED

    assert result.follow_ups == 1
    assert follow_up["email_type"] == "follow_up_1" and follow_up["subject"].startswith("Re: ")
    assert follow_up["body_text"].startswith("Dear Priya,") and follow_up["attachments"] == []
    assert approved["status"] == "queued"
    request = route.calls[-1].request
    assert request.url.params["uploadType"] == "multipart"
    assert b'{"threadId": "thread-1"}' in request.content
    raw = request.content.split(b"Content-Type: message/rfc822\r\n\r\n", 1)[1]
    sent = email.message_from_bytes(raw, policy=policy.default)
    assert sent["In-Reply-To"] == "<real-1@mail.gmail.com>"
    detail = client.get(f"{API}/applications/{application['id']}", headers=user).json()
    assert detail["status"] == "applied"  # a follow-up never changes the status
    # Only one follow-up, even on the next poll.
    respx.get(f"{HISTORY}").mock(return_value=httpx.Response(200, json={"historyId": "102"}))
    assert _poll(app, gmail_settings, user_id).follow_ups == 0


@respx.mock
def test_a_reply_cancels_a_pending_follow_up_and_no_response_after_the_limit(
    app: FastAPI,
    client: TestClient,
    migrated_database: str,
    gmail_settings: Settings,
    tmp_path: Path,
) -> None:
    user_id, user, application, _, _ = _sent_application(
        app, client, migrated_database, gmail_settings, tmp_path
    )
    client.patch(
        f"{API}/users/me/settings", json={"follow_up_days": 0, "no_response_days": 21}, headers=user
    )
    db(migrated_database, "UPDATE emails SET sent_at = now() - interval '22 days'")
    respx.get(f"{THREADS}/thread-1").mock(return_value=httpx.Response(200, json={"messages": []}))

    result = _poll(app, gmail_settings, user_id)
    detail = client.get(f"{API}/applications/{application['id']}", headers=user).json()

    assert result.no_response == 1 and result.follow_ups == 0
    assert detail["status"] == "no_response"
    assert detail["history"][-1]["source"] == "system"


# ---------- automation ----------


ABC_PARAGRAPHS = [
    p.replace("React Native Developer 1", "React Native Developer").replace(
        "Company 1", "ABC Technologies"
    )
    for p in EMAIL_PARAGRAPHS
]


@respx.mock
def test_automate_saved_jobs_uses_jobs_with_an_approved_contact(
    app: FastAPI,
    client: TestClient,
    migrated_database: str,
    gmail_settings: Settings,
    tmp_path: Path,
) -> None:
    user_id, user = _setup(app, client, migrated_database, gmail_settings, tmp_path)
    _connect_gmail(client, user)
    client.patch(
        f"{API}/users/me/settings",
        json={
            "automation_min_score": 50,
            "automation_tailor": False,
            "automation_cover_letter": False,
        },
        headers=user,
    )
    run = _search_and_run(
        app, client, gmail_settings, tmp_path, user, FakeJobSource([make_job(1, description=JD)])
    )
    job_id = run["jobs"][0]["id"]
    nothing = client.post(f"{API}/automation/run", json={"mode": "saved"}, headers=user)
    before = client.get(f"{API}/automation", headers=user).json()
    client.post(
        f"{API}/contacts",
        json={"email": "priya1@acme.com", "name": "Priya Sharma", "job_id": job_id},
        headers=user,
    )
    ready = client.get(f"{API}/automation", headers=user).json()
    respx.post(AI_URL).side_effect = [
        chat_response(MATCH),
        chat_response({"subject": "Application", "paragraphs": EMAIL_PARAGRAPHS}),
    ]

    task_id = client.post(f"{API}/automation/run", json={"mode": "saved"}, headers=user).json()[
        "task_id"
    ]
    posts = FakePosts([_post(1, HIRING)])
    assert _work(app, gmail_settings, task_id, tmp_path, post_source=posts) is Outcome.SUCCEEDED
    after = client.get(f"{API}/automation", headers=user).json()
    (queued,) = client.get(f"{API}/outbox?status=draft", headers=user).json()["items"]
    again = client.post(f"{API}/automation/run", json={"mode": "saved"}, headers=user)

    assert nothing.json()["error"]["code"] == "NOTHING_TO_AUTOMATE"
    assert (before["saved_ready"], ready["saved_ready"], after["saved_ready"]) == (0, 1, 0)
    assert before["fetch_allowed"] is False
    result = after["last_run"]["result"]
    assert (result["mode"], result["posts"], result["scored"], result["prepared"]) == (
        "saved",
        0,
        1,
        1,
    )
    assert posts.queries == []  # saved mode never calls Apify
    assert queued["contact"]["approval"] == "approved"
    assert queued["application"]["job_title"] == "React Native Developer 1"
    assert again.json()["error"]["code"] == "NOTHING_TO_AUTOMATE"  # it has an application now


@respx.mock
def test_fetch_and_automate_is_locked_until_an_admin_enables_it(
    app: FastAPI,
    client: TestClient,
    migrated_database: str,
    gmail_settings: Settings,
    tmp_path: Path,
) -> None:
    user_id, user = _setup(app, client, migrated_database, gmail_settings, tmp_path)
    _, admin = make_user(client, migrated_database, "admin@example.com", role="admin")
    _connect_gmail(client, user)
    client.patch(
        f"{API}/users/me/settings",
        json={
            "linkedin_source_enabled": True,
            "automation_keywords": ["React Native", " react native "],
            "automation_min_score": 50,
            "automation_tailor": False,
            "automation_cover_letter": False,
        },
        headers=user,
    )
    locked = client.post(f"{API}/automation/run", json={"mode": "fetch"}, headers=user)
    not_admin = client.patch(
        f"{API}/admin/platform", json={"automation_fetch_enabled": True}, headers=user
    )
    enabled = client.patch(
        f"{API}/admin/platform", json={"automation_fetch_enabled": True}, headers=admin
    ).json()
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
        chat_response(MATCH),
        chat_response(
            {"subject": "Application – React Native Developer", "paragraphs": ABC_PARAGRAPHS}
        ),
    ]

    task_id = client.post(f"{API}/automation/run", json={"mode": "fetch"}, headers=user).json()[
        "task_id"
    ]
    outcome = _work(
        app,
        gmail_settings,
        task_id,
        tmp_path,
        post_source=FakePosts([_post(1, HIRING)]),
        domain_checker=FakeDomains(),
    )
    status = client.get(f"{API}/automation", headers=user).json()
    (queued,) = client.get(f"{API}/outbox?status=draft", headers=user).json()["items"]
    approved = client.post(
        f"{API}/emails/{queued['id']}/approve?approve_contact=true", headers=user
    ).json()

    assert locked.status_code == 403 and locked.json()["error"]["code"] == "FETCH_LOCKED"
    assert not_admin.status_code == 403
    assert enabled["automation_fetch_enabled"] is True and status["fetch_allowed"] is True
    assert outcome is Outcome.SUCCEEDED
    assert status["keywords"] == ["React Native"]  # duplicates removed
    run = status["last_run"]["result"]
    assert (run["mode"], run["posts"], run["candidates"], run["prepared"]) == ("fetch", 1, 1, 1)
    assert queued["contact"]["approval"] == "pending"  # found on LinkedIn, not yet approved
    assert queued["contact"]["source_excerpt"] and queued["application"]["match_score"] is not None
    assert approved["status"] == "queued" and approved["contact"]["approval"] == "approved"
    (action,) = db(
        migrated_database, "SELECT action FROM audit_logs WHERE action LIKE 'platform%'"
    )[0]
    assert action == "platform.automation_fetch"


@respx.mock
def test_empty_keyword_search_is_reported(
    app: FastAPI,
    client: TestClient,
    migrated_database: str,
    gmail_settings: Settings,
    tmp_path: Path,
) -> None:
    user_id, user = _setup(app, client, migrated_database, gmail_settings, tmp_path)
    _, admin = make_user(client, migrated_database, "admin@example.com", role="admin")
    _connect_gmail(client, user)
    client.patch(f"{API}/admin/platform", json={"automation_fetch_enabled": True}, headers=admin)
    client.patch(
        f"{API}/users/me/settings",
        json={"linkedin_source_enabled": True, "automation_keywords": ["Associate Data Scientist"]},
        headers=user,
    )

    task_id = client.post(f"{API}/automation/run", json={"mode": "fetch"}, headers=user).json()[
        "task_id"
    ]
    _work(app, gmail_settings, task_id, tmp_path, post_source=FakePosts([]))
    result = client.get(f"{API}/automation", headers=user).json()["last_run"]["result"]

    assert result["posts"] == 0 and result["empty_keywords"] == ["Associate Data Scientist"]
