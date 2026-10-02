"""Job search and the user's job list (Phase 8, Modules 02 + 03)."""

import uuid
from collections.abc import Sequence
from dataclasses import dataclass

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings
from app.core.errors import ConflictError, NotFoundError
from app.domain.jobs import classify_description
from app.models.enums import DescriptionQuality, JobSource, SearchRunStatus, UserJobState
from app.models.jobs import Job, JobSearchRun, UserJob
from app.models.system import Task
from app.repositories.jobs import (
    JobFilters,
    JobRepository,
    JobSearchRunRepository,
    UserJobRepository,
)
from app.repositories.profiles import ProfileRepository
from app.repositories.resumes import ResumeAtsReportRepository, ResumeRepository
from app.repositories.tasks import TaskRepository
from app.schemas.jobs import MAX_PAGES_PER_SEARCH, JobSearchRequest, JobUpdate
from app.services.job_export import to_csv
from app.services.tasks import TaskDispatcher, TaskService

RUN_ENTITY = "job_search_run"
JOB_ENTITY = "job"
EXPORT_LIMIT = 5000


def pages_loaded(run: JobSearchRun) -> int:
    return int(run.query.get("pages_loaded") or 0)


def can_load_more(run: JobSearchRun) -> bool:
    return (
        run.status is SearchRunStatus.SUCCEEDED
        and not run.query.get("exhausted")
        and pages_loaded(run) < MAX_PAGES_PER_SEARCH
    )


@dataclass(frozen=True)
class JobView:
    job: Job
    user_job: UserJob | None

    @property
    def description(self) -> str | None:
        if self.user_job and self.user_job.description_override:
            return self.user_job.description_override
        return self.job.description

    @property
    def quality(self) -> DescriptionQuality:
        if self.user_job and self.user_job.description_override:
            return classify_description(self.user_job.description_override)
        return self.job.description_quality


class JobService:
    def __init__(
        self,
        session: AsyncSession,
        user_id: uuid.UUID,
        *,
        settings: Settings,
        dispatcher: TaskDispatcher,
    ) -> None:
        self.session = session
        self.user_id = user_id
        self.settings = settings
        self.jobs = JobRepository(session)
        self.user_jobs = UserJobRepository(session, owner_id=user_id)
        self.runs = JobSearchRunRepository(session, owner_id=user_id)
        self.tasks = TaskService(session, user_id, dispatcher)

    # ---------- searching ----------

    async def start_search(
        self, request: JobSearchRequest, *, saved_search_id: uuid.UUID | None = None
    ) -> tuple[JobSearchRun, Task]:
        query = request.model_dump(mode="json") | {"pages_loaded": 0, "exhausted": False}
        run = await self.runs.add(
            JobSearchRun(source=JobSource.JSEARCH, query=query, saved_search_id=saved_search_id)
        )
        task = await self.tasks.create(
            "job_search", {"run_id": str(run.id)}, entity_type=RUN_ENTITY, entity_id=run.id
        )  # commits and dispatches
        run.task_id = task.id
        await self.session.commit()
        return run, task

    async def load_more(self, run_id: uuid.UUID) -> tuple[JobSearchRun, Task]:
        """Fetch the next JSearch page for the same search (one request per click)."""
        run = await self._run(run_id)
        if run.status in (SearchRunStatus.QUEUED, SearchRunStatus.RUNNING) and run.task_id:
            running = await TaskRepository(self.session, owner_id=self.user_id).get(run.task_id)
            if running is not None:
                return run, running  # already loading
        if not can_load_more(run):
            raise ConflictError(
                "There are no more results for this search.", code="NO_MORE_RESULTS"
            )
        task = await self.tasks.create(
            "job_search",
            {"run_id": str(run.id), "page": pages_loaded(run) + 1, "num_pages": 1},
            entity_type=RUN_ENTITY,
            entity_id=run.id,
        )
        run.status = SearchRunStatus.QUEUED
        run.task_id = task.id
        await self.session.commit()
        return run, task

    async def recent_runs(self, limit: int = 10) -> Sequence[JobSearchRun]:
        return await self.runs.recent(limit)

    async def _run(self, run_id: uuid.UUID) -> JobSearchRun:
        run = await self.runs.get(run_id)
        if run is None:
            raise NotFoundError("Search not found.")
        return run

    async def run_detail(
        self, run_id: uuid.UUID
    ) -> tuple[JobSearchRun, list[tuple[JobView, bool]]]:
        """The run and its jobs, each with `is_new` (added to your list by this search)."""
        run = await self._run(run_id)
        results = await self.runs.results(run.id)
        return run, [(JobView(job, user_job), is_new) for job, user_job, is_new in results]

    async def suggested_roles(self) -> tuple[list[str], str | None, str | None]:
        """Roles from the active resume's latest ATS report (Module 02 role suggestion)."""
        profile = await ProfileRepository(self.session, owner_id=self.user_id).get(self.user_id)
        location = profile.location if profile else None
        resume = await ResumeRepository(self.session, owner_id=self.user_id).first()
        if resume is None or resume.active_version_id is None:
            return [], location, "Upload a resume to get role suggestions."
        report = await ResumeAtsReportRepository(self.session, owner_id=self.user_id).latest_for(
            resume.active_version_id
        )
        if report is None:
            return [], location, "Run the ATS analysis on your active resume to get suggestions."
        return list(report.top_roles), location, None

    # ---------- the user's jobs ----------

    async def list(
        self, filters: JobFilters, *, page: int, page_size: int
    ) -> tuple[list[JobView], int]:
        rows, total = await self.user_jobs.page(
            filters, limit=page_size, offset=(page - 1) * page_size
        )
        return [JobView(job, user_job) for user_job, job in rows], total

    async def export_csv(self, filters: JobFilters, *, include_description: bool) -> str:
        """All jobs matching the filters (up to EXPORT_LIMIT) as CSV text."""
        rows, _ = await self.user_jobs.page(filters, limit=EXPORT_LIMIT, offset=0)
        views = [JobView(job, user_job) for user_job, job in rows]
        return to_csv(
            (
                {
                    "title": v.job.title,
                    "company": v.job.company,
                    "location": v.job.location,
                    "remote": v.job.is_remote,
                    "employment_type": v.job.employment_type,
                    "posted_at": v.job.posted_at,
                    "state": v.user_job.state.value if v.user_job else None,
                    "description_quality": v.quality.value,
                    "apply_url": v.job.apply_url,
                    "found_at": v.user_job.first_found_at if v.user_job else None,
                    "notes": v.user_job.notes if v.user_job else None,
                    # match_score / matching_skills / missing_skills / scored_at: Phase 9
                    "description": v.description,
                }
                for v in views
            ),
            include_description=include_description,
        )

    async def counts(self) -> dict[str, int]:
        return await self.user_jobs.state_counts()

    async def _visible(self, job_id: uuid.UUID) -> Job:
        job = await self.jobs.visible(job_id, self.user_id)
        if job is None:
            raise NotFoundError("Job not found.")
        return job

    async def detail(self, job_id: uuid.UUID) -> tuple[JobView, Sequence[Task]]:
        job = await self._visible(job_id)
        user_job = await self.user_jobs.for_job(job.id)
        active = await TaskRepository(self.session, owner_id=self.user_id).active_for(
            JOB_ENTITY, job.id
        )
        return JobView(job, user_job), active

    async def update(self, job_id: uuid.UUID, changes: JobUpdate) -> JobView:
        job = await self._visible(job_id)
        user_job = await self.user_jobs.for_job(job.id)
        if user_job is None:
            user_job = await self.user_jobs.add(UserJob(job_id=job.id))
        fields = changes.model_fields_set
        if "state" in fields and changes.state is not None:
            user_job.state = UserJobState(changes.state)
        if "notes" in fields:
            user_job.notes = (changes.notes or "").strip() or None
        if "description" in fields:
            user_job.description_override = (changes.description or "").strip() or None
        await self.session.commit()
        await self.session.refresh(user_job)
        return JobView(job, user_job)

    async def start_fetch_description(self, job_id: uuid.UUID) -> Task:
        job = await self._visible(job_id)
        running = await TaskRepository(self.session, owner_id=self.user_id).active_for(
            JOB_ENTITY, job.id
        )
        for task in running:
            if task.type == "job_fetch_page":
                return task
        if not job.apply_url:
            raise ConflictError("This job has no apply link to read.", code="NO_APPLY_URL")
        if job.description_quality is DescriptionQuality.COMPLETE:
            raise ConflictError("This job already has a full description.", code="ALREADY_COMPLETE")
        return await self.tasks.create(
            "job_fetch_page", {"job_id": str(job.id)}, entity_type=JOB_ENTITY, entity_id=job.id
        )
