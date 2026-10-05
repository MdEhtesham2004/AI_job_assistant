"""Phase 17: interview prep pack — automatic on Interview, on demand, focused mock."""

import asyncio
import json
from datetime import UTC, datetime
from pathlib import Path

import respx
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.core.config import Settings
from app.db.session import create_engine, create_session_factory
from app.services.prep import dispatch_preps
from app.services.tasks import RecordingDispatcher
from app.workers.runner import Outcome
from tests.fakes import FakeJobSource, chat_response
from tests.helpers import db, make_user
from tests.test_applications import _create, _move, _setup
from tests.test_interviews import PLAN
from tests.test_jobs import _work

AI_URL = "https://ai.test/v1/chat/completions"
API = "/api/v1"

PACK = {
    "role_summary": "Build and ship React Native features.",
    "what_they_value": ["Shipping reliably", "TypeScript"],
    "your_fit": [
        {"requirement": "React Native", "evidence": "4 years at Acme Apps"},
        {"requirement": "GraphQL", "evidence": "Not shown in your resume"},
    ],
    "likely_questions": [
        {"question": f"Question {n}?", "why": "Core skill.", "how_to_answer": "Use Acme."}
        for n in range(1, 7)
    ],
    "star_stories": [
        {
            "title": f"Story {n}",
            "situation": "Crashes were high.",
            "task": "Fix them.",
            "action": "Added error handling.",
            "result": "Crash rate down 30%." if n == 1 else "Grew users by 75%.",
            "use_for": ["Question 1?"],
        }
        for n in range(1, 5)  # 4: only 3 are kept
    ],
    "gaps": [{"gap": "GraphQL", "honest_answer": "Learning it; built a demo."}],
    "questions_to_ask": ["How do you release?"],
    "checklist": ["Test your mic"],
}


def _run(app: FastAPI, settings: Settings, tmp_path: Path, task_id: str) -> Outcome:
    return _work(app, settings, task_id, tmp_path, FakeJobSource())


def _prep_tasks(app: FastAPI) -> list[str]:
    return [str(t) for t, kind in app.state.dispatcher.sent if kind == "interview_prep"]


@respx.mock
def test_moving_to_interview_makes_the_pack_once(
    app: FastAPI, client: TestClient, migrated_database: str, settings: Settings, tmp_path: Path
) -> None:
    user, (job_id,), _ = _setup(app, client, migrated_database, settings, tmp_path)
    app_id = _create(client, user, job_id, channel="portal").json()["id"]
    client.post(f"{API}/applications/{app_id}/mark-applied", json={}, headers=user)

    assert _move(client, user, app_id, "interview").status_code == 200
    (task_id,) = _prep_tasks(app)
    state = client.get(f"{API}/jobs/{job_id}/prep", headers=user).json()
    assert state["pack"] is None and state["running_task_id"] == task_id

    ai = respx.post(AI_URL).mock(return_value=chat_response(PACK))
    assert _run(app, settings, tmp_path, task_id) is Outcome.SUCCEEDED
    got = client.get(f"{API}/jobs/{job_id}/prep", headers=user).json()
    pack = got["pack"]
    assert len(pack["star_stories"]) == 3
    assert pack["check"] == ["75"]  # 30% is in the resume, 75% is not
    assert got["pdf_url"].startswith("/api/v1/files/")
    assert client.get(got["pdf_url"]).content.startswith(b"%PDF")
    sent = json.loads(ai.calls.last.request.content)["messages"][1]["content"]
    assert "React Native" in sent  # the job and the resume go to the AI
    (title,) = db(
        migrated_database, "SELECT title FROM notifications WHERE type = 'interview_prep_ready'"
    )[0]
    assert title.startswith("Interview prep ready")

    # Later moves never make a second pack automatically; the user can refresh it.
    _move(client, user, app_id, "in_process")
    _move(client, user, app_id, "interview")
    assert len(_prep_tasks(app)) == 1
    refresh = client.post(f"{API}/jobs/{job_id}/prep", headers=user)
    assert refresh.status_code == 202 and len(_prep_tasks(app)) == 2

    # Another user sees nothing.
    _, other = make_user(client, migrated_database, "b@example.com")
    assert client.get(f"{API}/jobs/{job_id}/prep", headers=other).json()["pack"] is None


def test_reply_set_interviews_are_picked_up_by_the_sweep(
    app: FastAPI, client: TestClient, migrated_database: str, settings: Settings, tmp_path: Path
) -> None:
    user, (job_id,), _ = _setup(app, client, migrated_database, settings, tmp_path)
    _create(client, user, job_id, channel="portal")
    # As if an email reply had set the status (no API move, so nothing queued yet).
    db(migrated_database, "UPDATE applications SET status = 'interview', last_status_at = now()")
    dispatcher = RecordingDispatcher()

    def sweep() -> int:
        async def go() -> int:
            engine = create_engine(settings)
            async with create_session_factory(engine)() as session:
                started = await dispatch_preps(session, settings, dispatcher, datetime.now(UTC))
            await engine.dispose()
            return started

        return asyncio.run(go())

    assert sweep() == 1
    assert sweep() == 0  # still running: no duplicate
    assert [kind for _, kind in dispatcher.sent] == ["interview_prep"]


@respx.mock
def test_practise_with_maya_rehearses_the_packs_questions(
    app: FastAPI, client: TestClient, migrated_database: str, settings: Settings, tmp_path: Path
) -> None:
    user, (job_id,), _ = _setup(app, client, migrated_database, settings, tmp_path)
    no_pack = client.post(f"{API}/jobs/{job_id}/interviews", json={"from_prep": True}, headers=user)
    assert no_pack.status_code == 409 and no_pack.json()["error"]["code"] == "PREP_REQUIRED"

    respx.post(AI_URL).mock(return_value=chat_response(PACK))
    made = client.post(f"{API}/jobs/{job_id}/prep", headers=user).json()["task_id"]
    assert _run(app, settings, tmp_path, made) is Outcome.SUCCEEDED

    ai = respx.post(AI_URL).mock(return_value=chat_response(PLAN))
    created = client.post(f"{API}/jobs/{job_id}/interviews", json={"from_prep": True}, headers=user)
    assert created.status_code == 202, created.text
    assert _run(app, settings, tmp_path, created.json()["task_id"]) is Outcome.SUCCEEDED
    prompt = json.loads(ai.calls.last.request.content)["messages"][0]["content"]
    assert "rehearsing a real upcoming interview" in prompt
    assert "Question 1? | Question 2? | Question 3?" in prompt
