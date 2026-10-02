"""AI job analysis (Phase 9, Module 04) — on demand only (admin decision 2026-10-02).

A score is made only when the user asks ("Get match score", "Score all saved jobs",
Scan). It is cached per (job, resume version); switching the active resume makes old
scores "stale" until the user scores again.
"""

import hashlib
import json
import uuid
from collections.abc import Sequence
from dataclasses import dataclass, replace

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings
from app.core.errors import ConflictError, NotFoundError
from app.domain.jobs import classify_description, dedupe_hash
from app.domain.scoring import clamp, decide, grounded, weighted_score
from app.integrations.ai import AiClient
from app.models.analysis import JobAnalysis
from app.models.enums import (
    DescriptionQuality,
    JobSource,
    JobVisibility,
    ParseStatus,
    UserJobState,
)
from app.models.jobs import Job, UserJob
from app.models.resumes import ResumeVersion
from app.models.system import Task
from app.prompts import jobs as prompts
from app.prompts.jobs import JobMatch
from app.repositories.analyses import JobAnalysisRepository
from app.repositories.jobs import JobFilters, JobRepository, UserJobRepository
from app.repositories.profiles import ProfileRepository, UserSettingsRepository
from app.repositories.resumes import ResumeRepository, ResumeVersionRepository
from app.repositories.tasks import TaskRepository
from app.services.ai import AiService
from app.services.tasks import TaskDispatcher, TaskService

JOB_ENTITY = "job"
MAX_DESCRIPTION_CHARS = 12_000
MAX_SKILLS = 12
MAX_NOTES = 5
BATCH_LIMIT = 50  # one click never scores more than this (cost control)
PARTIAL_WARNING = "The job description looks incomplete — this score is less reliable."


class ResumeRequiredError(ConflictError):
    code = "RESUME_REQUIRED"
    message = "Upload a resume and wait until it is parsed before scoring jobs."


async def active_version(session: AsyncSession, user_id: uuid.UUID) -> ResumeVersion | None:
    resume = await ResumeRepository(session, owner_id=user_id).first()
    if resume is None or resume.active_version_id is None:
        return None
    return await ResumeVersionRepository(session, owner_id=user_id).get(resume.active_version_id)


def effective_description(job: Job, user_job: UserJob | None) -> str:
    if user_job and user_job.description_override:
        return user_job.description_override
    return job.description or ""


def can_score(job: Job, user_job: UserJob | None) -> bool:
    return (
        classify_description(effective_description(job, user_job)) is not DescriptionQuality.MISSING
    )


async def analyze_job(
    session: AsyncSession,
    ai: AiClient,
    user_id: uuid.UUID,
    job: Job,
    user_job: UserJob | None,
    version: ResumeVersion,
) -> JobAnalysis:
    """Score one job against one parsed resume version and store the result."""
    description = effective_description(job, user_job)
    quality = classify_description(description)
    if quality is DescriptionQuality.MISSING:
        raise ConflictError(
            "This job has no usable description. Paste it first.", code="DESCRIPTION_MISSING"
        )
    settings = await UserSettingsRepository(session, owner_id=user_id).get_or_create()
    profile = await ProfileRepository(session, owner_id=user_id).get(user_id)
    resume = dict(version.parsed or {})
    resume.pop("links", None)
    if not resume.get("location") and profile and profile.location:
        resume["location"] = profile.location
    job_input = {
        "title": job.title,
        "company": job.company,
        "location": job.location,
        "remote": job.is_remote,
        "employment_type": job.employment_type,
        "description": description[:MAX_DESCRIPTION_CHARS],
    }

    result = await AiService(session, ai).complete_json(
        user_id=user_id,
        task_type="job_analyze",
        prompt_version=prompts.MATCH_VERSION,
        messages=prompts.match_messages(resume, job_input),
        output=JobMatch,
    )
    data = result.data
    components = {
        "skills": clamp(data.skills_match),
        "experience": clamp(data.experience_match),
        "technology": clamp(data.technology_match),
        "education": clamp(data.education_match),
        "location": clamp(data.location_match),
    }
    weights = {key: int(value) for key, value in settings.score_weights.items()}
    score = weighted_score(components, weights)
    resume_text = (
        json.dumps(version.parsed, ensure_ascii=False) + " " + (version.text_content or "")
    )
    red_flags = [flag.strip() for flag in data.red_flags if flag.strip()][:MAX_NOTES]
    if quality is DescriptionQuality.PARTIAL:
        red_flags = [PARTIAL_WARNING, *red_flags][:MAX_NOTES]

    analysis = await JobAnalysisRepository(session, owner_id=user_id).save(
        {
            "job_id": job.id,
            "resume_version_id": version.id,
            "component_scores": components,
            "weights_used": weights,
            "match_score": score,
            "matched_skills": grounded(data.matched_skills, resume_text, MAX_SKILLS),
            "missing_skills": grounded(data.missing_skills, description, MAX_SKILLS),
            "recommendations": [r.strip() for r in data.recommendations if r.strip()][:MAX_NOTES],
            "red_flags": red_flags,
            "seniority_fit": data.seniority_fit,
            "decision": decide(score, settings.threshold_use_master, settings.threshold_tailor),
            "model": result.model,
            "prompt_version": prompts.MATCH_VERSION,
        }
    )
    if user_job is not None and user_job.state is UserJobState.NEW:
        user_job.state = UserJobState.ANALYZED  # saved jobs stay saved
    await session.commit()
    return analysis


@dataclass(frozen=True)
class BatchPlan:
    job_ids: list[uuid.UUID]
    already_scored: int
    no_description: int
    over_limit: int


class AnalysisService:
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
        self.analyses = JobAnalysisRepository(session, owner_id=user_id)
        self.user_jobs = UserJobRepository(session, owner_id=user_id)
        self.tasks = TaskService(session, user_id, dispatcher)

    async def _scoring_version(self) -> ResumeVersion:
        version = await active_version(self.session, self.user_id)
        if version is None or version.parse_status is not ParseStatus.PARSED:
            raise ResumeRequiredError()
        return version

    async def start(self, job_id: uuid.UUID, *, force: bool = False) -> Task | None:
        """Score one job. Returns None when a score for the active resume already exists."""
        job = await JobRepository(self.session).visible(job_id, self.user_id)
        if job is None:
            raise NotFoundError("Job not found.")
        version = await self._scoring_version()
        if not force and await self.analyses.for_pair(job.id, version.id) is not None:
            return None
        user_job = await self.user_jobs.for_job(job.id)
        if not can_score(job, user_job):
            raise ConflictError(
                "This job has no usable description. Paste it first.", code="DESCRIPTION_MISSING"
            )
        running = await TaskRepository(self.session, owner_id=self.user_id).active_for(
            JOB_ENTITY, job.id
        )
        for task in running:
            if task.type == "job_analyze":
                return task
        return await self.tasks.create(
            "job_analyze",
            {"job_id": str(job.id), "version_id": str(version.id)},
            entity_type=JOB_ENTITY,
            entity_id=job.id,
        )

    async def plan_batch(self, filters: JobFilters) -> tuple[ResumeVersion, BatchPlan]:
        """Which jobs in this view still need a score (for the button label and the task)."""
        version = await self._scoring_version()
        base = replace(filters, active_version_id=version.id)
        _, total = await self.user_jobs.page(base, limit=1, offset=0)
        unscored_filters = replace(base, unscored_only=True)
        rows, unscored = await self.user_jobs.page(unscored_filters, limit=1000, offset=0)
        scorable = [job.id for user_job, job in rows if can_score(job, user_job)]
        return version, BatchPlan(
            job_ids=scorable[:BATCH_LIMIT],
            already_scored=total - unscored,
            no_description=unscored - len(scorable),
            over_limit=max(0, len(scorable) - BATCH_LIMIT),
        )

    async def start_batch(self, filters: JobFilters) -> tuple[Task | None, BatchPlan]:
        version, plan = await self.plan_batch(filters)
        if not plan.job_ids:
            return None, plan
        task = await self.tasks.create(
            "job_analyze_batch",
            {"job_ids": [str(i) for i in plan.job_ids], "version_id": str(version.id)},
        )
        return task, plan

    async def scan_text(self, title: str, company: str, description: str) -> tuple[Job, Task]:
        """Score a pasted job description. It is saved as a private job (source = manual)."""
        version = await self._scoring_version()
        if classify_description(description) is DescriptionQuality.MISSING:
            raise ConflictError(
                "Paste at least a few sentences of the job description.",
                code="DESCRIPTION_MISSING",
            )
        digest = hashlib.sha256(f"{self.user_id}|{description}".encode()).hexdigest()
        jobs = JobRepository(self.session)
        job = await jobs.by_external_id(JobSource.MANUAL, digest)
        if job is None:
            job = await jobs.insert_new(
                {
                    "source": JobSource.MANUAL,
                    "external_id": digest,
                    "visibility": JobVisibility.PRIVATE,
                    "created_by_user_id": self.user_id,
                    "title": title,
                    "company": company,
                    "description": description,
                    "description_quality": classify_description(description),
                    "dedupe_hash": dedupe_hash(company, title, None),
                }
            )
            assert job is not None
        await self.user_jobs.link(job.id)
        await self.session.commit()
        task = await self.tasks.create(
            "job_analyze",
            {"job_id": str(job.id), "version_id": str(version.id)},
            entity_type=JOB_ENTITY,
            entity_id=job.id,
        )
        return job, task

    async def best_for(
        self, job_ids: Sequence[uuid.UUID]
    ) -> tuple[dict[uuid.UUID, JobAnalysis], uuid.UUID | None]:
        version = await active_version(self.session, self.user_id)
        version_id = version.id if version else None
        return await self.analyses.best_for_jobs(job_ids, version_id), version_id
