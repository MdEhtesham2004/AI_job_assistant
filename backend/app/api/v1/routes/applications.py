import uuid
from datetime import UTC, datetime
from typing import Annotated, Literal

from fastapi import APIRouter, Query, Request, Response, status

from app.api.deps import ApprovedUser, DbSession
from app.core.config import Settings
from app.models.enums import ApplicationChannel, ApplicationStatus
from app.repositories.applications import ApplicationFilters
from app.schemas.applications import (
    ApplicationCounts,
    ApplicationCreate,
    ApplicationDetail,
    ApplicationJob,
    ApplicationSummary,
    ApplicationUpdate,
    ContactRef,
    CoverLetterRef,
    HistoryEntry,
    MarkApplied,
    ResumeRef,
    StatusChange,
)
from app.schemas.common import Page
from app.services.applications import ApplicationService, ApplicationView
from app.services.tasks import download_url

router = APIRouter(tags=["applications"])


def service(db: DbSession, user: ApprovedUser) -> ApplicationService:
    return ApplicationService(db, user.id)


def to_summary(view: ApplicationView) -> ApplicationSummary:
    a, job = view.application, view.job
    return ApplicationSummary(
        id=a.id,
        job=ApplicationJob(
            id=job.id,
            title=job.title,
            company=job.company,
            location=job.location,
            apply_url=job.apply_url,
        ),
        channel=a.channel,
        status=a.status,
        next_action=a.next_action,
        applied_at=a.applied_at,
        last_status_at=a.last_status_at,
        created_at=a.created_at,
        match_score=view.analysis.match_score if view.analysis else None,
    )


def to_detail(view: ApplicationView, settings: Settings) -> ApplicationDetail:
    resume, letter = view.resume, view.cover_letter
    return ApplicationDetail(
        **to_summary(view).model_dump(),
        resume=ResumeRef(
            id=resume.id,
            version_no=resume.version_no,
            kind=resume.kind,
            file_name=resume.file_name,
            download_url=download_url(
                settings,
                resume.user_id,
                key=resume.file_key,
                filename=resume.file_name,
                content_type=resume.mime_type,
            ),
        )
        if resume
        else None,
        cover_letter=CoverLetterRef(
            id=letter.id,
            status=letter.status,
            download_url=download_url(
                settings,
                letter.user_id,
                key=letter.file_key,
                filename=f"Cover letter - {view.job.company}.pdf",
                content_type="application/pdf",
            )
            if letter.file_key
            else None,
        )
        if letter
        else None,
        contact=ContactRef(
            id=view.contact.id,
            email=view.contact.email,
            name=view.contact.name,
            approval=view.contact.approval,
            verification=view.contact.verification,
        )
        if view.contact
        else None,
        history=[HistoryEntry.model_validate(entry) for entry in view.history],
        allowed_next=view.options,
    )


def _filters(
    status_: list[ApplicationStatus] | None,
    channel: ApplicationChannel | None,
    q: str | None,
    sort: str,
) -> ApplicationFilters:
    return ApplicationFilters(statuses=tuple(status_ or ()), channel=channel, q=q, sort=sort)


@router.post(
    "/jobs/{job_id}/applications",
    response_model=ApplicationDetail,
    status_code=status.HTTP_201_CREATED,
    summary="Prepare an application for this job (one per job)",
)
async def create_application(
    job_id: uuid.UUID, body: ApplicationCreate, request: Request, db: DbSession, user: ApprovedUser
) -> ApplicationDetail:
    svc = service(db, user)
    application = await svc.create(
        job_id,
        channel=body.channel,
        resume_version_id=body.resume_version_id,
        cover_letter_id=body.cover_letter_id,
        next_action=body.next_action,
        contact_id=body.contact_id,
    )
    return to_detail(await svc.view(application), request.app.state.settings)


@router.get(
    "/jobs/{job_id}/application",
    response_model=ApplicationDetail | None,
    summary="The application for this job, if there is one",
)
async def application_for_job(
    job_id: uuid.UUID, request: Request, db: DbSession, user: ApprovedUser
) -> ApplicationDetail | None:
    view = await service(db, user).for_job(job_id)
    return to_detail(view, request.app.state.settings) if view else None


@router.get("/applications", response_model=Page[ApplicationSummary], summary="Your applications")
async def list_applications(
    db: DbSession,
    user: ApprovedUser,
    status_: Annotated[list[ApplicationStatus] | None, Query(alias="status")] = None,
    channel: ApplicationChannel | None = None,
    q: Annotated[str | None, Query(max_length=100)] = None,
    sort: Literal["updated", "applied", "company"] = "updated",
    page: Annotated[int, Query(ge=1)] = 1,
    page_size: Annotated[int, Query(ge=1, le=200)] = 50,
) -> Page[ApplicationSummary]:
    views, total = await service(db, user).list(
        _filters(status_, channel, q, sort), page=page, page_size=page_size
    )
    return Page(items=[to_summary(v) for v in views], total=total, page=page, page_size=page_size)


@router.get("/applications/counts", response_model=ApplicationCounts, summary="Count per status")
async def application_counts(db: DbSession, user: ApprovedUser) -> ApplicationCounts:
    counts = await service(db, user).counts()
    return ApplicationCounts(counts=counts, total=sum(counts.values()))


@router.get(
    "/applications/export.csv",
    response_class=Response,
    summary="Download your applications as CSV",
    responses={200: {"content": {"text/csv": {}}}},
)
async def export_applications(
    db: DbSession,
    user: ApprovedUser,
    status_: Annotated[list[ApplicationStatus] | None, Query(alias="status")] = None,
    channel: ApplicationChannel | None = None,
    q: Annotated[str | None, Query(max_length=100)] = None,
    sort: Literal["updated", "applied", "company"] = "updated",
) -> Response:
    content = await service(db, user).export_csv(_filters(status_, channel, q, sort))
    name = f"applications-{datetime.now(UTC):%Y-%m-%d}.csv"
    return Response(
        content=content,
        media_type="text/csv; charset=utf-8",
        headers={
            "Content-Disposition": f'attachment; filename="{name}"',
            "Cache-Control": "private, no-store",
        },
    )


@router.get(
    "/applications/{application_id}",
    response_model=ApplicationDetail,
    summary="One application with its timeline",
)
async def application_detail(
    application_id: uuid.UUID, request: Request, db: DbSession, user: ApprovedUser
) -> ApplicationDetail:
    view = await service(db, user).detail(application_id)
    return to_detail(view, request.app.state.settings)


@router.patch(
    "/applications/{application_id}",
    response_model=ApplicationDetail,
    summary="Change next action, or (before it goes out) resume, cover letter, channel",
)
async def update_application(
    application_id: uuid.UUID,
    body: ApplicationUpdate,
    request: Request,
    db: DbSession,
    user: ApprovedUser,
) -> ApplicationDetail:
    svc = service(db, user)
    application = await svc.update(application_id, body.model_dump(exclude_unset=True))
    return to_detail(await svc.view(application), request.app.state.settings)


@router.post(
    "/applications/{application_id}/status",
    response_model=ApplicationDetail,
    summary="Move the application to another status (only allowed steps)",
)
async def change_status(
    application_id: uuid.UUID,
    body: StatusChange,
    request: Request,
    db: DbSession,
    user: ApprovedUser,
) -> ApplicationDetail:
    svc = service(db, user)
    application = await svc.transition(application_id, body.to_status, note=body.note)
    return to_detail(await svc.view(application), request.app.state.settings)


@router.post(
    "/applications/{application_id}/mark-applied",
    response_model=ApplicationDetail,
    summary="You applied on the company's site (portal) or via a referral",
)
async def mark_applied(
    application_id: uuid.UUID,
    request: Request,
    db: DbSession,
    user: ApprovedUser,
    body: MarkApplied | None = None,
) -> ApplicationDetail:
    svc = service(db, user)
    application = await svc.mark_applied(application_id, body.note if body else None)
    return to_detail(await svc.view(application), request.app.state.settings)
