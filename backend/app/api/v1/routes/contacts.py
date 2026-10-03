import uuid
from datetime import UTC, datetime
from typing import Annotated

from fastapi import APIRouter, Query, Request, Response, status

from app.api.deps import ApprovedUser, DbSession
from app.models.enums import ContactApproval, ContactSource
from app.models.jobs import Job
from app.models.outreach import Contact
from app.repositories.outreach import ContactFilters
from app.schemas.common import Page
from app.schemas.outreach import (
    ContactCounts,
    ContactCreate,
    ContactJob,
    ContactRead,
    ContactUpdate,
    DiscoverRequest,
    DoNotContactCreate,
    DoNotContactRead,
)
from app.schemas.tasks import TaskCreated
from app.services.contacts import ContactService

router = APIRouter(tags=["contacts"])


def service(request: Request, db: DbSession, user: ApprovedUser) -> ContactService:
    state = request.app.state
    return ContactService(db, user.id, checker=state.domain_checker, dispatcher=state.dispatcher)


def to_read(contact: Contact, job: Job | None, blocked: bool) -> ContactRead:
    return ContactRead(
        id=contact.id,
        email=contact.email,
        name=contact.name,
        role_title=contact.role_title,
        company=contact.company,
        source=contact.source,
        source_url=contact.source_url,
        source_excerpt=contact.source_excerpt,
        verification=contact.verification,
        verified_at=contact.verified_at,
        approval=contact.approval,
        approved_at=contact.approved_at,
        blocked=blocked,
        job=ContactJob(id=job.id, title=job.title, company=job.company) if job else None,
        created_at=contact.created_at,
    )


@router.get("/contacts", response_model=Page[ContactRead], summary="Your contacts")
async def list_contacts(
    request: Request,
    db: DbSession,
    user: ApprovedUser,
    approval: ContactApproval | None = None,
    source: ContactSource | None = None,
    job_id: uuid.UUID | None = None,
    q: Annotated[str | None, Query(max_length=100)] = None,
    page: Annotated[int, Query(ge=1)] = 1,
    page_size: Annotated[int, Query(ge=1, le=200)] = 50,
) -> Page[ContactRead]:
    views, total = await service(request, db, user).list(
        ContactFilters(approval=approval, source=source, job_id=job_id, q=q),
        page=page,
        page_size=page_size,
    )
    return Page(
        items=[to_read(v.contact, v.job, v.blocked) for v in views],
        total=total,
        page=page,
        page_size=page_size,
    )


@router.get(
    "/contacts/export.csv",
    response_class=Response,
    summary="Download your contacts with their jobs as CSV (same filters as the list)",
    responses={200: {"content": {"text/csv": {}}}},
)
async def export_contacts(
    request: Request,
    db: DbSession,
    user: ApprovedUser,
    approval: ContactApproval | None = None,
    source: ContactSource | None = None,
    job_id: uuid.UUID | None = None,
    q: Annotated[str | None, Query(max_length=100)] = None,
) -> Response:
    content = await service(request, db, user).export_csv(
        ContactFilters(approval=approval, source=source, job_id=job_id, q=q)
    )
    name = f"contacts-{datetime.now(UTC):%Y-%m-%d}.csv"
    return Response(
        content=content,
        media_type="text/csv; charset=utf-8",
        headers={
            "Content-Disposition": f'attachment; filename="{name}"',
            "Cache-Control": "private, no-store",
        },
    )


@router.get("/contacts/counts", response_model=ContactCounts, summary="Count per approval state")
async def contact_counts(request: Request, db: DbSession, user: ApprovedUser) -> ContactCounts:
    counts = await service(request, db, user).counts()
    return ContactCounts(counts=counts, total=sum(counts.values()))


@router.post(
    "/contacts",
    response_model=ContactRead,
    status_code=status.HTTP_201_CREATED,
    summary="Add a contact yourself (approved straight away)",
)
async def create_contact(
    body: ContactCreate, request: Request, db: DbSession, user: ApprovedUser
) -> ContactRead:
    svc = service(request, db, user)
    contact = await svc.create(**body.model_dump())
    view = await svc.view(contact)
    return to_read(view.contact, view.job, view.blocked)


@router.post(
    "/contacts/discover",
    response_model=TaskCreated,
    status_code=status.HTTP_202_ACCEPTED,
    summary="Find LinkedIn hiring posts that publish an email (Apify)",
)
async def discover_contacts(
    body: DiscoverRequest, request: Request, db: DbSession, user: ApprovedUser
) -> TaskCreated:
    task = await service(request, db, user).start_discovery(
        body.keyword, max_posts=body.max_posts, posted_limit=body.posted_limit
    )
    return TaskCreated(task_id=task.id)


@router.patch(
    "/contacts/{contact_id}", response_model=ContactRead, summary="Edit / approve / reject"
)
async def update_contact(
    contact_id: uuid.UUID,
    body: ContactUpdate,
    request: Request,
    db: DbSession,
    user: ApprovedUser,
) -> ContactRead:
    svc = service(request, db, user)
    view = await svc.view(await svc.update(contact_id, body.model_dump(exclude_unset=True)))
    return to_read(view.contact, view.job, view.blocked)


@router.post(
    "/contacts/{contact_id}/verify", response_model=ContactRead, summary="Check the address again"
)
async def verify_contact(
    contact_id: uuid.UUID, request: Request, db: DbSession, user: ApprovedUser
) -> ContactRead:
    svc = service(request, db, user)
    view = await svc.view(await svc.reverify(contact_id))
    return to_read(view.contact, view.job, view.blocked)


@router.delete("/contacts/{contact_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_contact(
    contact_id: uuid.UUID, request: Request, db: DbSession, user: ApprovedUser
) -> None:
    await service(request, db, user).delete(contact_id)


@router.get(
    "/do-not-contact", response_model=list[DoNotContactRead], summary="Addresses never emailed"
)
async def list_blocked(
    request: Request, db: DbSession, user: ApprovedUser
) -> list[DoNotContactRead]:
    return [
        DoNotContactRead.model_validate(e) for e in await service(request, db, user).blocked_list()
    ]


@router.post(
    "/do-not-contact",
    response_model=DoNotContactRead,
    status_code=status.HTTP_201_CREATED,
    summary="Never email this address or domain",
)
async def add_blocked(
    body: DoNotContactCreate, request: Request, db: DbSession, user: ApprovedUser
) -> DoNotContactRead:
    entry = await service(request, db, user).block(
        email=body.email, domain=body.domain, reason=body.reason
    )
    return DoNotContactRead.model_validate(entry)


@router.delete("/do-not-contact/{entry_id}", status_code=status.HTTP_204_NO_CONTENT)
async def remove_blocked(
    entry_id: uuid.UUID, request: Request, db: DbSession, user: ApprovedUser
) -> None:
    await service(request, db, user).unblock(entry_id)
