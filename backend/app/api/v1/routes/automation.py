import uuid

from fastapi import APIRouter, Request, status
from sqlalchemy import select

from app.api.deps import AdminUser, ApprovedUser, DbSession
from app.core.errors import NotFoundError
from app.integrations.ai import AiClient
from app.models.enums import ActorType
from app.models.outreach import ReplyClassification
from app.models.system import AuditLog
from app.repositories.applications import ApplicationRepository
from app.repositories.outreach import EmailRepository
from app.repositories.profiles import UserSettingsRepository
from app.schemas.outreach import (
    AutomationRun,
    AutomationRunRequest,
    AutomationStatus,
    PlatformSettings,
    ReplyClassificationRead,
    ReplyConfirm,
    ReplyRead,
)
from app.schemas.tasks import TaskCreated
from app.services.automation import (
    app_settings,
    fetch_allowed,
    fetch_problem,
    last_run,
    not_ready_reason,
    saved_job_ids,
    start_run,
)
from app.services.replies import ReplyTracker

router = APIRouter(tags=["automation"])


@router.get("/automation", response_model=AutomationStatus, summary="What automation can do now")
async def automation_status(
    request: Request, db: DbSession, user: ApprovedUser
) -> AutomationStatus:
    user_settings = await UserSettingsRepository(db, owner_id=user.id).get_or_create()
    reason = await not_ready_reason(db, request.app.state.settings, user.id)
    task = await last_run(db, user.id)
    return AutomationStatus(
        keywords=list(user_settings.automation_keywords),
        ready=reason is None,
        not_ready_reason=reason,
        saved_ready=len(await saved_job_ids(db, user.id)),
        fetch_allowed=await fetch_allowed(db),
        fetch_problem=fetch_problem(user_settings),
        max_jobs=user_settings.automation_max_jobs,
        last_run=AutomationRun(
            task_id=task.id,
            status=task.status.value,
            progress=task.progress,
            result=task.result,
            error=task.error,
            created_at=task.created_at,
            finished_at=task.finished_at,
        )
        if task
        else None,
    )


@router.post(
    "/automation/run",
    response_model=TaskCreated,
    status_code=status.HTTP_202_ACCEPTED,
    summary="Automate saved jobs, or fetch new LinkedIn posts first (admin-enabled)",
)
async def run_now(
    request: Request, db: DbSession, user: ApprovedUser, body: AutomationRunRequest | None = None
) -> TaskCreated:
    state = request.app.state
    mode = body.mode if body else "saved"
    task = await start_run(db, state.settings, user.id, state.dispatcher, mode)
    return TaskCreated(task_id=task.id)


# ---------- platform settings (admin) ----------


@router.get("/admin/platform", response_model=PlatformSettings, summary="Platform switches (admin)")
async def get_platform(admin: AdminUser, db: DbSession) -> PlatformSettings:
    row = await app_settings(db)
    await db.commit()
    return PlatformSettings(automation_fetch_enabled=row.automation_fetch_enabled)


@router.patch(
    "/admin/platform", response_model=PlatformSettings, summary="Change platform switches (admin)"
)
async def update_platform(
    body: PlatformSettings, admin: AdminUser, db: DbSession
) -> PlatformSettings:
    row = await app_settings(db)
    if row.automation_fetch_enabled != body.automation_fetch_enabled:
        row.automation_fetch_enabled = body.automation_fetch_enabled
        row.updated_by_id = admin.id
        db.add(
            AuditLog(
                user_id=admin.id,
                actor_type=ActorType.ADMIN,
                action="platform.automation_fetch",
                entity_type="app_settings",
                data={"enabled": body.automation_fetch_enabled},
            )
        )
    await db.commit()
    return PlatformSettings(automation_fetch_enabled=row.automation_fetch_enabled)


# ---------- replies ----------


@router.get(
    "/applications/{application_id}/replies",
    response_model=list[ReplyRead],
    summary="Replies in the application's Gmail thread, with their AI reading",
)
async def application_replies(
    application_id: uuid.UUID, db: DbSession, user: ApprovedUser
) -> list[ReplyRead]:
    if await ApplicationRepository(db, owner_id=user.id).get(application_id) is None:
        raise NotFoundError("Application not found.")
    inbound = await EmailRepository(db, owner_id=user.id).inbound_for(application_id)
    readings = {
        r.email_id: r
        for r in (
            await db.scalars(
                select(ReplyClassification).where(
                    ReplyClassification.user_id == user.id,
                    ReplyClassification.email_id.in_([e.id for e in inbound]),
                )
            )
        ).all()
    }
    return [
        ReplyRead(
            id=e.id,
            status=e.status,
            from_address=e.from_address,
            subject=e.subject,
            body_text=e.body_text,
            received_at=e.received_at,
            classification=ReplyClassificationRead.model_validate(readings[e.id])
            if e.id in readings
            else None,
        )
        for e in inbound
    ]


@router.post(
    "/replies/{classification_id}/confirm",
    response_model=ReplyClassificationRead,
    summary="Confirm (or dismiss) the status a reply suggests",
)
async def confirm_reply(
    classification_id: uuid.UUID,
    body: ReplyConfirm,
    request: Request,
    db: DbSession,
    user: ApprovedUser,
) -> ReplyClassificationRead:
    state = request.app.state
    tracker = ReplyTracker(db, user.id, state.settings, AiClient(state.settings, state.redis))
    classification = await tracker.confirm(classification_id, body.accept)
    return ReplyClassificationRead.model_validate(classification)
