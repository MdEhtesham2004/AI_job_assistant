"""Phase 8 tasks: run a job search, read a job's public page for its description."""

import uuid
from datetime import UTC, datetime
from typing import Any

from app.core.errors import AppError, ExternalServiceError
from app.domain.jobs import Experience, JobQuery, classify_description
from app.integrations.job_page import PageFetchError, fetch_job_description
from app.models.enums import DescriptionQuality, NotificationSeverity, SearchRunStatus
from app.models.jobs import JobSearchRun, SavedSearch
from app.repositories.jobs import JobRepository, JobSearchRunRepository
from app.services.job_catalog import store_results
from app.services.notifications import notify
from app.services.usage import Meter, MeteredJobSource
from app.workers.runner import TaskContext, handler


class JobTaskError(AppError):
    status_code = 409
    code = "JOB_TASK_FAILED"


def _owner(ctx: TaskContext) -> uuid.UUID:
    if ctx.user_id is None:
        raise JobTaskError("Job tasks need an owner.")
    return ctx.user_id


JSEARCH_PAGE_SIZE = 10


def _query(run: JobSearchRun, page: int, num_pages: int) -> JobQuery:
    q = run.query
    return JobQuery(
        page=page,
        keywords=q["keywords"],
        location=q.get("location"),
        experience=Experience(q["experience"]) if q.get("experience") else None,
        remote_only=bool(q.get("remote_only")),
        country=q.get("country") or "in",
        date_posted=q.get("date_posted") or "week",
        num_pages=num_pages,
    )


@handler("job_search", "Job search", link="/jobs")
async def job_search(ctx: TaskContext) -> dict[str, Any]:
    owner = _owner(ctx)
    run = await JobSearchRunRepository(ctx.session, owner_id=owner).get(
        uuid.UUID(str(ctx.task.payload.get("run_id")))
    )
    if run is None:
        raise JobTaskError("The search no longer exists.")
    run.status = SearchRunStatus.RUNNING
    run.started_at = run.started_at or datetime.now(UTC)
    run.error = None
    await ctx.progress(10)

    settings = ctx.services.settings
    # First run: pages 1..num_pages. "Load more": the payload names the next page.
    page = int(ctx.task.payload.get("page") or 1)
    num_pages = int(ctx.task.payload.get("num_pages") or run.query.get("num_pages") or 1)
    # Shared cache + per-user quota + usage log (Phase 14 cost control).
    source = MeteredJobSource(
        Meter(ctx.session, settings, ctx.services.redis, owner), ctx.services.jobs
    )
    try:
        items = await source.search(_query(run, page, num_pages))
    except AppError as exc:
        retrying = (
            isinstance(exc, ExternalServiceError) and ctx.task.attempts <= settings.task_max_retries
        )
        if not retrying:
            run.status = SearchRunStatus.FAILED
            run.error = exc.message
            run.finished_at = datetime.now(UTC)
            await ctx.session.commit()
        raise
    await ctx.progress(60)

    stored = await store_results(
        ctx.session, owner, run.id, items, dedupe_days=settings.job_dedupe_days
    )
    run.status = SearchRunStatus.SUCCEEDED
    run.results_count += stored.results
    run.new_jobs_count += stored.new_for_user
    run.finished_at = datetime.now(UTC)
    run.query = {  # new dict so the JSONB change is saved
        **run.query,
        "pages_loaded": page + num_pages - 1,
        # A short page means JSearch has nothing further for this query.
        "exhausted": len(items) < JSEARCH_PAGE_SIZE * num_pages,
    }

    if run.saved_search_id:
        # Scheduled runs only notify when there is something new.
        ctx.notify_on_success = False
        saved = await ctx.session.get(SavedSearch, run.saved_search_id)
        if stored.new_for_user and saved is not None:
            plural = "s" if stored.new_for_user != 1 else ""
            notify(
                ctx.session,
                owner,
                type="saved_search_new_jobs",
                title=f"{stored.new_for_user} new job{plural} for “{saved.name}”",
                link=f"/jobs/searches/{run.id}",
                severity=NotificationSeverity.SUCCESS,
            )
    return {
        "run_id": str(run.id),
        "page": page,
        "num_pages": num_pages,
        "results": stored.results,
        "new_jobs": stored.new_for_user,
        "new_in_catalog": stored.new_in_catalog,
    }


@handler("job_fetch_page", "Job description fetch", link="/jobs")
async def job_fetch_page(ctx: TaskContext) -> dict[str, Any]:
    owner = _owner(ctx)
    job = await JobRepository(ctx.session).visible(
        uuid.UUID(str(ctx.task.payload.get("job_id"))), owner
    )
    if job is None or not job.apply_url:
        raise JobTaskError("The job or its apply link no longer exists.")
    await ctx.progress(20)
    try:
        text = await fetch_job_description(job.apply_url, ctx.services.settings)
    except PageFetchError as exc:
        raise JobTaskError(f"{exc.reason} Please paste the job description instead.") from exc

    quality = classify_description(text)
    if quality is DescriptionQuality.MISSING or len(text) <= len(job.description or ""):
        raise JobTaskError(
            "No better job description was found on the page. Please paste it instead."
        )
    job.description = text  # public page text → stored on the shared job for everyone
    job.description_quality = quality
    return {"job_id": str(job.id), "quality": quality.value, "characters": len(text)}
