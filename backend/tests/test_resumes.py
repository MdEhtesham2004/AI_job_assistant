"""Phase 7: resume upload, versions, parsing, ATS analysis, improved resume, LinkedIn summary."""

import asyncio
import copy
import uuid
from pathlib import Path

import pytest
import respx
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.core.config import Settings
from app.core.errors import ValidationAppError
from app.db.session import create_engine, create_session_factory
from app.prompts.resumes import ParsedResume
from app.services.resume_files import UnsupportedFileError, detect, extract_text
from app.services.resume_improve import render_html, ungrounded_facts
from app.workers.runner import Outcome, run_task
from tests.fakes import FAKE_PDF, chat_response, fake_services
from tests.helpers import db, make_user
from tests.resume_samples import ATS, PARSED, RESUME_LINES, make_docx, make_pdf

AI_URL = "https://ai.test/v1/chat/completions"
API = "/api/v1/resumes"


def _upload(client: TestClient, headers: dict[str, str], name: str, data: bytes, mime: str):
    return client.post(f"{API}/upload", headers=headers, files={"file": (name, data, mime)})


def _upload_pdf(client: TestClient, headers: dict[str, str]) -> dict:
    response = _upload(client, headers, "asha.pdf", make_pdf(), "application/pdf")
    assert response.status_code == 201, response.text
    return response.json()


def _work(app: FastAPI, settings: Settings, task_id: str, tmp_path: Path) -> Outcome:
    """Run one queued task the way the worker would, sharing the app's storage."""

    async def go() -> Outcome:
        engine = create_engine(settings)
        services = fake_services(settings, tmp_path, storage=app.state.storage)
        result = await run_task(
            uuid.UUID(task_id),
            settings,
            services=services,
            session_factory=create_session_factory(engine),
        )
        await engine.dispose()
        return result.outcome

    return asyncio.run(go())


# ---------- files ----------


def test_pdf_and_docx_text_is_extracted() -> None:
    for name, data in [("cv.pdf", make_pdf()), ("cv.docx", make_docx())]:
        info = detect(name, data)
        text = extract_text(data, info.kind)
        assert "Acme Apps" in text
        assert "B.Tech Computer Science" in text


@pytest.mark.parametrize(
    ("name", "data"),
    [
        ("photo.png", b"\x89PNG\r\n\x1a\n" + b"0" * 500),
        ("fake.pdf", b"not really a pdf"),
        ("cv.docx", make_pdf()),  # wrong extension for the content
        ("archive.docx", b"PK\x03\x04 broken zip"),
    ],
)
def test_other_files_are_rejected(name: str, data: bytes) -> None:
    with pytest.raises(UnsupportedFileError):
        detect(name, data)


def test_image_only_pdf_is_rejected() -> None:
    with pytest.raises(ValidationAppError):
        extract_text(make_pdf(["Hi"]), "pdf")


# ---------- grounding ----------


def test_truthful_rewrite_passes_the_grounding_check() -> None:
    original = ParsedResume.model_validate(PARSED)
    improved = copy.deepcopy(PARSED)
    improved["summary"] = "React Native developer with 4 years of experience shipping apps."
    improved["experience"][0]["highlights"][1] = "Reduced crash rate by 30% via error handling"

    problems = ungrounded_facts(
        ParsedResume.model_validate(improved), original, "\n".join(RESUME_LINES)
    )

    assert problems == []


def test_invented_facts_are_caught() -> None:
    original = ParsedResume.model_validate(PARSED)
    invented = copy.deepcopy(PARSED)
    invented["experience"][0]["company"] = "Google"
    invented["education"][0]["institution"] = "IIT Bombay"
    invented["skills"].append("Kubernetes")
    invented["experience"][1]["highlights"][0] = "Shipped 12 apps"

    problems = ungrounded_facts(
        ParsedResume.model_validate(invented), original, "\n".join(RESUME_LINES)
    )

    assert "employer 'Google'" in problems
    assert "institution 'IIT Bombay'" in problems
    assert "skill 'Kubernetes'" in problems
    assert "number '12'" in problems


def test_template_escapes_content() -> None:
    resume = ParsedResume.model_validate({**PARSED, "summary": "<script>alert(1)</script>"})

    html = render_html(resume)

    assert "<script>alert" not in html
    assert "&lt;script&gt;" in html
    assert "Acme Apps" in html


# ---------- upload & versions ----------


def test_upload_pdf_creates_first_active_version_and_queues_parsing(
    app: FastAPI, client: TestClient, migrated_database: str
) -> None:
    _, user = make_user(client, migrated_database, "a@example.com")

    body = _upload_pdf(client, user)

    version = body["version"]
    assert version["version_no"] == 1
    assert version["kind"] == "master"
    assert version["is_active"] is True
    assert version["parse_status"] == "pending"
    assert app.state.dispatcher.sent == [(uuid.UUID(body["task_id"]), "resume_parse")]
    overview = client.get(API, headers=user).json()
    assert overview["active_version_id"] == version["id"]
    assert [v["id"] for v in overview["versions"]] == [version["id"]]


def test_docx_is_accepted_and_other_types_rejected(
    client: TestClient, migrated_database: str
) -> None:
    _, user = make_user(client, migrated_database, "a@example.com")
    docx_mime = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"

    docx = _upload(client, user, "asha.docx", make_docx(), docx_mime)
    png = _upload(client, user, "me.png", b"\x89PNG\r\n\x1a\n" + b"0" * 500, "image/png")

    assert docx.status_code == 201
    assert docx.json()["version"]["mime_type"] == docx_mime
    assert png.status_code == 415
    assert png.json()["error"]["code"] == "UNSUPPORTED_FILE_TYPE"


def test_large_and_empty_files_are_rejected(
    client: TestClient, migrated_database: str, settings: Settings
) -> None:
    _, user = make_user(client, migrated_database, "a@example.com")
    too_big = b"%PDF" + b"0" * settings.resume_max_bytes

    assert _upload(client, user, "big.pdf", too_big, "application/pdf").status_code == 413
    assert _upload(client, user, "empty.pdf", b"", "application/pdf").status_code == 422


def test_new_upload_keeps_old_versions_and_active_can_be_switched(
    client: TestClient, migrated_database: str
) -> None:
    _, user = make_user(client, migrated_database, "a@example.com")
    first = _upload_pdf(client, user)["version"]
    second = _upload_pdf(client, user)["version"]

    assert second["version_no"] == 2
    assert second["is_active"] is False  # the first upload stays active until switched
    versions = client.get(API, headers=user).json()["versions"]
    assert [v["version_no"] for v in versions] == [2, 1]

    assert client.post(f"{API}/versions/{second['id']}/activate", headers=user).status_code == 204
    overview = client.get(API, headers=user).json()
    assert overview["active_version_id"] == second["id"]
    assert [v["is_active"] for v in overview["versions"]] == [True, False]
    assert client.get(f"{API}/versions/{first['id']}", headers=user).status_code == 200


def test_version_detail_offers_the_original_file(
    client: TestClient, migrated_database: str
) -> None:
    _, user = make_user(client, migrated_database, "a@example.com")
    version_id = _upload_pdf(client, user)["version"]["id"]

    detail = client.get(f"{API}/versions/{version_id}", headers=user).json()

    assert detail["ats_report"] is None
    assert [t["type"] for t in detail["active_tasks"]] == ["resume_parse"]
    download = client.get(detail["download_url"])
    assert download.status_code == 200
    assert download.content == make_pdf()


def test_resumes_are_private(client: TestClient, migrated_database: str) -> None:
    _, alice = make_user(client, migrated_database, "alice@example.com")
    _, bob = make_user(client, migrated_database, "bob@example.com")
    version_id = _upload_pdf(client, alice)["version"]["id"]

    assert client.get(API, headers=bob).json()["versions"] == []
    assert client.get(f"{API}/versions/{version_id}", headers=bob).status_code == 404
    assert client.post(f"{API}/versions/{version_id}/activate", headers=bob).status_code == 404
    assert client.post(f"{API}/versions/{version_id}/ats", headers=bob).status_code == 404


def test_pending_accounts_cannot_upload(client: TestClient, migrated_database: str) -> None:
    _, pending = make_user(client, migrated_database, "p@example.com", approval="pending")

    response = _upload(client, pending, "asha.pdf", make_pdf(), "application/pdf")

    assert response.status_code == 403


def test_actions_check_their_preconditions_and_do_not_duplicate(
    app: FastAPI, client: TestClient, migrated_database: str
) -> None:
    _, user = make_user(client, migrated_database, "a@example.com")
    version_id = _upload_pdf(client, user)["version"]["id"]

    improve = client.post(f"{API}/versions/{version_id}/improve", headers=user)
    first_ats = client.post(f"{API}/versions/{version_id}/ats", headers=user).json()
    again_ats = client.post(f"{API}/versions/{version_id}/ats", headers=user).json()

    assert improve.status_code == 409
    assert improve.json()["error"]["code"] == "RESUME_NOT_PARSED"
    assert first_ats == again_ats  # still queued → the same task is returned
    assert [kind for _, kind in app.state.dispatcher.sent] == ["resume_parse", "resume_ats"]


# ---------- background tasks ----------


@respx.mock
def test_full_flow_parse_ats_improve_linkedin(
    app: FastAPI, client: TestClient, migrated_database: str, settings: Settings, tmp_path: Path
) -> None:
    improved = copy.deepcopy(PARSED)
    improved["summary"] = "React Native developer with 4 years of experience shipping apps."
    # identity and contact details are always kept from the original
    improved["email"] = "changed@evil.test"
    improved["headline"] = "Chief Mobile Officer"
    route = respx.post(AI_URL)
    route.side_effect = [
        chat_response(PARSED),
        chat_response(ATS),
        chat_response(improved),
        chat_response({"headline": "React Native Developer | " + "x" * 300, "about": "I build."}),
    ]
    _, user = make_user(client, migrated_database, "a@example.com")
    upload = _upload_pdf(client, user)
    version_id = upload["version"]["id"]

    # parse
    assert _work(app, settings, upload["task_id"], tmp_path) is Outcome.SUCCEEDED
    detail = client.get(f"{API}/versions/{version_id}", headers=user).json()
    assert detail["parse_status"] == "parsed"
    assert detail["parsed"]["experience"][0]["company"] == "Acme Apps"
    assert detail["active_tasks"] == []

    # ATS
    task_id = client.post(f"{API}/versions/{version_id}/ats", headers=user).json()["task_id"]
    assert _work(app, settings, task_id, tmp_path) is Outcome.SUCCEEDED
    report = client.get(f"{API}/versions/{version_id}", headers=user).json()["ats_report"]
    assert report["ats_score"] == 72
    assert report["section_scores"]["keywords"] == 65
    assert report["prompt_version"] == "resume_ats.v1"
    assert client.get(API, headers=user).json()["versions"][0]["ats_score"] == 72

    # improved resume → new version, PDF stored, original untouched
    task_id = client.post(f"{API}/versions/{version_id}/improve", headers=user).json()["task_id"]
    assert _work(app, settings, task_id, tmp_path) is Outcome.SUCCEEDED
    task = client.get(f"/api/v1/tasks/{task_id}", headers=user).json()
    assert client.get(task["result"]["file"]["download_url"]).content == FAKE_PDF
    versions = client.get(API, headers=user).json()["versions"]
    assert [(v["version_no"], v["kind"]) for v in versions] == [(2, "improved"), (1, "master")]
    assert versions[0]["derived_from_id"] == version_id
    assert versions[1]["is_active"] is True
    new = client.get(f"{API}/versions/{versions[0]['id']}", headers=user).json()
    assert new["parsed"]["email"] == "asha@example.com"
    assert new["parsed"]["headline"] == "React Native Developer"
    assert new["parsed"]["summary"].startswith("React Native developer with 4 years")

    # LinkedIn summary, headline cut to 220 characters
    task_id = client.post(f"{API}/versions/{version_id}/linkedin-summary", headers=user).json()[
        "task_id"
    ]
    assert _work(app, settings, task_id, tmp_path) is Outcome.SUCCEEDED
    report = client.get(f"{API}/versions/{version_id}", headers=user).json()["ats_report"]
    assert len(report["linkedin_summary"]["headline"]) == 220
    assert report["linkedin_summary"]["about"] == "I build."
    (calls,) = db(migrated_database, "SELECT count(*) FROM ai_calls")[0]
    assert calls == 4


@respx.mock
def test_improve_retries_once_then_refuses_invented_facts(
    app: FastAPI, client: TestClient, migrated_database: str, settings: Settings, tmp_path: Path
) -> None:
    invented = copy.deepcopy(PARSED)
    invented["experience"][0]["company"] = "Google"
    respx.post(AI_URL).side_effect = [
        chat_response(PARSED),
        chat_response(ATS),
        chat_response(invented),
        chat_response(invented),
    ]
    _, user = make_user(client, migrated_database, "a@example.com")
    upload = _upload_pdf(client, user)
    version_id = upload["version"]["id"]
    _work(app, settings, upload["task_id"], tmp_path)
    ats = client.post(f"{API}/versions/{version_id}/ats", headers=user).json()["task_id"]
    _work(app, settings, ats, tmp_path)

    task_id = client.post(f"{API}/versions/{version_id}/improve", headers=user).json()["task_id"]
    outcome = _work(app, settings, task_id, tmp_path)

    assert outcome is Outcome.FAILED
    task = client.get(f"/api/v1/tasks/{task_id}", headers=user).json()
    assert "Google" in task["error"]
    assert len(client.get(API, headers=user).json()["versions"]) == 1  # nothing saved
    assert respx.calls.call_count == 4


@respx.mock
def test_parse_failure_is_shown_on_the_version_and_can_be_retried(
    app: FastAPI, client: TestClient, migrated_database: str, settings: Settings, tmp_path: Path
) -> None:
    respx.post(AI_URL).side_effect = [chat_response("not json"), chat_response("still not json")]
    _, user = make_user(client, migrated_database, "a@example.com")
    upload = _upload_pdf(client, user)
    version_id = upload["version"]["id"]
    db(migrated_database, "UPDATE tasks SET attempts = 3")  # pretend this is the last attempt

    assert _work(app, settings, upload["task_id"], tmp_path) is Outcome.FAILED

    detail = client.get(f"{API}/versions/{version_id}", headers=user).json()
    assert detail["parse_status"] == "failed"
    assert detail["parse_error"] == "The AI returned an invalid answer."
    retry = client.post(f"{API}/versions/{version_id}/parse", headers=user)
    assert retry.status_code == 202
