"""Phase 11: applications — state machine, history, one per job, mark applied, CSV."""

from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.core.config import Settings
from app.domain.state_machine import TransitionError, check, user_options
from app.models.enums import ApplicationChannel as C
from app.models.enums import ApplicationStatus as S
from app.models.enums import StatusChangeSource as Src
from tests.fakes import FakeJobSource, make_job
from tests.helpers import db, make_user
from tests.test_analysis import JD, _resume
from tests.test_jobs import _search_and_run

API = "/api/v1"


def _setup(app, client, url, settings, tmp_path, email="a@example.com", jobs=None):  # type: ignore[no-untyped-def]
    user_id, headers = make_user(client, url, email)
    version_id = _resume(url, user_id)
    run = _search_and_run(
        app,
        client,
        settings,
        tmp_path,
        headers,
        FakeJobSource(jobs or [make_job(1, description=JD)]),
    )
    return headers, [job["id"] for job in run["jobs"]], version_id


def _create(client, headers, job_id, **body):  # type: ignore[no-untyped-def]
    return client.post(f"{API}/jobs/{job_id}/applications", json=body, headers=headers)


def _move(client, headers, app_id, to, note=None):  # type: ignore[no-untyped-def]
    return client.post(
        f"{API}/applications/{app_id}/status", json={"to_status": to, "note": note}, headers=headers
    )


# ---------- state machine ----------


def test_state_machine_rules() -> None:
    check(S.READY_TO_APPLY, S.APPLIED, channel=C.PORTAL, source=Src.USER)
    check(S.APPLIED, S.INTERVIEW, channel=C.EMAIL, source=Src.EMAIL_REPLY)
    check(S.SENDING, S.APPLIED, channel=C.EMAIL, source=Src.SYSTEM)
    with pytest.raises(TransitionError, match="cannot go"):
        check(S.APPLIED, S.READY_TO_APPLY, channel=C.PORTAL, source=Src.USER)
    with pytest.raises(TransitionError, match="email sender"):
        check(S.APPROVED, S.SENDING, channel=C.EMAIL, source=Src.USER)
    with pytest.raises(TransitionError, match="only applies to email"):
        check(S.READY_TO_APPLY, S.WAITING_FOR_APPROVAL, channel=C.PORTAL, source=Src.USER)
    with pytest.raises(TransitionError, match="when the email is sent"):
        check(S.READY_TO_APPLY, S.APPLIED, channel=C.EMAIL, source=Src.USER)
    for terminal in (S.OFFER, S.REJECTED, S.WITHDRAWN):
        assert user_options(terminal, C.PORTAL) == []
    assert user_options(S.READY_TO_APPLY, C.PORTAL) == [S.APPLIED, S.WITHDRAWN]
    assert user_options(S.READY_TO_APPLY, C.EMAIL) == [S.WAITING_FOR_APPROVAL, S.WITHDRAWN]
    assert S.SENDING not in user_options(S.APPROVED, C.EMAIL)


# ---------- create ----------


def test_prepare_application_with_the_tailored_resume_by_default(
    app: FastAPI, client: TestClient, migrated_database: str, settings: Settings, tmp_path: Path
) -> None:
    user, (job_id,), master_id = _setup(app, client, migrated_database, settings, tmp_path)
    (tailored_id,) = db(
        migrated_database,
        "INSERT INTO resume_versions (user_id, resume_id, version_no, kind, job_id,"
        " derived_from_id, file_key, file_name, mime_type, file_size, parsed, parse_status)"
        " SELECT user_id, resume_id, 2, 'tailored', :j, id, 'k2', 'cv-acme.pdf',"
        " 'application/pdf', 1, parsed, 'parsed' FROM resume_versions WHERE id = :v RETURNING id",
        j=job_id,
        v=master_id,
    )[0]

    response = _create(client, user, job_id, channel="portal", next_action="Apply on the site")

    assert response.status_code == 201
    detail = response.json()
    assert (detail["status"], detail["channel"]) == ("ready_to_apply", "portal")
    assert detail["resume"]["id"] == str(tailored_id) and detail["resume"]["kind"] == "tailored"
    assert detail["next_action"] == "Apply on the site"
    assert detail["allowed_next"] == ["applied", "withdrawn"]
    assert [(h["from_status"], h["to_status"], h["source"]) for h in detail["history"]] == [
        (None, "ready_to_apply", "user")
    ]
    assert client.get(f"{API}/jobs/{job_id}/application", headers=user).json()["id"] == detail["id"]


def test_one_application_per_job(
    app: FastAPI, client: TestClient, migrated_database: str, settings: Settings, tmp_path: Path
) -> None:
    user, (job_id,), _ = _setup(app, client, migrated_database, settings, tmp_path)
    first = _create(client, user, job_id).json()

    second = _create(client, user, job_id)

    assert second.status_code == 409
    assert second.json()["error"]["code"] == "APPLICATION_EXISTS"
    assert second.json()["error"]["details"]["application_id"] == first["id"]


def test_documents_must_belong_to_the_job(
    app: FastAPI, client: TestClient, migrated_database: str, settings: Settings, tmp_path: Path
) -> None:
    jobs = [make_job(1, description=JD), make_job(2, description=JD)]
    user, (job_a, job_b), master_id = _setup(
        app, client, migrated_database, settings, tmp_path, jobs=jobs
    )
    (tailored_for_a,) = db(
        migrated_database,
        "INSERT INTO resume_versions (user_id, resume_id, version_no, kind, job_id, file_key,"
        " file_name, mime_type, file_size, parse_status) SELECT user_id, resume_id, 2, 'tailored',"
        " :j, 'k', 't.pdf', 'application/pdf', 1, 'parsed' FROM resume_versions WHERE id = :v"
        " RETURNING id",
        j=job_a,
        v=master_id,
    )[0]

    wrong = _create(client, user, job_b, resume_version_id=str(tailored_for_a))

    assert wrong.status_code == 422
    assert wrong.json()["error"]["code"] == "BAD_RESUME"


# ---------- lifecycle ----------


def test_portal_application_lifecycle_and_timeline(
    app: FastAPI, client: TestClient, migrated_database: str, settings: Settings, tmp_path: Path
) -> None:
    user, (job_id,), _ = _setup(app, client, migrated_database, settings, tmp_path)
    app_id = _create(client, user, job_id, channel="portal").json()["id"]

    applied = client.post(
        f"{API}/applications/{app_id}/mark-applied",
        json={"note": "Applied on careers page"},
        headers=user,
    ).json()
    interview = _move(client, user, app_id, "interview", "Call on Monday").json()
    offer = _move(client, user, app_id, "offer").json()

    assert applied["status"] == "applied" and applied["applied_at"] is not None
    assert interview["allowed_next"] == ["offer", "rejected", "withdrawn"]
    assert offer["allowed_next"] == []  # terminal
    timeline = [(h["from_status"], h["to_status"], h["note"]) for h in offer["history"]]
    assert timeline == [
        (None, "ready_to_apply", "Application prepared"),
        ("ready_to_apply", "applied", "Applied on careers page"),
        ("applied", "interview", "Call on Monday"),
        ("interview", "offer", None),
    ]
    (rows,) = db(migrated_database, "SELECT count(*) FROM application_status_history")[0]
    assert rows == 4


def test_invalid_moves_are_rejected(
    app: FastAPI, client: TestClient, migrated_database: str, settings: Settings, tmp_path: Path
) -> None:
    jobs = [make_job(1, description=JD), make_job(2, description=JD)]
    user, (job_a, job_b), _ = _setup(app, client, migrated_database, settings, tmp_path, jobs=jobs)
    portal = _create(client, user, job_a, channel="portal").json()["id"]
    email = _create(client, user, job_b, channel="email").json()["id"]

    skip_ahead = _move(client, user, portal, "offer")
    email_step = _move(client, user, portal, "waiting_for_approval")
    hand_sent = client.post(f"{API}/applications/{email}/mark-applied", headers=user)
    _move(client, user, email, "waiting_for_approval")
    _move(client, user, email, "approved")
    sending = _move(client, user, email, "sending")

    for response in (skip_ahead, email_step, hand_sent, sending):
        assert response.status_code == 409
        assert response.json()["error"]["code"] == "INVALID_TRANSITION"
    detail = client.get(f"{API}/applications/{email}", headers=user).json()
    assert detail["status"] == "approved"
    assert "sending" not in detail["allowed_next"]


def test_documents_lock_after_the_application_went_out(
    app: FastAPI, client: TestClient, migrated_database: str, settings: Settings, tmp_path: Path
) -> None:
    user, (job_id,), master_id = _setup(app, client, migrated_database, settings, tmp_path)
    app_id = _create(client, user, job_id, channel="portal").json()["id"]

    before = client.patch(
        f"{API}/applications/{app_id}", json={"resume_version_id": master_id}, headers=user
    )
    client.post(f"{API}/applications/{app_id}/mark-applied", headers=user)
    note = client.patch(
        f"{API}/applications/{app_id}", json={"next_action": "Follow up"}, headers=user
    )
    locked = client.patch(f"{API}/applications/{app_id}", json={"channel": "email"}, headers=user)

    assert before.status_code == 200 and before.json()["resume"]["id"] == master_id
    assert note.json()["next_action"] == "Follow up"
    assert locked.json()["error"]["code"] == "APPLICATION_LOCKED"


# ---------- list, counts, export, privacy ----------


def test_list_filters_counts_and_csv(
    app: FastAPI, client: TestClient, migrated_database: str, settings: Settings, tmp_path: Path
) -> None:
    jobs = [make_job(1, description=JD), make_job(2, description=JD, company="=cmd|evil")]
    user, (job_a, job_b), _ = _setup(app, client, migrated_database, settings, tmp_path, jobs=jobs)
    a = _create(client, user, job_a, channel="portal").json()["id"]
    _create(client, user, job_b, channel="referral")
    client.post(f"{API}/applications/{a}/mark-applied", headers=user)

    applied = client.get(f"{API}/applications?status=applied", headers=user).json()
    open_ = client.get(
        f"{API}/applications?status=ready_to_apply&status=applied", headers=user
    ).json()
    counts = client.get(f"{API}/applications/counts", headers=user).json()
    csv = client.get(f"{API}/applications/export.csv", headers=user)

    assert [item["id"] for item in applied["items"]] == [a]
    assert open_["total"] == 2
    assert (counts["counts"]["applied"], counts["counts"]["ready_to_apply"], counts["total"]) == (
        1,
        1,
        2,
    )
    text = csv.content.decode("utf-8")
    assert text.startswith("﻿Job,Company,Location,Channel,Status")
    assert "'=cmd|evil" in text  # formula neutralised
    assert ",portal,applied," in text and ",referral,ready_to_apply," in text
    assert 'filename="applications-' in csv.headers["content-disposition"]


def test_applications_are_private(
    app: FastAPI, client: TestClient, migrated_database: str, settings: Settings, tmp_path: Path
) -> None:
    alice, (job_id,), _ = _setup(app, client, migrated_database, settings, tmp_path)
    _, bob = make_user(client, migrated_database, "bob@example.com")
    app_id = _create(client, alice, job_id).json()["id"]

    assert client.get(f"{API}/applications/{app_id}", headers=bob).status_code == 404
    assert _move(client, bob, app_id, "withdrawn").status_code == 404
    assert client.get(f"{API}/applications", headers=bob).json()["total"] == 0
    assert client.get(f"{API}/jobs/{job_id}/application", headers=bob).json() is None
    assert _create(client, bob, job_id).status_code == 201  # Bob can apply to the same job
