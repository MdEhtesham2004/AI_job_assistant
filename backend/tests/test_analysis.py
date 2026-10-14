"""Phase 9: on-demand match scores, batch scoring, Scan (pasted JD), CSV score columns."""

import json
from pathlib import Path

import respx
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.core.config import Settings
from app.domain.scoring import decide, grounded, weighted_score
from app.models.enums import AnalysisDecision
from app.prompts.jobs import MATCH_VERSION
from app.workers.runner import Outcome
from tests.fakes import FakeJobSource, chat_response, make_job
from tests.helpers import db, make_user
from tests.resume_samples import PARSED, RESUME_LINES
from tests.test_jobs import _search_and_run, _work

API = "/api/v1/jobs"
AI_URL = "https://ai.test/v1/chat/completions"

MATCH = {
    "skills_match": 80,
    "experience_match": 80,
    "technology_match": 60,
    "education_match": 100,
    "location_match": 100,
    "matched_skills": ["React Native", "Kubernetes"],  # Kubernetes is not in the resume
    "missing_skills": ["GraphQL", "COBOL"],  # COBOL is not in the job
    "seniority_fit": "good",
    "recommendations": ["Mention the payments app."],
    "red_flags": [],
}
JD = (
    "Responsibilities: build React Native apps with TypeScript. "
    "Requirements: 3+ years of experience, GraphQL, Redux and Jest. " * 8
)


def _resume(url: str, user_id: str, *, version_no: int = 1, parsed: dict | None = None) -> str:
    """An active, parsed resume version for the user (no AI needed)."""
    if version_no == 1:
        db(url, "INSERT INTO resumes (user_id) VALUES (:u)", u=user_id)
    (version_id,) = db(
        url,
        "INSERT INTO resume_versions (user_id, resume_id, version_no, kind, file_key, file_name,"
        " mime_type, file_size, text_content, parsed, parse_status)"
        " SELECT :u, id, :n, 'master', 'k', 'cv.pdf', 'application/pdf', 1, :t,"
        " CAST(:p AS jsonb), 'parsed' FROM resumes WHERE user_id = :u RETURNING id",
        u=user_id,
        n=version_no,
        t="\n".join(RESUME_LINES),
        p=json.dumps(parsed or PARSED),
    )[0]
    db(url, "UPDATE resumes SET active_version_id = :v WHERE user_id = :u", v=version_id, u=user_id)
    return str(version_id)


def _setup(app, client, url, settings, tmp_path, email="a@example.com", jobs=None):  # type: ignore[no-untyped-def]
    user_id, headers = make_user(client, url, email)
    _resume(url, user_id)
    run = _search_and_run(
        app,
        client,
        settings,
        tmp_path,
        headers,
        FakeJobSource(jobs or [make_job(1, description=JD)]),
    )
    return user_id, headers, [job["id"] for job in run["jobs"]]


def _score(app, client, settings, tmp_path, headers, job_id, **body):  # type: ignore[no-untyped-def]
    started = client.post(f"{API}/{job_id}/analyze", json=body or None, headers=headers).json()
    if started["task_id"]:
        assert (
            _work(app, settings, started["task_id"], tmp_path, FakeJobSource()) is Outcome.SUCCEEDED
        )
    return started


# ---------- rules ----------


def test_weighted_score_and_decision() -> None:
    components = {
        "skills": 80,
        "experience": 80,
        "technology": 60,
        "education": 100,
        "location": 100,
    }

    assert weighted_score(components, {}) == 79  # default weights 40/25/20/10/5
    assert (
        weighted_score(
            components,
            {"skills": 100, "experience": 0, "technology": 0, "education": 0, "location": 0},
        )
        == 80
    )
    assert decide(85, 85, 65) is AnalysisDecision.USE_MASTER
    assert decide(84, 85, 65) is AnalysisDecision.TAILOR
    assert decide(64, 85, 65) is AnalysisDecision.SKIP


def test_grounded_keeps_only_real_items() -> None:
    assert grounded(["React Native", "react native", "Go"], "I use React Native daily", 5) == [
        "React Native"
    ]


# ---------- one job ----------


@respx.mock
def test_score_one_job_on_demand_and_cache_it(
    app: FastAPI, client: TestClient, migrated_database: str, settings: Settings, tmp_path: Path
) -> None:
    route = respx.post(AI_URL).mock(return_value=chat_response(MATCH))
    _, user, (job_id,) = _setup(app, client, migrated_database, settings, tmp_path)
    assert route.call_count == 0  # searching never scores

    first = _score(app, client, settings, tmp_path, user, job_id)
    detail = client.get(f"{API}/{job_id}", headers=user).json()

    assert first["cached"] is False
    analysis = detail["analysis"]
    assert detail["match_score"] == analysis["match_score"] == 79
    assert detail["decision"] == analysis["decision"] == "tailor"
    assert analysis["component_scores"]["technology"] == 60
    assert analysis["weights_used"] == {
        "skills": 40,
        "experience": 25,
        "technology": 20,
        "education": 10,
        "location": 5,
    }
    assert analysis["matched_skills"] == ["React Native"]  # invented skill dropped
    assert analysis["missing_skills"] == ["GraphQL"]  # not in the job → dropped
    assert analysis["prompt_version"] == MATCH_VERSION
    assert detail["state"] == "analyzed"

    again = client.post(f"{API}/{job_id}/analyze", headers=user).json()
    assert again == {"task_id": None, "cached": True}
    assert route.call_count == 1  # cached: no second AI call
    forced = _score(app, client, settings, tmp_path, user, job_id, force=True)
    assert forced["cached"] is False and route.call_count == 2
    (rows,) = db(migrated_database, "SELECT count(*) FROM job_analyses")[0]
    assert rows == 1  # re-analysis replaces, one row per job + resume version


@respx.mock
def test_thresholds_come_from_settings_and_saved_jobs_stay_saved(
    app: FastAPI, client: TestClient, migrated_database: str, settings: Settings, tmp_path: Path
) -> None:
    respx.post(AI_URL).mock(return_value=chat_response(MATCH))
    _, user, (job_id,) = _setup(app, client, migrated_database, settings, tmp_path)
    client.patch(
        "/api/v1/users/me/settings",
        json={"threshold_use_master": 75, "threshold_tailor": 50},
        headers=user,
    )
    client.patch(f"{API}/{job_id}", json={"state": "saved"}, headers=user)

    _score(app, client, settings, tmp_path, user, job_id)

    detail = client.get(f"{API}/{job_id}", headers=user).json()
    assert detail["decision"] == "use_master"
    assert detail["state"] == "saved"


def test_scoring_needs_a_resume_and_a_description(
    app: FastAPI, client: TestClient, migrated_database: str, settings: Settings, tmp_path: Path
) -> None:
    user_id, user = make_user(client, migrated_database, "a@example.com")
    run = _search_and_run(
        app, client, settings, tmp_path, user, FakeJobSource([make_job(1, description="Apply")])
    )
    job_id = run["jobs"][0]["id"]

    no_resume = client.post(f"{API}/{job_id}/analyze", headers=user)
    _resume(migrated_database, user_id)
    no_description = client.post(f"{API}/{job_id}/analyze", headers=user)

    assert no_resume.status_code == 409
    assert no_resume.json()["error"]["code"] == "RESUME_REQUIRED"
    assert no_description.json()["error"]["code"] == "DESCRIPTION_MISSING"
    client.patch(f"{API}/{job_id}", json={"description": JD}, headers=user)  # pasted JD fixes it
    assert client.post(f"{API}/{job_id}/analyze", headers=user).status_code == 200


@respx.mock
def test_scores_for_an_older_resume_are_marked_stale(
    app: FastAPI, client: TestClient, migrated_database: str, settings: Settings, tmp_path: Path
) -> None:
    respx.post(AI_URL).mock(return_value=chat_response(MATCH))
    user_id, user, (job_id,) = _setup(app, client, migrated_database, settings, tmp_path)
    _score(app, client, settings, tmp_path, user, job_id)

    _resume(migrated_database, user_id, version_no=2)  # new active version

    item = client.get(API, headers=user).json()["items"][0]
    assert (item["match_score"], item["score_stale"]) == (79, True)
    assert client.get(f"{API}?min_score=50", headers=user).json()["total"] == 0  # stale ignored
    assert client.post(f"{API}/{job_id}/analyze", headers=user).json()["cached"] is False


# ---------- many jobs ----------


@respx.mock
def test_score_all_saved_jobs(
    app: FastAPI, client: TestClient, migrated_database: str, settings: Settings, tmp_path: Path
) -> None:
    respx.post(AI_URL).mock(return_value=chat_response(MATCH))
    jobs = [make_job(1, description=JD), make_job(2, description=JD), make_job(3, description="x")]
    _, user, ids = _setup(app, client, migrated_database, settings, tmp_path, jobs=jobs)
    for job_id in ids:
        client.patch(f"{API}/{job_id}", json={"state": "saved"}, headers=user)
    _score(app, client, settings, tmp_path, user, ids[0])

    summary = client.get(f"{API}/analysis-summary?state=saved", headers=user).json()
    started = client.post(f"{API}/analyze-batch?state=saved", headers=user).json()

    assert summary == {"to_score": 1, "already_scored": 1, "no_description": 1, "over_limit": 0}
    assert started["to_score"] == 1 and started["task_id"]
    assert _work(app, settings, started["task_id"], tmp_path, FakeJobSource()) is Outcome.SUCCEEDED
    task = client.get(f"/api/v1/tasks/{started['task_id']}", headers=user).json()
    assert task["result"]["scored"] == 1
    after = client.get(f"{API}/analysis-summary?state=saved", headers=user).json()
    assert (after["to_score"], after["already_scored"]) == (0, 2)
    nothing = client.post(f"{API}/analyze-batch?state=saved", headers=user).json()
    assert nothing["task_id"] is None


@respx.mock
def test_batch_stops_at_the_ai_budget(
    app: FastAPI, client: TestClient, migrated_database: str, settings: Settings, tmp_path: Path
) -> None:
    respx.post(AI_URL).mock(return_value=chat_response(MATCH, cost=0.02))
    jobs = [make_job(1, description=JD), make_job(2, description=JD)]
    _, user, _ = _setup(app, client, migrated_database, settings, tmp_path, jobs=jobs)
    client.patch("/api/v1/users/me/settings", json={"monthly_ai_budget_usd": "0.01"}, headers=user)

    started = client.post(f"{API}/analyze-batch", headers=user).json()
    _work(app, settings, started["task_id"], tmp_path, FakeJobSource())

    result = client.get(f"/api/v1/tasks/{started['task_id']}", headers=user).json()["result"]
    assert result["scored"] == 1  # the first call used up the budget
    assert "budget" in result["stopped"]


@respx.mock
def test_sort_and_filter_by_score_and_export_scores(
    app: FastAPI, client: TestClient, migrated_database: str, settings: Settings, tmp_path: Path
) -> None:
    low = {**MATCH, "skills_match": 20, "experience_match": 20, "technology_match": 20}
    respx.post(AI_URL).mock(side_effect=[chat_response(MATCH), chat_response(low)])
    jobs = [make_job(1, description=JD), make_job(2, description=JD), make_job(3, description=JD)]
    _, user, ids = _setup(app, client, migrated_database, settings, tmp_path, jobs=jobs)
    _score(app, client, settings, tmp_path, user, ids[1])
    _score(app, client, settings, tmp_path, user, ids[2])

    by_score = client.get(f"{API}?sort=score", headers=user).json()["items"]
    good = client.get(f"{API}?min_score=60", headers=user).json()["items"]
    csv = client.get(f"{API}/export.csv?sort=score", headers=user).content.decode("utf-8")

    assert [job["match_score"] for job in by_score] == [79, 32, None]
    assert [job["id"] for job in good] == [ids[1]]
    row = csv.splitlines()[1]
    assert ",79," in row and "React Native" in row and "GraphQL" in row


# ---------- Scan (pasted JD) ----------


@respx.mock
def test_scan_pasted_description_creates_a_private_job(
    app: FastAPI, client: TestClient, migrated_database: str, settings: Settings, tmp_path: Path
) -> None:
    respx.post(AI_URL).mock(return_value=chat_response(MATCH))
    user_id, user = make_user(client, migrated_database, "a@example.com")
    _, other = make_user(client, migrated_database, "b@example.com")
    _resume(migrated_database, user_id)

    started = client.post(
        f"{API}/scan-text",
        json={"title": "Mobile Engineer", "company": "Acme", "description": JD},
        headers=user,
    )
    too_short = client.post(f"{API}/scan-text", json={"description": "short"}, headers=user)

    assert started.status_code == 202 and too_short.status_code == 422
    body = started.json()
    assert _work(app, settings, body["task_id"], tmp_path, FakeJobSource()) is Outcome.SUCCEEDED
    detail = client.get(f"{API}/{body['job_id']}", headers=user).json()
    assert detail["source"] == "manual" and detail["match_score"] == 79
    assert client.get(f"{API}/{body['job_id']}", headers=other).status_code == 404  # private
    again = client.post(
        f"{API}/scan-text", json={"title": "x", "company": "y", "description": JD}, headers=user
    ).json()
    assert again["job_id"] == body["job_id"]  # the same text is the same job


@respx.mock
def test_scores_are_private(
    app: FastAPI, client: TestClient, migrated_database: str, settings: Settings, tmp_path: Path
) -> None:
    respx.post(AI_URL).mock(return_value=chat_response(MATCH))
    _, alice, (job_id,) = _setup(app, client, migrated_database, settings, tmp_path)
    bob_id, bob = make_user(client, migrated_database, "bob@example.com")
    _resume(migrated_database, bob_id)
    _score(app, client, settings, tmp_path, alice, job_id)

    bob_view = client.get(f"{API}/{job_id}", headers=bob).json()  # public job, Bob's view

    assert bob_view["analysis"] is None and bob_view["match_score"] is None
