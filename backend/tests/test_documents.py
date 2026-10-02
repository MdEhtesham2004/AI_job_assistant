"""Phase 10: tailored resumes and cover letters (generation, checks, edits, privacy)."""

import copy
from pathlib import Path

import respx
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.core.config import Settings
from app.services.cover_letters import compose, problems
from app.workers.runner import Outcome
from tests.fakes import FAKE_PDF, FakeGotenberg, FakeJobSource, chat_response, make_job
from tests.helpers import db, make_user
from tests.resume_samples import PARSED, RESUME_LINES
from tests.test_analysis import JD, MATCH, _resume
from tests.test_jobs import _search_and_run, _work

AI_URL = "https://ai.test/v1/chat/completions"
JOBS = "/api/v1/jobs"

TAILORED = copy.deepcopy(PARSED)
TAILORED["summary"] = "React Native developer with 4 years of experience shipping apps."
TAILORED["skills"] = ["TypeScript", "React Native", "Redux", "Jest", "Firebase"]
TAILORED["email"] = "changed@evil.test"  # identity is always copied from the original

PARAGRAPHS = [
    "I am applying for the React Native Developer 1 role at Company 1. Over the past 4 years "
    "I have built and shipped React Native apps, most recently a payments app used by 50000 "
    "customers at Acme Apps, and I would like to bring that experience to your team.",
    "At Acme Apps I cut the crash rate by 30% through better error handling, and at Blue Labs "
    "I shipped 6 apps to the Play Store and App Store. I work daily with TypeScript, Redux, "
    "Jest and Firebase, which matches the stack described in your posting.",
    "Your description asks for engineers who own features from design to release. That is how "
    "I work: I plan the change, write the tests, ship it and watch the numbers afterwards. I "
    "enjoy working closely with designers and backend engineers to make releases calm.",
    "I would welcome the chance to discuss how I can help Company 1 deliver reliable mobile "
    "releases. Thank you for your time and consideration.",
]


def _setup(app, client, url, settings, tmp_path, email="a@example.com"):  # type: ignore[no-untyped-def]
    app.state.gotenberg = FakeGotenberg()
    user_id, headers = make_user(client, url, email)
    _resume(url, user_id)
    run = _search_and_run(
        app, client, settings, tmp_path, headers, FakeJobSource([make_job(1, description=JD)])
    )
    return user_id, headers, run["jobs"][0]["id"]


def _run(app, settings, tmp_path, task_id):  # type: ignore[no-untyped-def]
    return _work(app, settings, task_id, tmp_path, FakeJobSource())


# ---------- rules ----------


def test_compose_and_check_a_letter() -> None:
    letter = compose(PARAGRAPHS, contact_name="Priya Sharma", candidate_name="Asha Verma")
    resume_text = "\n".join(RESUME_LINES)

    assert letter.startswith("Dear Priya Sharma,\n\n")
    assert letter.endswith("Sincerely,\nAsha Verma")
    assert compose(["x"], contact_name=None, candidate_name=None).startswith("Dear Hiring Team,")
    ok = problems(
        letter,
        resume_text=resume_text,
        job_text=JD,
        company="Company 1",
        title="React Native Developer 1",
    )
    assert ok == []

    bad = letter.replace("30%", "45%").replace("Company 1", "[Company]")
    found = problems(
        bad,
        resume_text=resume_text,
        job_text=JD,
        company="Company 1",
        title="React Native Developer 1",
    )
    assert any("placeholder" in p for p in found)
    assert any("45" in p for p in found)
    other_company = problems(
        letter, resume_text=resume_text, job_text=JD, company="Zeta Labs", title="Mobile Lead"
    )
    assert "the company 'Zeta Labs' is not named" in other_company
    assert "the role 'Mobile Lead' is not named" in other_company


def test_letters_may_not_claim_skills_the_resume_lacks() -> None:
    resume_text = "\n".join(RESUME_LINES)
    title = "Frontend Engineer (React.js, React Native)"
    base = compose(PARAGRAPHS, contact_name=None, candidate_name="Asha Verma").replace(
        "React Native Developer 1 role at Company 1", f"{title} role at Company 1"
    )

    def check(text: str) -> list[str]:
        return problems(
            text,
            resume_text=resume_text,
            job_text=JD,
            company="Company 1",
            title=title,
            lacking=["React.js", "Node.js", "Responsive Web Design"],
        )

    assert check(base) == []  # naming the role (which contains React.js) is fine
    learning = base.replace("Thank you", "I am keen to learn Node.js quickly. Thank you")
    assert check(learning) == []  # honest: wanting to learn is not a claim
    claim = base.replace(
        "Thank you", "I also build Node.js services and responsive designs. Thank you"
    )
    assert check(claim) == [
        "claims skills that are not in the resume: Node.js, Responsive Web Design"
    ]


# ---------- tailored resume ----------


@respx.mock
def test_tailored_resume_is_a_new_version_for_the_job(
    app: FastAPI, client: TestClient, migrated_database: str, settings: Settings, tmp_path: Path
) -> None:
    respx.post(AI_URL).mock(return_value=chat_response(TAILORED))
    _, user, job_id = _setup(app, client, migrated_database, settings, tmp_path)

    started = client.post(f"{JOBS}/{job_id}/tailored-resume", headers=user)
    assert started.status_code == 202
    assert _run(app, settings, tmp_path, started.json()["task_id"]) is Outcome.SUCCEEDED

    docs = client.get(f"{JOBS}/{job_id}/documents", headers=user).json()
    tailored = docs["tailored"]
    assert (tailored["kind"], tailored["version_no"]) == ("tailored", 2)
    assert tailored["parsed"]["skills"][0] == "TypeScript"
    assert tailored["parsed"]["email"] == "asha@example.com"
    assert tailored["warnings"] == []
    assert "Redux" in tailored["emphasized_skills"]
    assert docs["tailored_from"]["version_no"] == 1
    assert tailored["file_name"].endswith("-company-1.pdf")
    assert client.get(tailored["download_url"]).content == FAKE_PDF
    overview = client.get("/api/v1/resumes", headers=user).json()
    assert overview["versions"][0]["kind"] == "tailored"
    assert overview["versions"][0]["is_active"] is False  # the master stays active


@respx.mock
def test_tailoring_refuses_invented_facts(
    app: FastAPI, client: TestClient, migrated_database: str, settings: Settings, tmp_path: Path
) -> None:
    invented = copy.deepcopy(TAILORED)
    invented["experience"][0]["company"] = "Google"
    route = respx.post(AI_URL).mock(return_value=chat_response(invented))
    _, user, job_id = _setup(app, client, migrated_database, settings, tmp_path)

    task_id = client.post(f"{JOBS}/{job_id}/tailored-resume", headers=user).json()["task_id"]

    assert _run(app, settings, tmp_path, task_id) is Outcome.FAILED
    task = client.get(f"/api/v1/tasks/{task_id}", headers=user).json()
    assert "Google" in task["error"]
    assert route.call_count == 2  # one retry
    assert client.get(f"{JOBS}/{job_id}/documents", headers=user).json()["tailored"] is None


@respx.mock
def test_missing_skills_from_the_analysis_are_never_added(
    app: FastAPI, client: TestClient, migrated_database: str, settings: Settings, tmp_path: Path
) -> None:
    sneaky = copy.deepcopy(TAILORED)
    sneaky["skills"] = [*TAILORED["skills"], "GraphQL"]  # the job wants it, the resume lacks it
    route = respx.post(AI_URL)
    route.side_effect = [chat_response(MATCH), chat_response(sneaky)]
    _, user, job_id = _setup(app, client, migrated_database, settings, tmp_path)
    task = client.post(f"{JOBS}/{job_id}/analyze", headers=user).json()["task_id"]
    _run(app, settings, tmp_path, task)

    task_id = client.post(f"{JOBS}/{job_id}/tailored-resume", headers=user).json()["task_id"]
    assert _run(app, settings, tmp_path, task_id) is Outcome.SUCCEEDED

    skills = client.get(f"{JOBS}/{job_id}/documents", headers=user).json()["tailored"]["parsed"][
        "skills"
    ]
    assert "GraphQL" not in skills
    assert "GraphQL" in route.calls.last.request.content.decode()  # told not to claim it


@respx.mock
def test_edit_tailored_resume_re_renders_and_warns(
    app: FastAPI, client: TestClient, migrated_database: str, settings: Settings, tmp_path: Path
) -> None:
    respx.post(AI_URL).mock(return_value=chat_response(TAILORED))
    _, user, job_id = _setup(app, client, migrated_database, settings, tmp_path)
    _run(
        app,
        settings,
        tmp_path,
        client.post(f"{JOBS}/{job_id}/tailored-resume", headers=user).json()["task_id"],
    )
    tailored = client.get(f"{JOBS}/{job_id}/documents", headers=user).json()["tailored"]
    rendered_before = len(app.state.gotenberg.rendered)

    edited = {
        **tailored["parsed"],
        "summary": "Edited by me.",
        "skills": ["Kubernetes", "Redux"],
        "name": "Someone Else",
    }
    response = client.put(
        f"/api/v1/resumes/versions/{tailored['id']}/content", json=edited, headers=user
    )

    assert response.status_code == 200
    after = response.json()["tailored"]
    assert after["parsed"]["summary"] == "Edited by me."
    assert after["parsed"]["name"] == "Asha Verma"  # identity cannot be edited away
    assert "skill 'Kubernetes'" in after["warnings"]  # saved, but flagged
    assert len(app.state.gotenberg.rendered) == rendered_before + 1
    assert "Edited by me." in app.state.gotenberg.rendered[-1]


# ---------- cover letter ----------


@respx.mock
def test_cover_letter_is_addressed_checked_and_rendered(
    app: FastAPI, client: TestClient, migrated_database: str, settings: Settings, tmp_path: Path
) -> None:
    placeholder = [PARAGRAPHS[0].replace("Company 1", "[Company]"), *PARAGRAPHS[1:]]
    route = respx.post(AI_URL)
    route.side_effect = [
        chat_response({"paragraphs": placeholder}),  # rejected: placeholder, company missing
        chat_response({"paragraphs": PARAGRAPHS}),
    ]
    _, user, job_id = _setup(app, client, migrated_database, settings, tmp_path)

    task_id = client.post(
        f"{JOBS}/{job_id}/cover-letter", json={"contact_name": "Priya Sharma"}, headers=user
    ).json()["task_id"]
    assert _run(app, settings, tmp_path, task_id) is Outcome.SUCCEEDED

    letter = client.get(f"{JOBS}/{job_id}/documents", headers=user).json()["cover_letter"]
    assert route.call_count == 2
    assert letter["content_md"].startswith("Dear Priya Sharma,")
    assert letter["content_md"].endswith("Sincerely,\nAsha Verma")
    assert letter["status"] == "draft"
    assert letter["warnings"] == []
    assert 150 < letter["word_count"] < 350
    assert client.get(letter["download_url"]).content == FAKE_PDF


@respx.mock
def test_edit_cover_letter_and_mark_final(
    app: FastAPI, client: TestClient, migrated_database: str, settings: Settings, tmp_path: Path
) -> None:
    respx.post(AI_URL).mock(return_value=chat_response({"paragraphs": PARAGRAPHS}))
    _, user, job_id = _setup(app, client, migrated_database, settings, tmp_path)
    _run(
        app,
        settings,
        tmp_path,
        client.post(f"{JOBS}/{job_id}/cover-letter", headers=user).json()["task_id"],
    )
    letter = client.get(f"{JOBS}/{job_id}/documents", headers=user).json()["cover_letter"]

    edited = letter["content_md"].replace("Thank you", "Regards from [Your Name]. Thank you")
    after = client.patch(
        f"/api/v1/cover-letters/{letter['id']}",
        json={"content_md": edited, "status": "final"},
        headers=user,
    ).json()["cover_letter"]

    assert after["content_md"].startswith("Dear Hiring Team,")
    assert after["status"] == "final"
    assert any("placeholder" in w for w in after["warnings"])
    assert "[Your Name]" in app.state.gotenberg.rendered[-1]


@respx.mock
def test_letter_from_a_tailored_resume_uses_the_masters_analysis(
    app: FastAPI, client: TestClient, migrated_database: str, settings: Settings, tmp_path: Path
) -> None:
    claims = [*PARAGRAPHS[:-1], "I also build GraphQL APIs every day. " + PARAGRAPHS[-1]]
    route = respx.post(AI_URL)
    route.side_effect = [
        chat_response(MATCH),  # analysis of the master: GraphQL is missing
        chat_response(TAILORED),
        chat_response({"paragraphs": claims}),  # rejected: claims GraphQL
        chat_response({"paragraphs": PARAGRAPHS}),
    ]
    _, user, job_id = _setup(app, client, migrated_database, settings, tmp_path)
    for path in ("analyze", "tailored-resume", "cover-letter"):
        _run(
            app,
            settings,
            tmp_path,
            client.post(f"{JOBS}/{job_id}/{path}", headers=user).json()["task_id"],
        )

    letter = client.get(f"{JOBS}/{job_id}/documents", headers=user).json()["cover_letter"]
    assert route.call_count == 4  # the GraphQL claim forced a retry
    assert "GraphQL" not in letter["content_md"]
    assert letter["warnings"] == []


# ---------- rules for starting ----------


def test_documents_need_a_resume_and_a_description(
    app: FastAPI, client: TestClient, migrated_database: str, settings: Settings, tmp_path: Path
) -> None:
    app.state.gotenberg = FakeGotenberg()
    user_id, user = make_user(client, migrated_database, "a@example.com")
    run = _search_and_run(
        app, client, settings, tmp_path, user, FakeJobSource([make_job(1, description="Apply")])
    )
    job_id = run["jobs"][0]["id"]

    no_resume = client.post(f"{JOBS}/{job_id}/tailored-resume", headers=user)
    _resume(migrated_database, user_id)
    no_description = client.post(f"{JOBS}/{job_id}/cover-letter", headers=user)
    docs = client.get(f"{JOBS}/{job_id}/documents", headers=user).json()

    assert no_resume.json()["error"]["code"] == "RESUME_REQUIRED"
    assert no_description.json()["error"]["code"] == "DESCRIPTION_MISSING"
    assert docs["source"]["version_no"] == 1 and docs["tailored"] is None


@respx.mock
def test_documents_are_private(
    app: FastAPI, client: TestClient, migrated_database: str, settings: Settings, tmp_path: Path
) -> None:
    route = respx.post(AI_URL)
    route.side_effect = [chat_response(TAILORED), chat_response({"paragraphs": PARAGRAPHS})]
    _, alice, job_id = _setup(app, client, migrated_database, settings, tmp_path)
    _, bob = make_user(client, migrated_database, "bob@example.com")
    _run(
        app,
        settings,
        tmp_path,
        client.post(f"{JOBS}/{job_id}/tailored-resume", headers=alice).json()["task_id"],
    )
    _run(
        app,
        settings,
        tmp_path,
        client.post(f"{JOBS}/{job_id}/cover-letter", headers=alice).json()["task_id"],
    )
    docs = client.get(f"{JOBS}/{job_id}/documents", headers=alice).json()

    bob_docs = client.get(f"{JOBS}/{job_id}/documents", headers=bob).json()  # public job

    assert bob_docs["tailored"] is None and bob_docs["cover_letter"] is None
    assert (
        client.put(
            f"/api/v1/resumes/versions/{docs['tailored']['id']}/content", json=PARSED, headers=bob
        ).status_code
        == 404
    )
    assert (
        client.patch(
            f"/api/v1/cover-letters/{docs['cover_letter']['id']}",
            json={"status": "final"},
            headers=bob,
        ).status_code
        == 404
    )
    (count,) = db(migrated_database, "SELECT count(*) FROM cover_letters")[0]
    assert count == 1
