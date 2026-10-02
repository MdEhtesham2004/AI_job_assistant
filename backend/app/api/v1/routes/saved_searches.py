import uuid

from fastapi import APIRouter, Request, status

from app.api.deps import ApprovedUser, DbSession
from app.models.jobs import SavedSearch
from app.schemas.jobs import (
    JobSearchStarted,
    SavedSearchCreate,
    SavedSearchRead,
    SavedSearchUpdate,
)
from app.services.saved_searches import SavedSearchService

router = APIRouter(prefix="/saved-searches", tags=["saved searches"])


def service(request: Request, db: DbSession, user: ApprovedUser) -> SavedSearchService:
    state = request.app.state
    return SavedSearchService(db, user.id, settings=state.settings, dispatcher=state.dispatcher)


async def to_read(svc: SavedSearchService, saved: SavedSearch) -> SavedSearchRead:
    return SavedSearchRead(
        id=saved.id,
        name=saved.name,
        keywords=saved.keywords,
        location=saved.location,
        experience=saved.experience,  # type: ignore[arg-type]
        remote_only=saved.remote_only,
        country=saved.country,
        schedule_cron=saved.schedule_cron,
        is_active=saved.is_active,
        last_run_at=saved.last_run_at,
        next_run_at=svc.next_run_at(saved, await svc.timezone()),
        created_at=saved.created_at,
    )


@router.get("", response_model=list[SavedSearchRead], summary="Your saved searches")
async def list_saved(request: Request, db: DbSession, user: ApprovedUser) -> list[SavedSearchRead]:
    svc = service(request, db, user)
    return [await to_read(svc, saved) for saved in await svc.list()]


@router.post(
    "",
    response_model=SavedSearchRead,
    status_code=status.HTTP_201_CREATED,
    summary="Save a search that runs on a schedule (cron, in your time zone)",
)
async def create_saved(
    body: SavedSearchCreate, request: Request, db: DbSession, user: ApprovedUser
) -> SavedSearchRead:
    svc = service(request, db, user)
    return await to_read(svc, await svc.create(body))


@router.patch("/{search_id}", response_model=SavedSearchRead, summary="Edit, pause or resume")
async def update_saved(
    search_id: uuid.UUID,
    body: SavedSearchUpdate,
    request: Request,
    db: DbSession,
    user: ApprovedUser,
) -> SavedSearchRead:
    svc = service(request, db, user)
    return await to_read(svc, await svc.update(search_id, body))


@router.delete("/{search_id}", status_code=status.HTTP_204_NO_CONTENT, summary="Delete (jobs stay)")
async def delete_saved(
    search_id: uuid.UUID, request: Request, db: DbSession, user: ApprovedUser
) -> None:
    await service(request, db, user).delete(search_id)


@router.post(
    "/{search_id}/run",
    response_model=JobSearchStarted,
    status_code=status.HTTP_202_ACCEPTED,
    summary="Run a saved search now",
)
async def run_saved(
    search_id: uuid.UUID, request: Request, db: DbSession, user: ApprovedUser
) -> JobSearchStarted:
    run, task_id = await service(request, db, user).run_now(search_id)
    return JobSearchStarted(task_id=task_id, run_id=run.id)
