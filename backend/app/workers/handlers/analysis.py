"""Phase 9 tasks: score one job, or a batch of jobs, against the active resume."""

import uuid
from typing import Any

import structlog

from app.core.errors import AppError, LimitExceededError
from app.models.enums import ParseStatus
from app.models.resumes import ResumeVersion
from app.repositories.analyses import JobAnalysisRepository
from app.repositories.jobs import JobRepository, UserJobRepository
from app.repositories.resumes import ResumeVersionRepository
from app.services.analysis import analyze_job, can_score
from app.workers.runner import TaskContext, handler

logger = structlog.get_logger("app.analysis")


class AnalysisTaskError(AppError):
    status_code = 409
    code = "ANALYSIS_FAILED"


def _owner(ctx: TaskContext) -> uuid.UUID:
    if ctx.user_id is None:
        raise AnalysisTaskError("Analysis tasks need an owner.")
    return ctx.user_id


async def _version(ctx: TaskContext) -> ResumeVersion:
    version = await ResumeVersionRepository(ctx.session, owner_id=_owner(ctx)).get(
        uuid.UUID(str(ctx.task.payload["version_id"]))
    )
    if version is None or version.parse_status is not ParseStatus.PARSED:
        raise AnalysisTaskError("The resume version is no longer available.")
    return version


@handler("job_analyze", "Match score", link="/jobs")
async def job_analyze(ctx: TaskContext) -> dict[str, Any]:
    owner = _owner(ctx)
    version = await _version(ctx)
    job_id = uuid.UUID(str(ctx.task.payload["job_id"]))
    job = await JobRepository(ctx.session).visible(job_id, owner)
    if job is None:
        raise AnalysisTaskError("The job no longer exists.")
    user_job = await UserJobRepository(ctx.session, owner_id=owner).for_job(job.id)
    await ctx.progress(10)
    analysis = await analyze_job(ctx.session, ctx.services.ai, owner, job, user_job, version)
    return {
        "job_id": str(job.id),
        "match_score": analysis.match_score,
        "decision": analysis.decision.value,
    }


@handler("job_analyze_batch", "Batch match scoring", link="/jobs")
async def job_analyze_batch(ctx: TaskContext) -> dict[str, Any]:
    """Score each job in turn; one failure does not stop the rest, the AI budget does."""
    owner = _owner(ctx)
    version = await _version(ctx)
    job_ids = [uuid.UUID(str(i)) for i in ctx.task.payload.get("job_ids", [])]
    jobs = JobRepository(ctx.session)
    user_jobs = UserJobRepository(ctx.session, owner_id=owner)
    analyses = JobAnalysisRepository(ctx.session, owner_id=owner)
    done = cached = failed = 0
    stopped: str | None = None
    errors: list[str] = []

    for index, job_id in enumerate(job_ids):
        await ctx.progress(round(100 * index / max(1, len(job_ids))))
        if await analyses.for_pair(job_id, version.id) is not None:
            cached += 1  # scored meanwhile (retry, or a single click)
            continue
        job = await jobs.visible(job_id, owner)
        user_job = await user_jobs.for_job(job_id)
        if job is None or not can_score(job, user_job):
            failed += 1
            continue
        title = job.title
        try:
            await analyze_job(ctx.session, ctx.services.ai, owner, job, user_job, version)
            done += 1
        except LimitExceededError as exc:
            stopped = exc.message  # monthly AI budget reached: stop, keep what is done
            break
        except AppError as exc:  # AI errors are raised before anything is written
            failed += 1
            errors.append(f"{title}: {exc.message}")
            logger.warning("analysis.batch_item_failed", job_id=str(job_id), error=exc.message)

    return {
        "scored": done,
        "already_scored": cached,
        "failed": failed,
        "stopped": stopped,
        "errors": errors[:5],
        "total": len(job_ids),
    }
