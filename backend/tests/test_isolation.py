"""Phase 5 rule: a user can never reach another user's data by changing an ID.

Every new user-owned endpoint/repository added in later phases must get a test here.
"""

import uuid

from fastapi.testclient import TestClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.accounts import User
from app.models.enums import AnalysisDecision, DescriptionQuality, JobSource, ResumeKind
from app.models.jobs import Job, JobSearchRun, SavedSearch
from app.models.resumes import Resume, ResumeAtsReport, ResumeVersion
from app.models.system import Task
from app.repositories.analyses import JobAnalysisRepository
from app.repositories.jobs import (
    JobFilters,
    JobSearchRunRepository,
    SavedSearchRepository,
    UserJobRepository,
)
from app.repositories.profiles import ProfileRepository
from app.repositories.resumes import (
    ResumeAtsReportRepository,
    ResumeRepository,
    ResumeVersionRepository,
)
from app.repositories.tasks import TaskRepository
from tests.helpers import make_user


async def _two_users(session: AsyncSession) -> tuple[User, User]:
    alice = User(email="alice@example.com", full_name="Alice", hashed_password="x")
    bob = User(email="bob@example.com", full_name="Bob", hashed_password="x")
    session.add_all([alice, bob])
    await session.flush()
    return alice, bob


async def test_owned_repository_hides_other_users_rows(session: AsyncSession) -> None:
    alice, bob = await _two_users(session)
    alice_task = await TaskRepository(session, owner_id=alice.id).add(Task(type="parse_resume"))
    await session.commit()

    as_bob = TaskRepository(session, owner_id=bob.id)

    assert await as_bob.get(alice_task.id) is None  # looks like it does not exist
    assert await as_bob.list() == []
    assert await as_bob.count() == 0
    assert await TaskRepository(session, owner_id=alice.id).get(alice_task.id) is not None


async def test_owner_is_always_the_repository_owner(session: AsyncSession) -> None:
    alice, bob = await _two_users(session)

    # Even if a caller tries to set someone else's user_id, the owner wins.
    task = await TaskRepository(session, owner_id=alice.id).add(Task(type="x", user_id=bob.id))

    assert task.user_id == alice.id


async def test_profiles_are_separate_per_user(session: AsyncSession) -> None:
    alice, bob = await _two_users(session)
    alice_profile = await ProfileRepository(session, owner_id=alice.id).get_or_create()
    alice_profile.headline = "Alice's headline"
    await session.commit()

    bob_profile = await ProfileRepository(session, owner_id=bob.id).get_or_create()

    assert bob_profile.user_id == bob.id
    assert bob_profile.headline is None
    assert await ProfileRepository(session, owner_id=bob.id).get(alice.id) is None


async def test_resumes_versions_and_reports_are_private(session: AsyncSession) -> None:
    """Phase 7. The HTTP side is covered by test_resumes.py::test_resumes_are_private."""
    alice, bob = await _two_users(session)
    resume = await ResumeRepository(session, owner_id=alice.id).add(Resume())
    version = await ResumeVersionRepository(session, owner_id=alice.id).add(
        ResumeVersion(
            resume_id=resume.id,
            version_no=1,
            kind=ResumeKind.MASTER,
            file_key="users/a/resumes/cv.pdf",
            file_name="cv.pdf",
            mime_type="application/pdf",
            file_size=10,
        )
    )
    report = await ResumeAtsReportRepository(session, owner_id=alice.id).add(
        ResumeAtsReport(
            resume_version_id=version.id,
            ats_score=70,
            section_scores={},
            strengths=[],
            missing_skills=[],
            top_roles=[],
            suggestions=[],
            model="m",
            prompt_version="v",
        )
    )
    await session.commit()

    bob_resumes = ResumeRepository(session, owner_id=bob.id)
    bob_versions = ResumeVersionRepository(session, owner_id=bob.id)
    bob_reports = ResumeAtsReportRepository(session, owner_id=bob.id)

    assert await bob_resumes.first() is None
    assert await bob_resumes.get(resume.id) is None
    assert await bob_versions.get(version.id) is None
    assert await bob_versions.for_resume(resume.id) == []
    assert await bob_versions.next_version_no(resume.id) == 1  # alice's versions not counted
    assert await bob_reports.get(report.id) is None
    assert await bob_reports.latest_for(version.id) is None
    assert await bob_reports.latest_scores([version.id]) == {}
    alice_reports = ResumeAtsReportRepository(session, owner_id=alice.id)
    assert await alice_reports.latest_scores([version.id]) == {version.id: 70}


async def test_job_state_saved_searches_and_runs_are_private(session: AsyncSession) -> None:
    """Phase 8. Jobs are shared; everything about them per user is not.
    HTTP side: test_jobs.py (…each_user_has_their_own_list, …saved_searches_are_private)."""
    alice, bob = await _two_users(session)
    job = Job(
        source=JobSource.JSEARCH,
        external_id="x1",
        title="Dev",
        company="Acme",
        description_quality=DescriptionQuality.MISSING,
        dedupe_hash="h",
    )
    session.add(job)
    await session.flush()
    await UserJobRepository(session, owner_id=alice.id).link(job.id)
    saved = await SavedSearchRepository(session, owner_id=alice.id).add(
        SavedSearch(name="s", keywords="React")
    )
    run = await JobSearchRunRepository(session, owner_id=alice.id).add(
        JobSearchRun(source=JobSource.JSEARCH, query={})
    )
    await session.commit()

    bob_jobs = UserJobRepository(session, owner_id=bob.id)
    assert await bob_jobs.for_job(job.id) is None
    rows, total = await bob_jobs.page(JobFilters(), limit=10, offset=0)
    assert (list(rows), total) == ([], 0)
    assert await SavedSearchRepository(session, owner_id=bob.id).get(saved.id) is None
    assert await JobSearchRunRepository(session, owner_id=bob.id).get(run.id) is None
    assert (
        await UserJobRepository(session, owner_id=alice.id).page(JobFilters(), limit=10, offset=0)
    )[1] == 1


async def test_match_scores_are_private(session: AsyncSession) -> None:
    """Phase 9. HTTP side: test_analysis.py::test_scores_are_private."""
    alice, bob = await _two_users(session)
    job = Job(
        source=JobSource.JSEARCH,
        external_id="x2",
        title="Dev",
        company="Acme",
        description_quality=DescriptionQuality.COMPLETE,
        dedupe_hash="h2",
    )
    resume = Resume(user_id=alice.id)
    session.add_all([job, resume])
    await session.flush()
    version = ResumeVersion(
        user_id=alice.id,
        resume_id=resume.id,
        version_no=1,
        kind=ResumeKind.MASTER,
        file_key="k",
        file_name="cv.pdf",
        mime_type="application/pdf",
        file_size=1,
    )
    session.add(version)
    await session.flush()
    analysis = await JobAnalysisRepository(session, owner_id=alice.id).save(
        {
            "job_id": job.id,
            "resume_version_id": version.id,
            "component_scores": {},
            "weights_used": {},
            "match_score": 70,
            "matched_skills": [],
            "missing_skills": [],
            "recommendations": [],
            "red_flags": [],
            "decision": AnalysisDecision.TAILOR,
            "model": "m",
            "prompt_version": "v",
        }
    )
    await session.commit()

    as_bob = JobAnalysisRepository(session, owner_id=bob.id)
    assert await as_bob.get(analysis.id) is None
    assert await as_bob.for_pair(job.id, version.id) is None
    assert await as_bob.best_for_jobs([job.id], version.id) == {}


def test_api_profile_and_settings_return_only_your_own(
    client: TestClient, migrated_database: str
) -> None:
    _, alice = make_user(client, migrated_database, "alice@example.com")
    _, bob = make_user(client, migrated_database, "bob@example.com")

    client.put(
        "/api/v1/users/me/profile",
        json={"headline": "Alice only", "links": {}, "timezone": "UTC"},
        headers=alice,
    )
    client.patch("/api/v1/users/me/settings", json={"daily_send_cap": 3}, headers=alice)

    assert client.get("/api/v1/users/me/profile", headers=bob).json()["headline"] is None
    assert client.get("/api/v1/users/me/settings", headers=bob).json()["daily_send_cap"] == 25


def test_random_ids_never_leak_existence(client: TestClient, migrated_database: str) -> None:
    _, admin = make_user(client, migrated_database, "admin@example.com", role="admin")

    response = client.get(f"/api/v1/admin/users/{uuid.uuid4()}", headers=admin)

    assert response.status_code == 404
    assert response.json()["error"]["code"] == "NOT_FOUND"
