import uuid
from typing import Annotated

from fastapi import APIRouter, Query, Request, status

from app.api.deps import ApprovedUser, DbSession, SettingsDep
from app.core.config import Settings
from app.models.system import Task
from app.schemas.common import Page
from app.schemas.tasks import TaskCreated, TaskRead
from app.services.tasks import TaskService, public_result

router = APIRouter(prefix="/tasks", tags=["tasks"])


def to_read(task: Task, settings: Settings) -> TaskRead:
    return TaskRead(
        id=task.id,
        type=task.type,
        status=task.status,
        progress=task.progress,
        attempts=task.attempts,
        result=public_result(task, settings),
        error=task.error,
        created_at=task.created_at,
        started_at=task.started_at,
        finished_at=task.finished_at,
    )


def service(request: Request, db: DbSession, user: ApprovedUser) -> TaskService:
    return TaskService(db, user.id, request.app.state.dispatcher)


@router.get("", response_model=Page[TaskRead], summary="Your background tasks, newest first")
async def list_tasks(
    request: Request,
    db: DbSession,
    user: ApprovedUser,
    settings: SettingsDep,
    page: Annotated[int, Query(ge=1)] = 1,
    page_size: Annotated[int, Query(ge=1, le=100)] = 20,
) -> Page[TaskRead]:
    tasks, total = await service(request, db, user).list(page=page, page_size=page_size)
    return Page(
        items=[to_read(t, settings) for t in tasks], total=total, page=page, page_size=page_size
    )


@router.get("/{task_id}", response_model=TaskRead, summary="One task (poll for progress)")
async def get_task(
    task_id: uuid.UUID, request: Request, db: DbSession, user: ApprovedUser, settings: SettingsDep
) -> TaskRead:
    return to_read(await service(request, db, user).get(task_id), settings)


@router.post(
    "/test-pdf",
    response_model=TaskCreated,
    status_code=status.HTTP_202_ACCEPTED,
    summary="Generate a test PDF in the background",
)
async def create_test_pdf(request: Request, db: DbSession, user: ApprovedUser) -> TaskCreated:
    task = await service(request, db, user).create("test_pdf")
    return TaskCreated(task_id=task.id)
