from fastapi import APIRouter, Request, status

from app.api.deps import AdminUser, DbSession, EngineDep, SettingsDep
from app.schemas.tasks import SystemStatus, TaskCreated
from app.services.system_status import SystemStatusService
from app.services.tasks import TaskService

router = APIRouter(prefix="/admin/system", tags=["admin"])


@router.get("", response_model=SystemStatus, summary="Health of every platform service")
async def system_status(
    request: Request, admin: AdminUser, db: DbSession, engine: EngineDep, settings: SettingsDep
) -> SystemStatus:
    state = request.app.state
    return await SystemStatusService(
        settings=settings,
        engine=engine,
        session=db,
        redis=state.redis,
        storage=state.storage,
        gotenberg=state.gotenberg,
    ).status()


@router.post(
    "/test-failure",
    response_model=TaskCreated,
    status_code=status.HTTP_202_ACCEPTED,
    summary="Start a task that always fails (shows retries and failure handling)",
)
async def test_failure(request: Request, admin: AdminUser, db: DbSession) -> TaskCreated:
    task = await TaskService(db, admin.id, request.app.state.dispatcher).create("test_failure")
    return TaskCreated(task_id=task.id)


@router.post(
    "/test-error",
    summary="Raise an unexpected error (checks error monitoring: Sentry / logs)",
)
async def test_error(admin: AdminUser) -> None:
    raise RuntimeError("Test error from Admin › System (monitoring check)")


@router.post(
    "/test-ai",
    response_model=TaskCreated,
    status_code=status.HTTP_202_ACCEPTED,
    summary="Send one tiny request to the AI provider (checks key, model, cost logging)",
)
async def test_ai(request: Request, admin: AdminUser, db: DbSession) -> TaskCreated:
    task = await TaskService(db, admin.id, request.app.state.dispatcher).create("ai_test")
    return TaskCreated(task_id=task.id)
