"""Phase 15: AI mock interview — plan, voice session token, transcript, report, limits."""

import json
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import httpx
import respx
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.core.config import Settings
from app.integrations.realtime import GeminiLiveClient, RealtimeClient, RealtimeToken, voice_client
from app.models.enums import InterviewSpeaker, InterviewVerdict
from app.services.interviews import communication_metrics, verdict_for
from app.workers.runner import Outcome
from tests.fakes import FakeJobSource, chat_response
from tests.helpers import db, make_user, set_platform
from tests.test_documents import _setup
from tests.test_jobs import _work

AI_URL = "https://ai.test/v1/chat/completions"
API = "/api/v1"

PLAN = {
    "company": "Company 1",
    "role": "React Native Developer 1",
    "opening": "Hi, thanks for joining! Could you briefly introduce yourself?",
    "questions": [
        {
            "id": "x",
            "kind": "skill",
            "topic": "React Native",
            "question": "How did you cut the crash rate at Acme Apps?",
            "follow_up": "What did you measure?",
            "strong_answer_signals": ["error handling", "a number"],
        },
        {
            "id": "y",
            "kind": "gap",
            "topic": "GraphQL",
            "question": "How would you get up to speed with GraphQL?",
            "follow_up": "Any first step?",
            "strong_answer_signals": ["a plan"],
        },
        {
            "id": "z",
            "kind": "behavioral",
            "topic": "Ownership",
            "question": "Tell me about a release you owned end to end.",
            "follow_up": "What was the result?",
            "strong_answer_signals": ["STAR"],
        },
    ],
    "closing": "Thanks so much, that's all from me!",
    "thin_description": False,
}

ANSWER = "Um I added better error handling and the crash rate went down by thirty percent"


def report(quote: str = "the crash rate went down by thirty percent") -> dict[str, Any]:
    question = {
        "went_well": "Concrete result.",
        "missing": "How it was measured.",
        "better_answer": "At Acme Apps I added error handling and cut crashes by 30%.",
    }
    return {
        "verdict": "practice",  # ignored: the verdict follows the score
        "overall_score": 68,
        "summary": "A good start with a concrete result.",
        "questions": [
            {
                "question_id": "q1",
                "question": PLAN["questions"][0]["question"],
                "score": 4,
                "quote": quote,
                **question,
            },
            {
                "question_id": "q2",
                "question": PLAN["questions"][1]["question"],
                "score": 9,
                "quote": "",
                **question,
            },
        ],
        "strengths": ["Numbers"],
        "improvements": ["Use STAR"],
        "skills_shown": ["React Native"],
        "skills_not_shown": ["GraphQL"],
        "communication": {"clarity": 4, "structure": 3, "notes": "Clear."},
        "practice_plan": ["Practise a STAR story"],
    }


class FakeRealtime:
    def __init__(self) -> None:
        self.instructions: list[str] = []

    async def create_token(self, instructions: str, *, minutes: int = 6) -> RealtimeToken:
        self.instructions.append(instructions)
        return RealtimeToken(
            "ek_test",
            datetime.now(UTC) + timedelta(minutes=2),
            "sess_1",
            "gpt-realtime-mini",
            connect_url="https://api.openai.com/v1/realtime/calls",
        )


def _work_task(app: FastAPI, settings: Settings, tmp_path: Path, task_id: str) -> Outcome:
    return _work(app, settings, task_id, tmp_path, FakeJobSource())


def _planned(app, client, url, settings, tmp_path, email="a@example.com"):  # type: ignore[no-untyped-def]
    user_id, headers, job_id = _setup(app, client, url, settings, tmp_path, email)
    respx.post(AI_URL).mock(return_value=chat_response(PLAN))
    created = client.post(f"{API}/jobs/{job_id}/interviews", json={}, headers=headers)
    assert created.status_code == 202, created.text
    body = created.json()
    assert _work_task(app, settings, tmp_path, body["task_id"]) is Outcome.SUCCEEDED
    return user_id, headers, job_id, body["interview_id"]


def _turns(client: TestClient, headers: dict, interview_id: str, *turns: tuple) -> httpx.Response:
    return client.post(
        f"{API}/interviews/{interview_id}/turns",
        json={
            "turns": [
                {"seq": s, "speaker": sp, "text": t, "offset_ms": s * 1000} for s, sp, t in turns
            ]
        },
        headers=headers,
    )


# ---------- rules ----------


def test_verdict_and_metrics_are_computed_by_code() -> None:
    class T:
        def __init__(self, speaker: InterviewSpeaker, text: str) -> None:
            self.speaker, self.text = speaker, text

    turns = [
        T(InterviewSpeaker.INTERVIEWER, "Tell me about yourself please"),
        T(InterviewSpeaker.CANDIDATE, "Um I build apps, you know, mostly mobile"),
        T(InterviewSpeaker.CANDIDATE, "I like working with designers"),
    ]
    metrics = communication_metrics(turns)  # type: ignore[arg-type]
    assert (metrics["answers"], metrics["candidate_words"]) == (2, 13)
    assert metrics["filler_words"] == 2 and set(metrics["top_fillers"]) == {"um", "you know"}
    assert (verdict_for(80), verdict_for(60), verdict_for(30)) == (
        InterviewVerdict.READY,
        InterviewVerdict.ALMOST,
        InterviewVerdict.PRACTICE,
    )


# ---------- the whole flow ----------


@respx.mock
def test_interview_from_plan_to_report(
    app: FastAPI, client: TestClient, migrated_database: str, settings: Settings, tmp_path: Path
) -> None:
    app.state.realtime = realtime = FakeRealtime()
    _, headers, job_id, interview_id = _planned(app, client, migrated_database, settings, tmp_path)
    url = f"{API}/interviews/{interview_id}"

    ready = client.get(url, headers=headers).json()
    assert ready["status"] == "ready" and ready["minutes"] == 6
    assert ready["questions"] == []  # hidden until the call is over

    session = client.post(f"{url}/session", headers=headers)
    assert session.status_code == 200, session.text
    grant = session.json()
    assert grant["client_secret"] == "ek_test" and grant["reconnect"] is False
    assert grant["connect_url"].endswith("/realtime/calls") and 350 <= grant["seconds_left"] <= 360
    assert (
        "Maya" in realtime.instructions[0] and "crash rate at Acme Apps" in realtime.instructions[0]
    )
    assert "first name is New" in realtime.instructions[0]
    assert "Time is almost up" in grant["wrap_up"]

    saved = _turns(
        client,
        headers,
        interview_id,
        (0, "interviewer", PLAN["questions"][0]["question"]),
        (1, "candidate", ANSWER),
        (1, "candidate", ANSWER),  # resend after a lost request: same line
        (2, "interviewer", "Thanks!"),
    )
    assert saved.json() == {"saved": 4}
    # A reconnect continues the conversation instead of greeting again.
    again = client.post(f"{url}/session", headers=headers).json()
    assert again["reconnect"] is True and "Conversation so far" in realtime.instructions[1]

    assert client.post(f"{url}/finish", headers=headers).status_code == 204
    ended = client.get(url, headers=headers).json()
    assert ended["status"] == "ended" and len(ended["questions"]) == 3
    assert [t["seq"] for t in ended["turns"]] == [0, 1, 2]
    assert client.post(f"{url}/session", headers=headers).status_code == 409

    # Fix a misheard word; the interviewer's lines cannot be edited.
    fixed = client.patch(f"{url}/turns/1", json={"text": ANSWER + " overall"}, headers=headers)
    assert fixed.json()["edited"] is True and fixed.json()["original_text"] == ANSWER
    assert client.patch(f"{url}/turns/0", json={"text": "x"}, headers=headers).status_code == 422

    respx.post(AI_URL).mock(return_value=chat_response(report()))
    started = client.post(f"{url}/report", headers=headers)
    assert started.status_code == 202
    assert client.get(url, headers=headers).json()["status"] == "reporting"
    assert _work_task(app, settings, tmp_path, started.json()["task_id"]) is Outcome.SUCCEEDED

    done = client.get(url, headers=headers).json()
    assert done["status"] == "completed"
    assert (done["verdict"], done["overall_score"]) == ("almost", 68)  # from the score
    body = done["report"]["report"]
    assert body["questions"][1]["score"] == 5  # clamped to 1-5
    assert body["metrics"]["filler_words"] == 1 and body["metrics"]["answers"] == 1
    assert done["report"]["pdf_url"].startswith("/api/v1/files/")
    assert client.get(done["report"]["pdf_url"]).content.startswith(b"%PDF")
    assert client.patch(f"{url}/turns/1", json={"text": "late"}, headers=headers).status_code == 409

    listed = client.get(f"{API}/interviews?job_id={job_id}", headers=headers).json()
    assert [(i["id"], i["verdict"]) for i in listed] == [(interview_id, "almost")]
    usage = client.get(f"{API}/usage", headers=headers).json()
    assert usage["interviews_month"] == {"used": 1, "limit": 10, "left": 9}
    tasks = {r[0] for r in db(migrated_database, "SELECT task_type FROM ai_calls")}
    assert {"interview_plan", "interview_report", "interview_realtime"} <= tasks
    (notes,) = db(
        migrated_database, "SELECT count(*) FROM notifications WHERE type = 'interview_report'"
    )[0:1]
    assert notes[0] == 1

    # "Retry weak questions" plans a new interview from this report (and counts).
    respx.post(AI_URL).mock(return_value=chat_response(PLAN))
    retry = client.post(
        f"{API}/jobs/{job_id}/interviews", json={"retry_of_id": interview_id}, headers=headers
    )
    assert retry.status_code == 202
    assert _work_task(app, settings, tmp_path, retry.json()["task_id"]) is Outcome.SUCCEEDED
    plan_prompt = json.loads(respx.calls.last.request.content)["messages"][0]["content"]
    assert "retry of weak answers" in plan_prompt

    assert client.delete(url, headers=headers).status_code == 204
    assert client.get(url, headers=headers).status_code == 404


@respx.mock
def test_quotes_that_are_not_the_candidates_words_are_dropped(
    app: FastAPI, client: TestClient, migrated_database: str, settings: Settings, tmp_path: Path
) -> None:
    app.state.realtime = FakeRealtime()
    _, headers, _, interview_id = _planned(app, client, migrated_database, settings, tmp_path)
    url = f"{API}/interviews/{interview_id}"
    client.post(f"{url}/session", headers=headers)
    _turns(client, headers, interview_id, (0, "interviewer", "Hello"), (1, "candidate", ANSWER))
    client.post(f"{url}/finish", headers=headers)

    invented = chat_response(report(quote="I led a team of twenty engineers"))
    ai = respx.post(AI_URL).mock(side_effect=[invented, invented])
    before = ai.call_count  # the plan call went to the same route
    task_id = client.post(f"{url}/report", headers=headers).json()["task_id"]
    assert _work_task(app, settings, tmp_path, task_id) is Outcome.SUCCEEDED

    assert ai.call_count - before == 2  # one retry asking for real quotes
    retry_prompt = json.loads(ai.calls.last.request.content)["messages"][-1]["content"]
    assert "not in the candidate's words" in retry_prompt
    q1 = client.get(url, headers=headers).json()["report"]["report"]["questions"][0]
    assert q1["quote"] == ""


# ---------- limits and rules ----------


@respx.mock
def test_limits_deadline_and_privacy(
    app: FastAPI, client: TestClient, migrated_database: str, settings: Settings, tmp_path: Path
) -> None:
    app.state.realtime = FakeRealtime()
    set_platform(migrated_database, interviews_per_month=1)
    _, headers, job_id, interview_id = _planned(app, client, migrated_database, settings, tmp_path)
    url = f"{API}/interviews/{interview_id}"

    over = client.post(f"{API}/jobs/{job_id}/interviews", json={}, headers=headers)
    assert over.status_code == 429 and over.json()["error"]["code"] == "INTERVIEW_LIMIT_REACHED"
    # Not started yet: no transcript, no report.
    assert _turns(client, headers, interview_id, (0, "candidate", "hi")).status_code == 409
    assert client.post(f"{url}/report", headers=headers).status_code == 409

    client.post(f"{url}/session", headers=headers)
    # Nothing answered → no report (the call is ended first).
    assert client.post(f"{url}/report", headers=headers).json()["error"]["code"] == "NO_ANSWERS"

    # Another user sees nothing.
    _, other = make_user(client, migrated_database, "b@example.com")
    assert client.get(url, headers=other).status_code == 404
    assert client.post(f"{url}/session", headers=other).status_code == 404
    assert client.get(f"{API}/interviews", headers=other).json() == []

    # A call whose tab was closed ends on its own after the deadline; late lines are refused.
    db(
        migrated_database,
        "UPDATE interviews SET status = 'in_progress', ended_at = NULL, "
        "started_at = now() - interval '10 minutes', deadline_at = now() - interval '4 minutes'",
    )
    late = _turns(client, headers, interview_id, (5, "candidate", "late answer"))
    assert late.status_code == 409
    auto = client.get(url, headers=headers).json()
    assert auto["status"] == "ended" and auto["seconds_used"] == 360


@respx.mock
def test_session_token_comes_from_openai_and_the_key_stays_on_the_server(
    app: FastAPI, client: TestClient, migrated_database: str, settings: Settings, tmp_path: Path
) -> None:
    keyed = settings.model_copy(update={"realtime_api_key": "sk-test-openai"})
    app.state.realtime = RealtimeClient(keyed)
    openai = respx.post("https://api.openai.com/v1/realtime/client_secrets").mock(
        return_value=httpx.Response(
            200,
            json={
                "value": "ek_abc",
                "expires_at": int((datetime.now(UTC) + timedelta(minutes=2)).timestamp()),
                "session": {"id": "sess_9", "model": "gpt-realtime-mini"},
            },
        )
    )
    _, headers, _, interview_id = _planned(app, client, migrated_database, settings, tmp_path)

    grant = client.post(f"{API}/interviews/{interview_id}/session", headers=headers)

    assert grant.status_code == 200, grant.text
    assert "sk-test-openai" not in grant.text and grant.json()["client_secret"] == "ek_abc"
    request = openai.calls.last.request
    assert request.headers["Authorization"] == "Bearer sk-test-openai"
    session = json.loads(request.content)["session"]
    assert (
        session["model"] == "gpt-realtime-mini" and session["audio"]["output"]["voice"] == "marin"
    )
    assert session["audio"]["input"]["transcription"]["language"] == "en"
    assert "English only" in session["instructions"]

    # Without a key the room explains what is missing (and nothing is started).
    app.state.realtime = RealtimeClient(settings)
    _, headers2, _, second = _planned(
        app, client, migrated_database, settings, tmp_path, email="d@example.com"
    )
    refused = client.post(f"{API}/interviews/{second}/session", headers=headers2)
    assert refused.json()["error"]["code"] == "REALTIME_NOT_CONFIGURED"
    assert client.get(f"{API}/interviews/{second}", headers=headers2).json()["status"] == "ready"


@respx.mock
def test_gemini_live_token_is_single_use_and_locked_to_the_interview(
    app: FastAPI, client: TestClient, migrated_database: str, settings: Settings, tmp_path: Path
) -> None:
    keyed = settings.model_copy(update={"gemini_api_key": "AIza-test-key"})
    assert voice_client(keyed).__class__ is GeminiLiveClient  # auto: Gemini when its key is set
    assert voice_client(settings).__class__ is RealtimeClient
    app.state.realtime = GeminiLiveClient(keyed)
    google = respx.post("https://generativelanguage.googleapis.com/v1beta/auth_tokens").mock(
        return_value=httpx.Response(200, json={"name": "auth_tokens/xyz"})
    )
    _, headers, _, interview_id = _planned(app, client, migrated_database, settings, tmp_path)

    grant = client.post(f"{API}/interviews/{interview_id}/session", headers=headers)

    assert grant.status_code == 200, grant.text
    body = grant.json()
    assert "AIza-test-key" not in grant.text
    assert (body["provider"], body["client_secret"]) == ("gemini", "auth_tokens/xyz")
    assert body["connect_url"].startswith("wss://generativelanguage.googleapis.com/ws/")
    assert body["connect_url"].endswith("BidiGenerateContentConstrained")
    request = google.calls.last.request
    assert request.headers["x-goog-api-key"] == "AIza-test-key"
    sent = json.loads(request.content)
    assert sent["uses"] == 1
    setup = sent["bidiGenerateContentSetup"]  # REST name (not liveConnectConstraints)
    assert setup["model"] == "models/gemini-2.5-flash-native-audio-latest"
    assert setup["generationConfig"]["responseModalities"] == ["AUDIO"]
    voice = setup["generationConfig"]["speechConfig"]["voiceConfig"]["prebuiltVoiceConfig"]
    assert voice["voiceName"] == "Aoede"
    assert "inputAudioTranscription" in setup and "outputAudioTranscription" in setup
    assert "Maya" in setup["systemInstruction"]["parts"][0]["text"]

    # Gemini minutes are priced with the Gemini rate.
    client.post(f"{API}/interviews/{interview_id}/finish", headers=headers)
    (model,) = db(migrated_database, "SELECT model FROM interviews")[0]
    assert model.startswith("gemini")
