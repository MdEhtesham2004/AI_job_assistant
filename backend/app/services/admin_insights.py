"""Admin › Audit log, Analytics and recent errors (Phase 14). Admin-only, read-only."""

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.accounts import User
from app.models.applications import Application
from app.models.enums import EmailDirection, EmailStatus, TaskStatus
from app.models.jobs import Job
from app.models.outreach import Email
from app.models.system import AiCall, AuditLog, Task


@dataclass(frozen=True)
class AuditFilters:
    action: str | None = None  # prefix, e.g. "user." or "platform."
    actor_type: str | None = None
    q: str | None = None  # user email


async def audit_page(
    session: AsyncSession, filters: AuditFilters, *, limit: int, offset: int
) -> tuple[Sequence[tuple[AuditLog, str | None]], int]:
    query = select(AuditLog, User.email).outerjoin(User, User.id == AuditLog.user_id)
    if filters.action:
        query = query.where(AuditLog.action.startswith(filters.action))
    if filters.actor_type:
        query = query.where(AuditLog.actor_type == filters.actor_type)
    if filters.q:
        query = query.where(User.email.ilike(f"%{filters.q.strip()}%"))
    total = await session.scalar(select(func.count()).select_from(query.subquery())) or 0
    rows = await session.execute(
        query.order_by(AuditLog.created_at.desc(), AuditLog.id).limit(limit).offset(offset)
    )
    return [(entry, email) for entry, email in rows.all()], total


@dataclass(frozen=True)
class UserUsage:
    user_id: Any
    email: str
    full_name: str
    applications: int
    emails_sent_30d: int
    ai_cost_month_usd: Decimal
    last_login_at: datetime | None


@dataclass(frozen=True)
class Analytics:
    users_by_status: dict[str, int]
    jobs_in_catalog: int
    applications_total: int
    emails_sent_30d: int
    ai_cost_month_usd: Decimal
    ai_calls_month: int
    ai_cost_by_feature: list[tuple[str, Decimal, int]]
    users: list[UserUsage]
    failed_tasks_7d: int


async def analytics(session: AsyncSession, now: datetime | None = None) -> Analytics:
    now = now or datetime.now(UTC)
    month = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    days30 = now - timedelta(days=30)
    sent = (
        (Email.direction == EmailDirection.OUTBOUND)
        & Email.status.in_((EmailStatus.SENT, EmailStatus.BOUNCED))
        & (Email.sent_at >= days30)
    )

    status_rows = await session.execute(
        select(User.approval_status, func.count()).group_by(User.approval_status)
    )
    users_by_status = {str(getattr(s, "value", s)): c for s, c in status_rows.all()}
    feature_rows = await session.execute(
        select(AiCall.task_type, func.coalesce(func.sum(AiCall.cost_usd), 0), func.count())
        .where(AiCall.created_at >= month)
        .group_by(AiCall.task_type)
        .order_by(func.sum(AiCall.cost_usd).desc().nulls_last())
    )

    apps = (
        select(Application.user_id, func.count().label("n"))
        .group_by(Application.user_id)
        .subquery()
    )
    mails = (
        select(Email.user_id, func.count().label("n"))
        .where(sent)
        .group_by(Email.user_id)
        .subquery()
    )
    costs = (
        select(AiCall.user_id, func.sum(AiCall.cost_usd).label("usd"))
        .where(AiCall.created_at >= month)
        .group_by(AiCall.user_id)
        .subquery()
    )
    user_rows = await session.execute(
        select(
            User,
            func.coalesce(apps.c.n, 0),
            func.coalesce(mails.c.n, 0),
            func.coalesce(costs.c.usd, 0),
        )
        .outerjoin(apps, apps.c.user_id == User.id)
        .outerjoin(mails, mails.c.user_id == User.id)
        .outerjoin(costs, costs.c.user_id == User.id)
        .order_by(func.coalesce(costs.c.usd, 0).desc(), User.created_at)
        .limit(200)
    )

    return Analytics(
        users_by_status=users_by_status,
        jobs_in_catalog=await session.scalar(select(func.count()).select_from(Job)) or 0,
        applications_total=await session.scalar(select(func.count()).select_from(Application)) or 0,
        emails_sent_30d=await session.scalar(select(func.count()).select_from(Email).where(sent))
        or 0,
        ai_cost_month_usd=Decimal(
            await session.scalar(
                select(func.coalesce(func.sum(AiCall.cost_usd), 0)).where(
                    AiCall.created_at >= month
                )
            )
            or 0
        ),
        ai_calls_month=await session.scalar(
            select(func.count()).select_from(AiCall).where(AiCall.created_at >= month)
        )
        or 0,
        ai_cost_by_feature=[(t, Decimal(c), n) for t, c, n in feature_rows.all()],
        users=[
            UserUsage(
                user_id=user.id,
                email=user.email,
                full_name=user.full_name,
                applications=int(n_apps),
                emails_sent_30d=int(n_mails),
                ai_cost_month_usd=Decimal(usd),
                last_login_at=user.last_login_at,
            )
            for user, n_apps, n_mails, usd in user_rows.all()
        ],
        failed_tasks_7d=await session.scalar(
            select(func.count())
            .select_from(Task)
            .where(Task.status == TaskStatus.FAILED, Task.created_at >= now - timedelta(days=7))
        )
        or 0,
    )


async def recent_errors(
    session: AsyncSession, limit: int = 50
) -> Sequence[tuple[Task, str | None]]:
    rows = await session.execute(
        select(Task, User.email)
        .outerjoin(User, User.id == Task.user_id)
        .where(Task.status == TaskStatus.FAILED)
        .order_by(Task.created_at.desc())
        .limit(limit)
    )
    return [(task, email) for task, email in rows.all()]
