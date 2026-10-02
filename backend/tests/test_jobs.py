"""Phase 8 over HTTP + worker: job search, dedupe, job list, saved searches, scheduler."""

import asyncio
import uuid
from datetime import UTC, datetime
from pathlib import Path

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.core.config import Settings
from app.core.errors import ExternalServiceError
from app.db.session import create_engine, create_session_factory
from app.integrations.jsearch import JobSourceConfigError
from app.services.saved_searches import dispatch_due_searches
from app.services.tasks import RecordingDispatcher
from app.workers.runner import Outcome, run_task
from tests.fakes import FakeJobSource, fake_services, make_job
from tests.helpers import db, make_user

API = "/api/v1/jobs"
SAVED = "/api/v1/saved-searches"


def _work(
    app: FastAPI, settings: Settings, task_id: str, tmp_path: Path, source: FakeJobSource
) -> Outcome:
    async def go() -> Outcome:
        engine = create_engine(settings)
        services = fake_services(settings, tmp_path, storage=app.state.storage, job_source=source)
        result = await run_task(
            uuid.UUID(task_id),
            settings,
            services=services,
            session_factory=create_session_factory(engine),
        )
        await engine.dispose()
        return result.outcome

    return asyncio.run(go())


def _search(client: TestClient, headers: dict[str, str], **body: object) -> dict:
    response = client.post(
        f"{API}/search", json={"keywords": "React Native", **body}, headers=headers
    )
    assert response.status_code == 202, response.text
    return response.json()


def _search_and_run(
    app: FastAPI,
    client: TestClient,
    settings: Settings,
    tmp_path: Path,
    headers: dict[str, str],
    source: FakeJobSource,
    **body: object,
) -> dict:
    started = _search(client, headers, **body)
    assert _work(app, settings, started["task_id"], tmp_path, source) is Outcome.SUCCEEDED
    return client.get(f"{API}/searches/{started['run_id']}", headers=headers).json()


# ---------- search ----------


def test_search_is_queued_with_its_parameters(
    app: FastAPI, client: TestClient, migrated_database: str
) -> None:
    _, user = make_user(client, migrated_database, "a@example.com")

    started = _search(
        client, user, location=" Hyderabad ", experience="under_3_years_experience", country="IN"
    )

    run = client.get(f"{API}/searches/{started['run_id']}", headers=user).json()
    assert run["status"] == "queued"
    assert run["task_id"] == started["task_id"]
    assert run["query"]["location"] == "Hyderabad"
    assert run["query"]["country"] == "in"
    assert run["query"]["num_pages"] == 1
    assert app.state.dispatcher.sent == [(uuid.UUID(started["task_id"]), "job_search")]


def test_search_stores_jobs_and_rerun_creates_no_duplicates(
    app: FastAPI, client: TestClient, migrated_database: str, settings: Settings, tmp_path: Path
) -> None:
    _, user = make_user(client, migrated_database, "a@example.com")
    source = FakeJobSource([make_job(1), make_job(2), make_job(3)])

    first = _search_and_run(app, client, settings, tmp_path, user, source, location="Hyderabad")
    second = _search_and_run(app, client, settings, tmp_path, user, source, location="Hyderabad")

    assert source.queries[0].text() == "React Native in Hyderabad"
    assert (first["status"], first["results_count"], first["new_jobs_count"]) == ("succeeded", 3, 3)
    assert (second["results_count"], second["new_jobs_count"]) == (3, 0)
    assert [job["title"] for job in second["jobs"]] == [
        "React Native Developer 1",
        "React Native Developer 2",
        "React Native Developer 3",
    ]
    assert client.get(API, headers=user).json()["total"] == 3
    (count,) = db(migrated_database, "SELECT count(*) FROM jobs")[0]
    assert count == 3


def test_same_job_from_another_listing_is_linked_as_duplicate(
    app: FastAPI, client: TestClient, migrated_database: str, settings: Settings, tmp_path: Path
) -> None:
    _, user = make_user(client, migrated_database, "a@example.com")
    original = make_job(1)
    repost = make_job(99, title="REACT NATIVE  developer 1", company="company 1")  # other id

    run = _search_and_run(app, client, settings, tmp_path, user, FakeJobSource([original, repost]))

    assert run["results_count"] == 1
    rows = db(
        migrated_database,
        "SELECT external_id, status, duplicate_of_id IS NOT NULL FROM jobs ORDER BY external_id",
    )
    assert rows == [("jsearch-1", "active", False), ("jsearch-99", "duplicate", True)]
    assert client.get(API, headers=user).json()["total"] == 1


def test_jobs_are_shared_but_each_user_has_their_own_list(
    app: FastAPI, client: TestClient, migrated_database: str, settings: Settings, tmp_path: Path
) -> None:
    _, alice = make_user(client, migrated_database, "alice@example.com")
    _, bob = make_user(client, migrated_database, "bob@example.com")
    source = FakeJobSource([make_job(1)])

    alice_run = _search_and_run(app, client, settings, tmp_path, alice, source)
    bob_run = _search_and_run(app, client, settings, tmp_path, bob, source)
    job_id = alice_run["jobs"][0]["id"]

    assert bob_run["new_jobs_count"] == 1  # new for Bob even though the job already existed
    assert bob_run["jobs"][0]["id"] == job_id  # stored once
    client.patch(f"{API}/{job_id}", json={"state": "skipped", "notes": "Alice only"}, headers=alice)
    bob_view = client.get(f"{API}/{job_id}", headers=bob).json()
    assert bob_view["state"] == "new" and bob_view["notes"] is None
    assert client.get(f"{API}/searches/{alice_run['id']}", headers=bob).status_code == 404
    assert client.get(f"{API}/searches", headers=bob).json()[0]["id"] == bob_run["id"]


def test_source_failure_marks_the_run_failed(
    app: FastAPI, client: TestClient, migrated_database: str, settings: Settings, tmp_path: Path
) -> None:
    _, user = make_user(client, migrated_database, "a@example.com")
    started = _search(client, user)
    source = FakeJobSource(
        error=JobSourceConfigError("JSearch quota reached.", code="JSEARCH_QUOTA")
    )

    assert _work(app, settings, started["task_id"], tmp_path, source) is Outcome.FAILED

    run = client.get(f"{API}/searches/{started['run_id']}", headers=user).json()
    assert run["status"] == "failed"
    assert run["error"] == "JSearch quota reached."


def test_temporary_source_outage_is_retried(
    app: FastAPI, client: TestClient, migrated_database: str, settings: Settings, tmp_path: Path
) -> None:
    _, user = make_user(client, migrated_database, "a@example.com")
    started = _search(client, user)
    source = FakeJobSource(error=ExternalServiceError("JSearch is unreachable."))

    assert _work(app, settings, started["task_id"], tmp_path, source) is Outcome.RETRY
    assert (
        client.get(f"{API}/searches/{started['run_id']}", headers=user).json()["status"]
        == "running"
    )


def test_search_request_is_validated(client: TestClient, migrated_database: str) -> None:
    _, user = make_user(client, migrated_database, "a@example.com")

    assert client.post(f"{API}/search", json={"keywords": "x"}, headers=user).status_code == 422
    bad_country = {"keywords": "React", "country": "india"}
    assert client.post(f"{API}/search", json=bad_country, headers=user).status_code == 422
    bad_experience = {"keywords": "React", "experience": "lots"}
    assert client.post(f"{API}/search", json=bad_experience, headers=user).status_code == 422


# ---------- job list ----------


def test_filters_and_sorting(
    app: FastAPI, client: TestClient, migrated_database: str, settings: Settings, tmp_path: Path
) -> None:
    _, user = make_user(client, migrated_database, "a@example.com")
    jobs = [
        make_job(1, company="Zeta", location="Pune, IN", city="Pune"),
        make_job(2, company="Alpha", is_remote=True),
        make_job(10, company="Beta", title="Flutter Developer"),
    ]
    run = _search_and_run(app, client, settings, tmp_path, user, FakeJobSource(jobs))
    ids = {job["company"]: job["id"] for job in run["jobs"]}

    def companies(query: str = "") -> list[str]:
        body = client.get(f"{API}?{query}", headers=user).json()
        return [job["company"] for job in body["items"]]

    assert companies() == ["Zeta", "Alpha", "Beta"]  # newest posting first
    assert companies("sort=company") == ["Alpha", "Beta", "Zeta"]
    assert companies("q=flutter") == ["Beta"]
    assert companies("q=%25") == []  # LIKE wildcards are literal
    assert companies("location=pune") == ["Zeta"]
    assert companies("remote_only=true") == ["Alpha"]
    assert companies("posted_within_days=3") == ["Zeta", "Alpha"]

    client.patch(f"{API}/{ids['Zeta']}", json={"state": "skipped"}, headers=user)
    client.patch(f"{API}/{ids['Alpha']}", json={"state": "saved"}, headers=user)
    assert companies() == ["Alpha", "Beta"]  # skipped jobs leave the main list
    assert companies("state=skipped") == ["Zeta"]
    assert companies("state=saved") == ["Alpha"]
    counts = client.get(f"{API}/counts", headers=user).json()
    assert (counts["new"], counts["saved"], counts["skipped"]) == (1, 1, 1)

    page = client.get(f"{API}?page=2&page_size=1", headers=user).json()
    assert (page["total"], len(page["items"])) == (2, 1)


def test_pasted_description_makes_a_partial_job_usable(
    app: FastAPI, client: TestClient, migrated_database: str, settings: Settings, tmp_path: Path
) -> None:
    _, user = make_user(client, migrated_database, "a@example.com")
    run = _search_and_run(
        app, client, settings, tmp_path, user, FakeJobSource([make_job(1, description="Apply now")])
    )
    job_id = run["jobs"][0]["id"]
    assert run["jobs"][0]["description_quality"] == "missing"

    pasted = client.patch(
        f"{API}/{job_id}",
        json={"description": "Responsibilities: build apps. Requirements: React. " * 20},
        headers=user,
    ).json()

    assert pasted["description_quality"] == "complete"
    assert pasted["has_own_description"] is True
    cleared = client.patch(f"{API}/{job_id}", json={"description": ""}, headers=user).json()
    assert cleared["description"] == "Apply now"
    assert cleared["description_quality"] == "missing"


def test_fetch_description_preconditions(
    app: FastAPI, client: TestClient, migrated_database: str, settings: Settings, tmp_path: Path
) -> None:
    _, user = make_user(client, migrated_database, "a@example.com")
    jobs = [
        make_job(1),
        make_job(2, description="short"),
        make_job(3, apply_url=None, description=""),
    ]
    run = _search_and_run(app, client, settings, tmp_path, user, FakeJobSource(jobs))
    by_title = {job["title"][-1]: job["id"] for job in run["jobs"]}

    complete = client.post(f"{API}/{by_title['1']}/fetch-description", headers=user)
    no_link = client.post(f"{API}/{by_title['3']}/fetch-description", headers=user)
    first = client.post(f"{API}/{by_title['2']}/fetch-description", headers=user)
    again = client.post(f"{API}/{by_title['2']}/fetch-description", headers=user)

    assert complete.json()["error"]["code"] == "ALREADY_COMPLETE"
    assert no_link.json()["error"]["code"] == "NO_APPLY_URL"
    assert first.status_code == 202 and first.json() == again.json()  # no duplicate task
    detail = client.get(f"{API}/{by_title['2']}", headers=user).json()
    assert [t["type"] for t in detail["active_tasks"]] == ["job_fetch_page"]


def test_unknown_jobs_are_404(client: TestClient, migrated_database: str) -> None:
    _, user = make_user(client, migrated_database, "a@example.com")
    missing = uuid.uuid4()

    assert client.get(f"{API}/{missing}", headers=user).status_code == 404
    assert (
        client.patch(f"{API}/{missing}", json={"state": "saved"}, headers=user).status_code == 404
    )
    assert client.get(f"{API}/searches/{missing}", headers=user).status_code == 404


def test_suggested_roles_come_from_the_active_resume(
    client: TestClient, migrated_database: str
) -> None:
    user_id, user = make_user(client, migrated_database, "a@example.com")

    empty = client.get(f"{API}/suggested-roles", headers=user).json()
    assert empty["roles"] == [] and "Upload a resume" in empty["hint"]

    client.put(
        "/api/v1/users/me/profile",
        json={"location": "Hyderabad", "links": {}, "timezone": "Asia/Kolkata"},
        headers=user,
    )
    db(migrated_database, "INSERT INTO resumes (user_id) VALUES (:u)", u=user_id)
    db(
        migrated_database,
        "INSERT INTO resume_versions (user_id, resume_id, version_no, kind, file_key, file_name,"
        " mime_type, file_size) SELECT :u, id, 1, 'master', 'k', 'cv.pdf', 'application/pdf', 1"
        " FROM resumes WHERE user_id = :u",
        u=user_id,
    )
    db(
        migrated_database,
        "UPDATE resumes SET active_version_id ="
        " (SELECT id FROM resume_versions WHERE user_id = :u)",
        u=user_id,
    )
    db(
        migrated_database,
        "INSERT INTO resume_ats_reports (user_id, resume_version_id, ats_score, section_scores,"
        " strengths, missing_skills, top_roles, suggestions, model, prompt_version)"
        " SELECT :u, id, 70, '{}', '[]', '[]', '[\"Mobile Engineer\", \"React Native Developer\"]',"
        " '[]', 'm', 'v' FROM resume_versions WHERE user_id = :u",
        u=user_id,
    )

    body = client.get(f"{API}/suggested-roles", headers=user).json()
    assert body == {
        "roles": ["Mobile Engineer", "React Native Developer"],
        "location": "Hyderabad",
        "hint": None,
    }


# ---------- saved searches ----------


def test_saved_search_crud_and_validation(client: TestClient, migrated_database: str) -> None:
    _, user = make_user(client, migrated_database, "a@example.com")
    body = {"name": "RN Hyderabad", "keywords": "React Native", "location": "Hyderabad"}

    created = client.post(SAVED, json=body, headers=user)
    too_often = client.post(SAVED, json={**body, "schedule_cron": "*/10 * * * *"}, headers=user)
    nonsense = client.post(SAVED, json={**body, "schedule_cron": "every day"}, headers=user)

    assert created.status_code == 201
    saved = created.json()
    assert saved["schedule_cron"] == "0 8 * * *" and saved["is_active"] is True
    assert saved["next_run_at"] is not None
    assert too_often.status_code == nonsense.status_code == 422
    assert too_often.json()["error"]["code"] == "INVALID_SCHEDULE"

    paused = client.patch(f"{SAVED}/{saved['id']}", json={"is_active": False}, headers=user).json()
    assert paused["is_active"] is False and paused["next_run_at"] is None
    renamed = client.patch(
        f"{SAVED}/{saved['id']}", json={"name": "RN", "schedule_cron": "30 9 * * 1-5"}, headers=user
    ).json()
    assert (renamed["name"], renamed["schedule_cron"]) == ("RN", "30 9 * * 1-5")

    assert client.delete(f"{SAVED}/{saved['id']}", headers=user).status_code == 204
    assert client.get(SAVED, headers=user).json() == []


def test_active_saved_searches_are_limited(
    client: TestClient, migrated_database: str, settings: Settings
) -> None:
    _, user = make_user(client, migrated_database, "a@example.com")
    body = {"name": "s", "keywords": "React Native"}
    for _ in range(settings.max_active_saved_searches):
        assert client.post(SAVED, json=body, headers=user).status_code == 201

    over = client.post(SAVED, json=body, headers=user)
    paused = client.post(SAVED, json={**body, "is_active": False}, headers=user)

    assert over.status_code == 429
    assert over.json()["error"]["code"] == "SAVED_SEARCH_LIMIT"
    assert paused.status_code == 201  # paused searches do not count


def test_saved_searches_are_private(client: TestClient, migrated_database: str) -> None:
    _, alice = make_user(client, migrated_database, "alice@example.com")
    _, bob = make_user(client, migrated_database, "bob@example.com")
    saved_id = client.post(SAVED, json={"name": "a", "keywords": "React"}, headers=alice).json()[
        "id"
    ]

    assert client.get(SAVED, headers=bob).json() == []
    assert client.patch(f"{SAVED}/{saved_id}", json={"name": "x"}, headers=bob).status_code == 404
    assert client.post(f"{SAVED}/{saved_id}/run", headers=bob).status_code == 404
    assert client.delete(f"{SAVED}/{saved_id}", headers=bob).status_code == 404


def test_saved_search_run_notifies_only_about_new_jobs(
    app: FastAPI, client: TestClient, migrated_database: str, settings: Settings, tmp_path: Path
) -> None:
    _, user = make_user(client, migrated_database, "a@example.com")
    saved_id = client.post(
        SAVED, json={"name": "RN Hyderabad", "keywords": "React Native"}, headers=user
    ).json()["id"]
    source = FakeJobSource([make_job(1), make_job(2)])

    for _ in range(2):
        started = client.post(f"{SAVED}/{saved_id}/run", headers=user).json()
        assert _work(app, settings, started["task_id"], tmp_path, source) is Outcome.SUCCEEDED

    notes = client.get("/api/v1/notifications", headers=user).json()["items"]
    assert [n["title"] for n in notes] == ["2 new jobs for “RN Hyderabad”"]
    assert notes[0]["link"].startswith("/jobs/searches/")
    runs = client.get(f"{API}/searches", headers=user).json()
    assert [r["saved_search_id"] for r in runs] == [saved_id, saved_id]


def test_scheduler_starts_only_due_searches(
    client: TestClient, migrated_database: str, settings: Settings
) -> None:
    user_id, user = make_user(client, migrated_database, "a@example.com")
    pending_id, _ = make_user(client, migrated_database, "p@example.com", approval="pending")
    client.put(
        "/api/v1/users/me/profile",
        json={"links": {}, "timezone": "Asia/Kolkata"},
        headers=user,
    )
    created = datetime(2026, 10, 1, 0, 0, tzinfo=UTC)
    insert = (
        "INSERT INTO saved_searches (user_id, name, keywords, is_active, created_at)"
        " VALUES (:u, :n, 'React Native', :a, :c)"
    )
    db(migrated_database, insert, u=user_id, n="daily", a=True, c=created)
    db(migrated_database, insert, u=user_id, n="paused", a=False, c=created)
    db(migrated_database, insert, u=pending_id, n="pending user", a=True, c=created)

    def tick(now: datetime) -> tuple[int, RecordingDispatcher]:
        async def go() -> tuple[int, RecordingDispatcher]:
            dispatcher = RecordingDispatcher()
            engine = create_engine(settings)
            async with create_session_factory(engine)() as session:
                started = await dispatch_due_searches(session, settings, dispatcher, now)
            await engine.dispose()
            return started, dispatcher

        return asyncio.run(go())

    # 08:00 IST on 2026-10-01 is 02:30 UTC.
    assert tick(datetime(2026, 10, 1, 2, 29, tzinfo=UTC))[0] == 0
    started, dispatcher = tick(datetime(2026, 10, 1, 2, 31, tzinfo=UTC))
    assert started == 1  # only the approved user's active search
    assert [kind for _, kind in dispatcher.sent] == ["job_search"]
    assert tick(datetime(2026, 10, 1, 2, 36, tzinfo=UTC))[0] == 0  # not twice
    assert tick(datetime(2026, 10, 2, 2, 31, tzinfo=UTC))[0] == 1  # next day
    assert db(migrated_database, "SELECT count(*) FROM job_search_runs")[0][0] == 2


# ---------- admin change requests: labels, load more, pages, CSV ----------


def test_results_say_which_jobs_are_new(
    app: FastAPI, client: TestClient, migrated_database: str, settings: Settings, tmp_path: Path
) -> None:
    _, user = make_user(client, migrated_database, "a@example.com")
    _search_and_run(
        app, client, settings, tmp_path, user, FakeJobSource([make_job(1), make_job(2)])
    )

    rerun = _search_and_run(
        app, client, settings, tmp_path, user, FakeJobSource([make_job(2), make_job(3)])
    )

    assert [(job["title"][-1], job["is_new"]) for job in rerun["jobs"]] == [
        ("2", False),  # already in the list
        ("3", True),
    ]
    assert (rerun["results_count"], rerun["new_jobs_count"]) == (2, 1)


def test_load_more_appends_the_next_page(
    app: FastAPI, client: TestClient, migrated_database: str, settings: Settings, tmp_path: Path
) -> None:
    _, user = make_user(client, migrated_database, "a@example.com")
    first = _search_and_run(
        app, client, settings, tmp_path, user, FakeJobSource([make_job(n) for n in range(1, 11)])
    )
    assert (first["pages_loaded"], first["can_load_more"]) == (1, True)

    more = client.post(f"{API}/searches/{first['id']}/more", headers=user)
    assert more.status_code == 202
    assert client.get(f"{API}/searches/{first['id']}", headers=user).json()["status"] == "queued"
    page_two = FakeJobSource([make_job(10), make_job(11), make_job(12)])  # 10 repeats
    assert _work(app, settings, more.json()["task_id"], tmp_path, page_two) is Outcome.SUCCEEDED

    run = client.get(f"{API}/searches/{first['id']}", headers=user).json()
    assert (page_two.queries[0].page, page_two.queries[0].num_pages) == (2, 1)
    assert (run["results_count"], run["new_jobs_count"]) == (12, 12)
    assert [job["title"].split()[-1] for job in run["jobs"]][-3:] == ["10", "11", "12"]
    assert (run["pages_loaded"], run["can_load_more"]) == (2, False)  # short page → done
    again = client.post(f"{API}/searches/{first['id']}/more", headers=user)
    assert again.json()["error"]["code"] == "NO_MORE_RESULTS"


def test_load_more_while_running_returns_the_same_task(
    client: TestClient, migrated_database: str
) -> None:
    _, user = make_user(client, migrated_database, "a@example.com")
    started = _search(client, user)

    more = client.post(f"{API}/searches/{started['run_id']}/more", headers=user).json()

    assert more["task_id"] == started["task_id"]


def test_pages_can_be_chosen_up_to_three(
    app: FastAPI, client: TestClient, migrated_database: str, settings: Settings, tmp_path: Path
) -> None:
    _, user = make_user(client, migrated_database, "a@example.com")
    source = FakeJobSource([make_job(1)])

    run = _search_and_run(app, client, settings, tmp_path, user, source, num_pages=3)
    too_many = client.post(
        f"{API}/search", json={"keywords": "React", "num_pages": 4}, headers=user
    )

    assert (source.queries[0].page, source.queries[0].num_pages) == (1, 3)
    assert run["pages_loaded"] == 3
    assert too_many.status_code == 422


def test_csv_export_follows_filters_and_is_excel_safe(
    app: FastAPI, client: TestClient, migrated_database: str, settings: Settings, tmp_path: Path
) -> None:
    _, user = make_user(client, migrated_database, "a@example.com")
    _, other = make_user(client, migrated_database, "b@example.com")
    jobs = [
        make_job(1, company='=HYPERLINK("http://evil")', salary_min=None),
        make_job(2, title="Développeur React Native ₹"),
    ]
    run = _search_and_run(app, client, settings, tmp_path, user, FakeJobSource(jobs))
    client.patch(
        f"{API}/{run['jobs'][1]['id']}", json={"state": "saved", "notes": "call Ravi"}, headers=user
    )

    everything = client.get(f"{API}/export.csv", headers=user)
    saved = client.get(f"{API}/export.csv?state=saved&include_description=true", headers=user)

    assert everything.status_code == 200
    assert everything.headers["content-type"].startswith("text/csv")
    assert 'filename="jobs-inbox-' in everything.headers["content-disposition"]
    text = everything.content.decode("utf-8")
    assert text.startswith("﻿Title,Company,Location,Remote")
    assert "Match score,Matching skills,Missing skills,Scored" in text.splitlines()[0]
    assert "'=HYPERLINK" in text  # formula neutralised
    assert "Développeur React Native ₹" in text
    assert len(text.strip().splitlines()) == 3  # header + 2 jobs

    saved_lines = saved.content.decode("utf-8").strip().splitlines()
    assert saved_lines[0].endswith("Job description")
    assert len(saved_lines) > 1 and "call Ravi" in saved.content.decode("utf-8")
    assert "Développeur" in saved_lines[1]
    assert "jobs-saved-" in saved.headers["content-disposition"]
    other_lines = (
        client.get(f"{API}/export.csv", headers=other).content.decode().strip().splitlines()
    )
    assert len(other_lines) == 1  # only the header: exports are private
