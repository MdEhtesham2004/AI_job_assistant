import uuid
from typing import Annotated

from fastapi import APIRouter, Query, Request, status

from app.api.deps import ApprovedUser, DbSession
from app.core.config import Settings
from app.models.enums import EmailStatus
from app.schemas.common import Page
from app.schemas.outreach import (
    ApproveBatch,
    ApproveBatchRead,
    AttachmentRead,
    DraftRequest,
    EmailApplication,
    EmailContact,
    EmailRead,
    EmailUpdate,
    OutboxSummaryRead,
)
from app.schemas.tasks import TaskCreated
from app.services.outreach import EmailService, EmailView
from app.services.tasks import download_url

router = APIRouter(tags=["outreach"])


def service(request: Request, db: DbSession, user: ApprovedUser) -> EmailService:
    state = request.app.state
    return EmailService(db, user.id, settings=state.settings, dispatcher=state.dispatcher)


def to_read(view: EmailView, settings: Settings) -> EmailRead:
    email, contact = view.email, view.contact
    return EmailRead(
        id=email.id,
        email_type=email.email_type,
        status=email.status,
        from_address=email.from_address,
        to_address=email.to_address,
        subject=email.subject,
        body_text=email.body_text,
        approved_at=email.approved_at,
        scheduled_for=email.scheduled_for,
        sent_at=email.sent_at,
        error=email.error,
        gmail_thread_id=email.gmail_thread_id,
        contact=EmailContact(
            id=contact.id,
            email=contact.email,
            name=contact.name,
            approval=contact.approval,
            verification=contact.verification,
            source=contact.source,
            source_url=contact.source_url,
            source_excerpt=contact.source_excerpt,
            role_title=contact.role_title,
        )
        if contact
        else None,
        application=EmailApplication(
            id=view.application.id,
            status=view.application.status,
            job_id=view.job.id,
            job_title=view.job.title,
            company=view.job.company,
            match_score=view.match_score,
        ),
        attachments=[
            AttachmentRead(
                id=item.id,
                file_name=item.file_name,
                mime_type=item.mime_type,
                file_size=item.file_size,
                download_url=download_url(
                    settings,
                    item.user_id,
                    key=item.file_key,
                    filename=item.file_name,
                    content_type=item.mime_type,
                ),
            )
            for item in view.attachments
        ],
        warnings=view.warnings,
        updated_at=email.updated_at,
    )


@router.post(
    "/applications/{application_id}/email/draft",
    response_model=TaskCreated,
    status_code=status.HTTP_202_ACCEPTED,
    summary="Write the application email (AI) — it waits for your approval",
)
async def draft_email(
    application_id: uuid.UUID,
    request: Request,
    db: DbSession,
    user: ApprovedUser,
    body: DraftRequest | None = None,
) -> TaskCreated:
    task = await service(request, db, user).start_draft(
        application_id, body.contact_id if body else None
    )
    return TaskCreated(task_id=task.id)


@router.get(
    "/applications/{application_id}/email",
    response_model=EmailRead | None,
    summary="The application's email (draft, scheduled or sent)",
)
async def application_email(
    application_id: uuid.UUID, request: Request, db: DbSession, user: ApprovedUser
) -> EmailRead | None:
    view = await service(request, db, user).for_application(application_id)
    return to_read(view, request.app.state.settings) if view else None


@router.get("/outbox", response_model=Page[EmailRead], summary="Drafts, scheduled, sent, failed")
async def outbox(
    request: Request,
    db: DbSession,
    user: ApprovedUser,
    status_: Annotated[list[EmailStatus] | None, Query(alias="status")] = None,
    page: Annotated[int, Query(ge=1)] = 1,
    page_size: Annotated[int, Query(ge=1, le=100)] = 50,
) -> Page[EmailRead]:
    views, total = await service(request, db, user).outbox(
        tuple(status_ or ()), page=page, page_size=page_size
    )
    settings = request.app.state.settings
    return Page(
        items=[to_read(v, settings) for v in views], total=total, page=page, page_size=page_size
    )


@router.get("/outbox/summary", response_model=OutboxSummaryRead, summary="Counts and send limits")
async def outbox_summary(request: Request, db: DbSession, user: ApprovedUser) -> OutboxSummaryRead:
    summary = await service(request, db, user).summary()
    return OutboxSummaryRead(**summary.__dict__)


@router.get("/emails/{email_id}", response_model=EmailRead, summary="One email")
async def email_detail(
    email_id: uuid.UUID, request: Request, db: DbSession, user: ApprovedUser
) -> EmailRead:
    return to_read(await service(request, db, user).detail(email_id), request.app.state.settings)


@router.put("/emails/{email_id}", response_model=EmailRead, summary="Edit a draft")
async def edit_email(
    email_id: uuid.UUID, body: EmailUpdate, request: Request, db: DbSession, user: ApprovedUser
) -> EmailRead:
    svc = service(request, db, user)
    email = await svc.edit(email_id, body.model_dump(exclude_unset=True))
    return to_read(await svc.view(email), request.app.state.settings)


async def _act(
    request: Request, db: DbSession, user: ApprovedUser, email_id: uuid.UUID, action: str
) -> EmailRead:
    svc = service(request, db, user)
    email = await getattr(svc, action)(email_id)
    return to_read(await svc.view(email), request.app.state.settings)


@router.post(
    "/emails/approve-batch",
    response_model=ApproveBatchRead,
    summary="Approve several drafts (each is scheduled with the send gap)",
)
async def approve_batch(
    body: ApproveBatch, request: Request, db: DbSession, user: ApprovedUser
) -> ApproveBatchRead:
    result = await service(request, db, user).approve_batch(
        body.email_ids, approve_contacts=body.approve_contacts
    )
    return ApproveBatchRead(approved=result.approved, errors=result.errors)


@router.post("/emails/{email_id}/approve", response_model=EmailRead, summary="Approve → schedule")
async def approve_email(
    email_id: uuid.UUID,
    request: Request,
    db: DbSession,
    user: ApprovedUser,
    approve_contact: bool = False,
) -> EmailRead:
    svc = service(request, db, user)
    email = await svc.approve(email_id, approve_contact=approve_contact)
    return to_read(await svc.view(email), request.app.state.settings)


@router.post("/emails/{email_id}/reject", response_model=EmailRead, summary="Do not send")
async def reject_email(
    email_id: uuid.UUID, request: Request, db: DbSession, user: ApprovedUser
) -> EmailRead:
    return await _act(request, db, user, email_id, "reject")


@router.post(
    "/emails/{email_id}/cancel", response_model=EmailRead, summary="Unschedule (back to draft)"
)
async def cancel_email(
    email_id: uuid.UUID, request: Request, db: DbSession, user: ApprovedUser
) -> EmailRead:
    return await _act(request, db, user, email_id, "cancel")


@router.post(
    "/emails/{email_id}/retry", response_model=EmailRead, summary="Failed → draft (approve again)"
)
async def retry_email(
    email_id: uuid.UUID, request: Request, db: DbSession, user: ApprovedUser
) -> EmailRead:
    return await _act(request, db, user, email_id, "retry")
