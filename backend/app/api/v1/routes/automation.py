import uuid

from fastapi import APIRouter, Request, status
from sqlalchemy import select

from app.api.deps import AdminUser, ApprovedUser, DbSession
from app.core.errors import NotFoundError
from app.integrations.ai import AiClient
from app.models.enums import ActorType
from app.models.outreach import ReplyClassification
from app.models.system import AppSettings, AuditLog
from app.repositories.ai_calls import AiCallRepository
from app.repositories.applications import ApplicationRepository
from app.repositories.outreach import EmailRepository
from app.repositories.profiles import UserSettingsRepository
from app.schemas.outreach import (
    AutomationRun,
    AutomationRunRequest,
    AutomationStatus,
    PlatformSettings,
    PlatformUpdate,
    QuotaRead,
    ReplyClassificationRead,
    ReplyConfirm,
    ReplyRead,
    UsageRead,
)
from app.schemas.tasks import TaskCreated
from app.services.ai import month_start
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
from app.services.usage import Quota, user_usage

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


QUOTA_FIELDS = (
    "jsearch_requests_per_month",
    "apify_posts_per_month",
    "apify_runs_per_day",
    "apify_max_posts_per_fetch",
    "jsearch_max_pages",
    "jsearch_allow_load_more",
)


def _platform(row: AppSettings) -> PlatformSettings:
    return PlatformSettings(
        automation_fetch_enabled=row.automation_fetch_enabled,
        **{name: getattr(row, name) for name in QUOTA_FIELDS},
    )


@router.get("/admin/platform", response_model=PlatformSettings, summary="Platform switches (admin)")
async def get_platform(admin: AdminUser, db: DbSession) -> PlatformSettings:
    row = await app_settings(db)
    await db.commit()
    return _platform(row)


@router.patch(
    "/admin/platform", response_model=PlatformSettings, summary="Change platform switches (admin)"
)
async def update_platform(
    body: PlatformUpdate, admin: AdminUser, db: DbSession
) -> PlatformSettings:
    row = await app_settings(db)

    def audit(action: str, data: dict[str, object]) -> None:
        db.add(
            AuditLog(
                user_id=admin.id,
                actor_type=ActorType.ADMIN,
                action=action,
                entity_type="app_settings",
                data=data,
            )
        )

    enabled = body.automation_fetch_enabled
    if enabled is not None and row.automation_fetch_enabled != enabled:
        row.automation_fetch_enabled = enabled
        audit("platform.automation_fetch", {"enabled": enabled})
    quotas = {
        name: value
        for name in QUOTA_FIELDS
        if (value := getattr(body, name)) is not None and value != getattr(row, name)
    }
    if quotas:
        for name, value in quotas.items():
            setattr(row, name, value)
        audit("platform.quotas", quotas)
    if enabled is not None or quotas:
        row.updated_by_id = admin.id
    await db.commit()
    return _platform(row)


@router.get("/usage", response_model=UsageRead, summary="Your paid-API and AI usage this month")
async def my_usage(db: DbSession, user: ApprovedUser) -> UsageRead:
    usage = await user_usage(db, user.id)
    platform = await app_settings(db)
    user_settings = await UserSettingsRepository(db, owner_id=user.id).get_or_create()
    spent = await AiCallRepository(db).cost_since(user.id, month_start())
    await db.commit()

    def quota(q: Quota) -> QuotaRead:
        return QuotaRead(used=q.used, limit=q.limit, left=q.left)

    return UsageRead(
        jsearch_month=quota(usage.jsearch_month),
        apify_month=quota(usage.apify_month),
        apify_today=quota(usage.apify_today),
        resets_at=usage.resets_at,
        cached_hits_month=usage.cached_hits_month,
        ai_spent_month_usd=spent,
        ai_budget_usd=user_settings.monthly_ai_budget_usd,
        max_jobs_per_search=platform.jsearch_max_pages * 10,
        load_more_allowed=platform.jsearch_allow_load_more,
        max_posts_per_fetch=platform.apify_max_posts_per_fetch,
    )


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
