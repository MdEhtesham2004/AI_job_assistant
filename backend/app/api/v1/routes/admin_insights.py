from typing import Annotated

from fastapi import APIRouter, Query

from app.api.deps import AdminUser, DbSession
from app.schemas.admin_insights import (
    AnalyticsRead,
    AuditEntryRead,
    ErrorRead,
    FeatureCost,
    ProviderUsageRead,
    UserUsageRead,
)
from app.schemas.common import Page
from app.services.admin_insights import AuditFilters, analytics, audit_page, recent_errors
from app.services.usage import APIFY, JSEARCH, provider_stats, provider_units_by_user

router = APIRouter(prefix="/admin", tags=["admin"])


@router.get("/audit", response_model=Page[AuditEntryRead], summary="Audit log (admin)")
async def audit_log(
    admin: AdminUser,
    db: DbSession,
    action: Annotated[str | None, Query(max_length=60)] = None,
    actor_type: Annotated[str | None, Query(pattern="^(user|admin|system)$")] = None,
    q: Annotated[str | None, Query(max_length=100)] = None,
    page: Annotated[int, Query(ge=1)] = 1,
    page_size: Annotated[int, Query(ge=1, le=200)] = 50,
) -> Page[AuditEntryRead]:
    rows, total = await audit_page(
        db,
        AuditFilters(action=action, actor_type=actor_type, q=q),
        limit=page_size,
        offset=(page - 1) * page_size,
    )
    return Page(
        items=[
            AuditEntryRead(
                id=entry.id,
                created_at=entry.created_at,
                actor_type=entry.actor_type.value,
                user_email=email,
                action=entry.action,
                entity_type=entry.entity_type,
                entity_id=entry.entity_id,
                data=entry.data,
                ip_address=str(entry.ip_address) if entry.ip_address else None,
            )
            for entry, email in rows
        ],
        total=total,
        page=page,
        page_size=page_size,
    )


@router.get("/analytics", response_model=AnalyticsRead, summary="Platform usage (admin)")
async def platform_analytics(admin: AdminUser, db: DbSession) -> AnalyticsRead:
    data = await analytics(db)
    providers, jsearch_left = await provider_stats(db)
    by_user = await provider_units_by_user(db)
    return AnalyticsRead(
        users_by_status=data.users_by_status,
        jobs_in_catalog=data.jobs_in_catalog,
        applications_total=data.applications_total,
        emails_sent_30d=data.emails_sent_30d,
        ai_cost_month_usd=data.ai_cost_month_usd,
        ai_calls_month=data.ai_calls_month,
        ai_cost_by_feature=[
            FeatureCost(feature=f, cost_usd=c, calls=n) for f, c, n in data.ai_cost_by_feature
        ],
        users=[
            UserUsageRead(
                **u.__dict__,
                jsearch_requests_month=by_user.get(u.user_id, {}).get(JSEARCH, 0),
                apify_posts_month=by_user.get(u.user_id, {}).get(APIFY, 0),
            )
            for u in data.users
        ],
        failed_tasks_7d=data.failed_tasks_7d,
        providers=[
            ProviderUsageRead(
                provider=p.provider,
                calls=p.calls,
                cache_hits=p.cache_hits,
                cache_rate=p.cache_rate,
                units=p.units,
                cost_usd=p.cost_usd,
                failed=p.failed,
            )
            for p in providers
        ],
        jsearch_quota_remaining=jsearch_left,
    )


@router.get("/errors", response_model=list[ErrorRead], summary="Recent failed tasks (admin)")
async def errors(admin: AdminUser, db: DbSession) -> list[ErrorRead]:
    return [
        ErrorRead(
            task_id=task.id,
            type=task.type,
            user_email=email,
            error=task.error,
            attempts=task.attempts,
            created_at=task.created_at,
            finished_at=task.finished_at,
        )
        for task, email in await recent_errors(db)
    ]
