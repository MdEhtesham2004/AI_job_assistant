import uuid
from collections.abc import Sequence
from datetime import UTC, datetime
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, Query, Request, Response, status

from app.api.deps import ApprovedUser, DbSession
from app.models.enums import JobSource, UserJobState
from app.models.jobs import JobSearchRun
from app.models.system import Task
from app.repositories.jobs import JobFilters
from app.schemas.common import Page
from app.schemas.jobs import (
    ActiveJobTask,
    AnalysisRead,
    AnalyzeRequest,
    AnalyzeStarted,
    BatchStarted,
    BatchSummary,
    JobCounts,
    JobDetail,
    JobSearchRequest,
    JobSearchStarted,
    JobSummary,
    JobUpdate,
    ScanTextRequest,
    ScanTextStarted,
    SearchResultJob,
    SearchRunDetail,
    SearchRunRead,
    SuggestedRoles,
)
from app.schemas.tasks import TaskCreated
from app.services.analysis import AnalysisService
from app.services.jobs import JobService, JobView, can_load_more, pages_loaded

router = APIRouter(prefix="/jobs", tags=["jobs"])


def service(request: Request, db: DbSession, user: ApprovedUser) -> JobService:
    state = request.app.state
    return JobService(db, user.id, settings=state.settings, dispatcher=state.dispatcher)


def to_summary(view: JobView) -> JobSummary:
    job, user_job = view.job, view.user_job
    return JobSummary(
        id=job.id,
        title=job.title,
        company=job.company,
        location=job.location,
        is_remote=job.is_remote,
        employment_type=job.employment_type,
        posted_at=job.posted_at,
        apply_url=job.apply_url,
        source=job.source,
        description_quality=view.quality,
        state=user_job.state if user_job else None,
        first_found_at=user_job.first_found_at if user_job else None,
        match_score=view.analysis.match_score if view.analysis else None,
        decision=view.analysis.decision if view.analysis else None,
        score_stale=view.score_stale,
    )


def to_detail(view: JobView, active: Sequence[Task] = ()) -> JobDetail:
    job, user_job = view.job, view.user_job
    return JobDetail(
        **to_summary(view).model_dump(),
        description=view.description,
        has_own_description=bool(user_job and user_job.description_override),
        notes=user_job.notes if user_job else None,
        company_domain=job.company_domain,
        salary_min=job.salary_min,
        salary_max=job.salary_max,
        salary_currency=job.salary_currency,
        first_seen_at=job.first_seen_at,
        last_seen_at=job.last_seen_at,
        active_tasks=[
            ActiveJobTask(id=t.id, type=t.type, status=t.status, progress=t.progress)
            for t in active
        ],
        analysis=AnalysisRead.model_validate(view.analysis) if view.analysis else None,
    )


@router.post(
    "/search",
    response_model=JobSearchStarted,
    status_code=status.HTTP_202_ACCEPTED,
    summary="Search JSearch in the background; results are stored and added to your jobs",
)
async def search(
    body: JobSearchRequest, request: Request, db: DbSession, user: ApprovedUser
) -> JobSearchStarted:
    run, task = await service(request, db, user).start_search(body)
    return JobSearchStarted(task_id=task.id, run_id=run.id)


def to_run(run: JobSearchRun) -> SearchRunRead:
    return SearchRunRead(
        id=run.id,
        saved_search_id=run.saved_search_id,
        task_id=run.task_id,
        status=run.status,
        query=run.query,
        results_count=run.results_count,
        new_jobs_count=run.new_jobs_count,
        error=run.error,
        created_at=run.created_at,
        finished_at=run.finished_at,
        pages_loaded=pages_loaded(run),
        can_load_more=can_load_more(run),
    )


@router.get("/searches", response_model=list[SearchRunRead], summary="Your recent searches")
async def recent_searches(
    request: Request, db: DbSession, user: ApprovedUser
) -> list[SearchRunRead]:
    runs = await service(request, db, user).recent_runs()
    return [to_run(run) for run in runs]


@router.post(
    "/searches/{run_id}/more",
    response_model=JobSearchStarted,
    status_code=status.HTTP_202_ACCEPTED,
    summary="Load the next page of results (one JSearch request)",
)
async def load_more(
    run_id: uuid.UUID, request: Request, db: DbSession, user: ApprovedUser
) -> JobSearchStarted:
    run, task = await service(request, db, user).load_more(run_id)
    return JobSearchStarted(task_id=task.id, run_id=run.id)


@router.get("/searches/{run_id}", response_model=SearchRunDetail, summary="One search and its jobs")
async def search_detail(
    run_id: uuid.UUID, request: Request, db: DbSession, user: ApprovedUser
) -> SearchRunDetail:
    run, results = await service(request, db, user).run_detail(run_id)
    return SearchRunDetail(
        **to_run(run).model_dump(),
        jobs=[
            SearchResultJob(**to_summary(view).model_dump(), is_new=is_new)
            for view, is_new in results
        ],
    )


@router.get(
    "/suggested-roles",
    response_model=SuggestedRoles,
    summary="Job titles to search for, from your active resume's ATS report",
)
async def suggested_roles(request: Request, db: DbSession, user: ApprovedUser) -> SuggestedRoles:
    roles, location, hint = await service(request, db, user).suggested_roles()
    return SuggestedRoles(roles=roles, location=location, hint=hint)


@router.get("/counts", response_model=JobCounts, summary="Number of your jobs per state")
async def counts(request: Request, db: DbSession, user: ApprovedUser) -> JobCounts:
    return JobCounts(**await service(request, db, user).counts())


def job_filters(
    state: UserJobState | None = None,
    source: JobSource | None = None,
    posted_within_days: Annotated[int | None, Query(ge=1, le=365)] = None,
    q: Annotated[str | None, Query(max_length=100)] = None,
    location: Annotated[str | None, Query(max_length=100)] = None,
    remote_only: bool = False,
    min_score: Annotated[int | None, Query(ge=0, le=100)] = None,
    sort: Literal["posted", "found", "company", "score"] = "posted",
) -> JobFilters:
    """Shared by the list, the CSV export and batch scoring: the same view everywhere."""
    return JobFilters(
        state=state,
        source=source,
        posted_within_days=posted_within_days,
        q=q,
        location=location,
        remote_only=remote_only,
        min_score=min_score,
        sort=sort,
    )


Filters = Annotated[JobFilters, Depends(job_filters)]


@router.get("", response_model=Page[JobSummary], summary="Your jobs, with filters and sorting")
async def list_jobs(
    request: Request,
    db: DbSession,
    user: ApprovedUser,
    filters: Filters,
    page: Annotated[int, Query(ge=1)] = 1,
    page_size: Annotated[int, Query(ge=1, le=100)] = 20,
) -> Page[JobSummary]:
    views, total = await service(request, db, user).list(filters, page=page, page_size=page_size)
    return Page(items=[to_summary(v) for v in views], total=total, page=page, page_size=page_size)


@router.get(
    "/export.csv",
    response_class=Response,
    summary="Download your jobs as CSV (same filters as the list, all pages)",
    responses={200: {"content": {"text/csv": {}}}},
)
async def export_csv(
    request: Request,
    db: DbSession,
    user: ApprovedUser,
    filters: Filters,
    include_description: bool = False,
) -> Response:
    content = await service(request, db, user).export_csv(
        filters, include_description=include_description
    )
    label = filters.state.value if filters.state else "inbox"
    name = f"jobs-{label}-{datetime.now(UTC):%Y-%m-%d}.csv"
    return Response(
        content=content,
        media_type="text/csv; charset=utf-8",
        headers={
            "Content-Disposition": f'attachment; filename="{name}"',
            "Cache-Control": "private, no-store",
        },
    )


# ---------- Phase 9: match scores (on demand only) ----------


def analysis_service(request: Request, db: DbSession, user: ApprovedUser) -> AnalysisService:
    state = request.app.state
    return AnalysisService(db, user.id, settings=state.settings, dispatcher=state.dispatcher)


@router.get(
    "/analysis-summary",
    response_model=BatchSummary,
    summary="How many jobs in this view still need a match score",
)
async def analysis_summary(
    request: Request, db: DbSession, user: ApprovedUser, filters: Filters
) -> BatchSummary:
    _, plan = await analysis_service(request, db, user).plan_batch(filters)
    return BatchSummary(
        to_score=len(plan.job_ids),
        already_scored=plan.already_scored,
        no_description=plan.no_description,
        over_limit=plan.over_limit,
    )


@router.post(
    "/analyze-batch",
    response_model=BatchStarted,
    summary="Score every unscored job in this view (max 50 per click)",
)
async def analyze_batch(
    request: Request, db: DbSession, user: ApprovedUser, filters: Filters
) -> BatchStarted:
    task, plan = await analysis_service(request, db, user).start_batch(filters)
    return BatchStarted(
        task_id=task.id if task else None,
        to_score=len(plan.job_ids),
        already_scored=plan.already_scored,
        no_description=plan.no_description,
        over_limit=plan.over_limit,
    )


@router.post(
    "/scan-text",
    response_model=ScanTextStarted,
    status_code=status.HTTP_202_ACCEPTED,
    summary="Score a pasted job description (saved as a private job)",
)
async def scan_text(
    body: ScanTextRequest, request: Request, db: DbSession, user: ApprovedUser
) -> ScanTextStarted:
    job, task = await analysis_service(request, db, user).scan_text(
        body.title, body.company, body.description
    )
    return ScanTextStarted(job_id=job.id, task_id=task.id)


@router.post(
    "/{job_id}/analyze",
    response_model=AnalyzeStarted,
    summary="Get a match score for this job against your active resume",
)
async def analyze(
    job_id: uuid.UUID,
    request: Request,
    db: DbSession,
    user: ApprovedUser,
    body: AnalyzeRequest | None = None,
) -> AnalyzeStarted:
    task = await analysis_service(request, db, user).start(job_id, force=bool(body and body.force))
    return AnalyzeStarted(task_id=task.id if task else None, cached=task is None)


@router.get("/{job_id}", response_model=JobDetail, summary="One job with its description")
async def job_detail(
    job_id: uuid.UUID, request: Request, db: DbSession, user: ApprovedUser
) -> JobDetail:
    view, active = await service(request, db, user).detail(job_id)
    return to_detail(view, active)


@router.patch(
    "/{job_id}",
    response_model=JobDetail,
    summary="Save / skip / archive a job, add notes, or paste its description",
)
async def update_job(
    job_id: uuid.UUID, body: JobUpdate, request: Request, db: DbSession, user: ApprovedUser
) -> JobDetail:
    return to_detail(await service(request, db, user).update(job_id, body))


@router.post(
    "/{job_id}/fetch-description",
    response_model=TaskCreated,
    status_code=status.HTTP_202_ACCEPTED,
    summary="Try to read the full description from the job's public page",
)
async def fetch_description(
    job_id: uuid.UUID, request: Request, db: DbSession, user: ApprovedUser
) -> TaskCreated:
    task = await service(request, db, user).start_fetch_description(job_id)
    return TaskCreated(task_id=task.id)
