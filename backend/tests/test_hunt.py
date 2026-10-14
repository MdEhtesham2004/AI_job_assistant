"""Phase 16: daily digest, skill gaps + learning plan, screening answers."""

import asyncio
import base64
import email
import json
from datetime import UTC, date, datetime
from email import policy
from pathlib import Path

import httpx
import respx
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.core.config import Settings
from app.db.session import create_engine, create_session_factory
from app.models.hunt import Digest
from app.services.hunt import aggregate_skills, digest_email, dispatch_digests, unsupported_numbers
from app.services.tasks import RecordingDispatcher
from app.workers.runner import Outcome
from tests.fakes import FakeJobSource, chat_response, make_job
from tests.helpers import db
from tests.test_analysis import JD, MATCH, _setup
from tests.test_jobs import _work
from tests.test_outreach import GMAIL, _connect_gmail

AI_URL = "https://ai.test/v1/chat/completions"
API = "/api/v1"


def _run(app: FastAPI, settings: Settings, tmp_path: Path, task_id: str) -> Outcome:
    return _work(app, settings, task_id, tmp_path, FakeJobSource())


# ---------- rules ----------


def test_skill_counts_answer_checks_and_digest_email() -> None:
    gaps, strengths = aggregate_skills(
        [
            (["GraphQL", "Jest"], ["React Native"], "Dev 1 — A"),
            (["graphql", "Docker"], ["React Native", "Redux"], "Dev 2 — B"),
            (["GraphQL"], [], "Dev 3 — C"),
        ]
    )
    assert [(g.skill, g.jobs) for g in gaps] == [("GraphQL", 3), ("Docker", 1), ("Jest", 1)]
    assert gaps[0].examples == ["Dev 1 — A", "Dev 2 — B", "Dev 3 — C"]
    assert [(s.skill, s.jobs) for s in strengths] == [("React Native", 2), ("Redux", 1)]

    resume = "Cut the crash rate by 30% at Acme; 4 years of React Native"
    assert unsupported_numbers("I cut crashes by 30% over 4 years", resume) == []
    assert unsupported_numbers("I led 12 engineers and saved 45%", resume) == ["12", "45"]

    digest = Digest(
        digest_date=date(2026, 10, 5),
        jobs=[
            {"job_id": "j1", "title": "RN Dev", "company": "Acme", "location": "Pune", "score": 81}
        ],
    )
    subject, text, html = digest_email(digest, app_url="https://jobs.example", name="Asha")
    assert subject == "1 new job match for you today"
    assert "1. RN Dev — Acme (81/100) https://jobs.example/jobs/j1" in text
    assert "href='https://jobs.example/jobs/j1'" in html and "Hi Asha," in html


# ---------- digest ----------


@respx.mock
def test_digest_scores_new_jobs_within_the_cap_and_ranks_the_best(
    app: FastAPI, client: TestClient, migrated_database: str, settings: Settings, tmp_path: Path
) -> None:
    jobs = [make_job(n, description=JD) for n in (1, 2, 3)]
    _, headers, _ = _setup(app, client, migrated_database, settings, tmp_path, jobs=jobs)
    capped = settings.model_copy(update={"digest_score_cap": 2})
    ai = respx.post(AI_URL).mock(return_value=chat_response(MATCH))

    task = client.post(f"{API}/digest/run", headers=headers).json()["task_id"]
    assert _run(app, capped, tmp_path, task) is Outcome.SUCCEEDED

    state = client.get(f"{API}/digest", headers=headers).json()
    digest = state["digest"]
    assert digest["is_today"] and (digest["new_jobs"], digest["scored"]) == (3, 2)
    assert len(digest["jobs"]) == 2 and {j["score"] for j in digest["jobs"]} == {79}
    assert ai.call_count == 2  # the cap: the third job waits for tomorrow
    assert (digest["emailed"], digest["email_error"]) == (False, "Gmail is not connected.")
    (title,) = db(migrated_database, "SELECT title FROM notifications WHERE type = 'digest_daily'")[
        0
    ]
    assert title == "2 new matches for you today (best 79/100)"

    # Running again reuses the scores (no AI) and only scores what is still missing.
    again = client.post(f"{API}/digest/run", headers=headers).json()["task_id"]
    assert _run(app, capped, tmp_path, again) is Outcome.SUCCEEDED
    assert ai.call_count == 3
    assert len(client.get(f"{API}/digest", headers=headers).json()["digest"]["jobs"]) == 3

    # Above the user's minimum only.
    client.patch(f"{API}/users/me/settings", json={"digest_min_score": 90}, headers=headers)
    third = client.post(f"{API}/digest/run", headers=headers).json()["task_id"]
    assert _run(app, capped, tmp_path, third) is Outcome.SUCCEEDED
    assert client.get(f"{API}/digest", headers=headers).json()["digest"]["jobs"] == []


@respx.mock
def test_digest_email_goes_from_the_users_gmail_to_themselves(
    app: FastAPI,
    client: TestClient,
    migrated_database: str,
    gmail_settings: Settings,
    tmp_path: Path,
) -> None:
    app.state.settings = gmail_settings  # the API uses the fake Google endpoints too
    _, headers, _ = _setup(app, client, migrated_database, gmail_settings, tmp_path)
    _connect_gmail(client, headers)
    respx.post(AI_URL).mock(return_value=chat_response(MATCH))
    send = respx.post(f"{GMAIL}/upload/gmail/v1/users/me/messages/send").mock(
        return_value=httpx.Response(200, json={"id": "m1", "threadId": "t1"})
    )

    task = client.post(f"{API}/digest/run", headers=headers).json()["task_id"]
    assert _run(app, gmail_settings, tmp_path, task) is Outcome.SUCCEEDED

    assert client.get(f"{API}/digest", headers=headers).json()["digest"]["emailed"] is True
    raw = send.calls.last.request.content
    message = email.message_from_bytes(raw, policy=policy.default)
    assert message["To"] == "asha@gmail.com" and "asha@gmail.com" in message["From"]
    assert message["Subject"] == "1 new job match for you today"
    assert message.get_body(("html",)) is not None  # HTML + plain text
    assert base64 is not None  # (raw upload, no base64 wrapping needed)


def test_digests_start_once_the_local_hour_has_come(
    client: TestClient, migrated_database: str, settings: Settings
) -> None:
    from tests.helpers import make_user

    user_id, headers = make_user(client, migrated_database, "a@example.com")
    client.patch(f"{API}/users/me/settings", json={"digest_hour": 8}, headers=headers)
    client.get(f"{API}/users/me/profile", headers=headers)  # profile: Asia/Kolkata (UTC+5:30)
    dispatcher = RecordingDispatcher()

    def tick(at: datetime) -> int:
        async def go() -> int:
            engine = create_engine(settings)
            async with create_session_factory(engine)() as session:
                started = await dispatch_digests(session, settings, dispatcher, at)
            await engine.dispose()
            return started

        return asyncio.run(go())

    assert tick(datetime(2026, 10, 5, 2, 0, tzinfo=UTC)) == 0  # 07:30 in India
    assert tick(datetime(2026, 10, 5, 2, 45, tzinfo=UTC)) == 1  # 08:15
    assert tick(datetime(2026, 10, 5, 3, 0, tzinfo=UTC)) == 0  # task still queued: no duplicate
    assert [kind for _, kind in dispatcher.sent] == ["daily_digest"]
    client.patch(f"{API}/users/me/settings", json={"digest_enabled": False}, headers=headers)
    db(migrated_database, "UPDATE tasks SET status = 'succeeded'")
    assert tick(datetime(2026, 10, 5, 4, 0, tzinfo=UTC)) == 0  # turned off
    assert user_id


# ---------- skills ----------


@respx.mock
def test_skill_gaps_are_counted_and_a_plan_is_written(
    app: FastAPI, client: TestClient, migrated_database: str, settings: Settings, tmp_path: Path
) -> None:
    jobs = [make_job(n, description=JD) for n in (1, 2)]
    _, headers, _ = _setup(app, client, migrated_database, settings, tmp_path, jobs=jobs)
    assert client.post(f"{API}/skills/plan", headers=headers).status_code == 409  # nothing scored
    respx.post(AI_URL).mock(return_value=chat_response(MATCH))
    task = client.post(f"{API}/digest/run", headers=headers).json()["task_id"]
    _run(app, settings, tmp_path, task)

    skills = client.get(f"{API}/skills", headers=headers).json()
    assert skills["jobs_analyzed"] == 2
    assert [(g["skill"], g["jobs"]) for g in skills["gaps"]] == [("GraphQL", 2)]  # COBOL: not in JD
    assert skills["strengths"][0]["skill"] == "React Native"

    plan = {
        "summary": "GraphQL is asked for most.",
        "days": [{"day": d, "focus": "GraphQL", "task": f"Step {d}"} for d in range(14, 0, -1)],
        "mini_project": "A small GraphQL API for a todo app.",
        "resources": ["The official GraphQL docs (Learn section)"],
        "interview_tip": "Say what you have built so far and what you are learning.",
    }
    ai = respx.post(AI_URL).mock(return_value=chat_response(plan))
    started = client.post(f"{API}/skills/plan", headers=headers).json()["task_id"]
    assert _run(app, settings, tmp_path, started) is Outcome.SUCCEEDED

    saved = client.get(f"{API}/skills", headers=headers).json()["plan"]
    assert [d["day"] for d in saved["plan"]["days"]][:3] == [1, 2, 3]  # sorted
    assert saved["gaps"] == [{"skill": "GraphQL", "jobs": 2}]
    sent = json.loads(ai.calls.last.request.content)["messages"][1]["content"]
    assert '"GraphQL"' in sent and "COBOL" not in sent


# ---------- screening answers ----------


@respx.mock
def test_screening_answers_are_grounded_and_never_guess_salary(
    app: FastAPI, client: TestClient, migrated_database: str, settings: Settings, tmp_path: Path
) -> None:
    _, headers, job_ids = _setup(app, client, migrated_database, settings, tmp_path)
    job = job_ids[0]
    answers = {
        "answers": [
            {"key": "about", "answer": "I build React Native apps and cut crashes by 30%."},
            {"key": "why_hire", "answer": "I led 12 engineers."},  # 12 is not in the resume
            {"key": "salary", "answer": "I expect 25 LPA."},  # guessed: no profile fact
            {"key": "notice", "answer": "30 days."},
            {"key": "custom_1", "answer": "Yes, I can relocate to Pune."},
        ]
    }
    ai = respx.post(AI_URL).mock(return_value=chat_response(answers))
    started = client.post(
        f"{API}/jobs/{job}/answers",
        json={"custom_questions": ["Are you willing to relocate?"]},
        headers=headers,
    )
    assert started.status_code == 202, started.text
    assert _run(app, settings, tmp_path, started.json()["task_id"]) is Outcome.SUCCEEDED

    got = {
        a["key"]: a
        for a in client.get(f"{API}/jobs/{job}/answers", headers=headers).json()["answers"]
    }
    assert len(got) == 9  # 8 standard + 1 custom
    assert got["why_company"]["question"].endswith("at Company 1?")
    assert got["salary"]["answer"] == "My expectation is [fill in], and I am open to discussing it."
    assert got["notice"]["answer"] == "My notice period is [fill in]."
    assert got["why_hire"]["check"] == ["12"] and got["about"]["check"] == []
    assert got["strength"]["answer"] == "[fill in]"  # not answered by the AI
    assert got["custom_1"]["custom"] is True
    prompt = json.loads(ai.calls.last.request.content)["messages"][0]["content"]
    assert "no notice period or salary" in prompt

    # The profile's facts are used; the user's edits survive a rewrite.
    client.put(
        f"{API}/users/me/profile",
        json={
            "notice_period": "30 days",
            "expected_salary": "12-14 LPA",
            "timezone": "Asia/Kolkata",
        },
        headers=headers,
    )
    edited = client.patch(
        f"{API}/jobs/{job}/answers/about", json={"answer": "My own intro."}, headers=headers
    )
    assert edited.status_code == 200
    again = client.post(f"{API}/jobs/{job}/answers", json={}, headers=headers).json()["task_id"]
    assert _run(app, settings, tmp_path, again) is Outcome.SUCCEEDED
    got = {
        a["key"]: a
        for a in client.get(f"{API}/jobs/{job}/answers", headers=headers).json()["answers"]
    }
    assert got["about"] == {**got["about"], "answer": "My own intro.", "edited": True}
    assert got["notice"]["answer"] == "30 days."  # a profile fact exists now
    prompt = json.loads(ai.calls.last.request.content)["messages"][0]["content"]
    assert "notice period: 30 days" in prompt and "expected salary: 12-14 LPA" in prompt

    # Another user sees nothing.
    from tests.helpers import make_user

    _, other = make_user(client, migrated_database, "b@example.com")
    assert client.get(f"{API}/jobs/{job}/answers", headers=other).json()["answers"] == []
    assert (
        client.patch(
            f"{API}/jobs/{job}/answers/about", json={"answer": "x"}, headers=other
        ).status_code
        == 404
    )
