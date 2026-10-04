"""Dashboard (Phase 14): the user's numbers in a few aggregate queries.

Stage counts use the same grouping as the Applications board, so both pages agree.
"Responded" = an application that got past "applied" (responded, interview, offer, rejected).
"""

import uuid
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from typing import Any

from sqlalchemy import case, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.applications import Application, ApplicationStatusHistory
from app.models.enums import (
    ApplicationStatus,
    EmailDirection,
    EmailStatus,
    TaskStatus,
    UserJobState,
)
from app.models.jobs import Job, UserJob
from app.models.outreach import Email
from app.models.resumes import ResumeVersion
from app.models.system import AiCall, Task

S = ApplicationStatus
# Same columns as the Applications board (frontend BOARD_COLUMNS).
STAGES: dict[str, tuple[ApplicationStatus, ...]] = {
    "to_do": (S.READY_TO_APPLY, S.REJECTED_BY_USER),
    "outbox": (S.WAITING_FOR_APPROVAL, S.APPROVED, S.SENDING, S.FAILED),
    "applied": (S.APPLIED, S.NO_RESPONSE),
    "in_process": (S.RESPONDED, S.INTERVIEW),
    "offer": (S.OFFER,),
    "closed": (S.REJECTED, S.WITHDRAWN),
}
RESPONDED = (S.RESPONDED, S.INTERVIEW, S.OFFER, S.REJECTED)


@dataclass(frozen=True)
class RateRow:
    key: str
    applied: int
    responded: int

    @property
    def rate(self) -> float | None:
        return round(self.responded / self.applied, 3) if self.applied else None


@dataclass(frozen=True)
class Activity:
    application_id: uuid.UUID
    job_title: str
    company: str
    to_status: ApplicationStatus
    source: str
    note: str | None
    at: datetime


@dataclass(frozen=True)
class Dashboard:
    jobs_found: int
    jobs_new_this_week: int
    statuses: dict[str, int]
    stages: dict[str, int]
    waiting_for_approval: int
    applied_total: int
    responses: int
    interviews: int
    offers: int
    rejected: int
    emails_sent: int
    emails_sent_today: int
    tasks_running: int
    ai_cost_month_usd: Decimal
    by_source: list[RateRow]
    by_resume: list[RateRow]
    activity: list[Activity]

    @property
    def response_rate(self) -> float | None:
        return round(self.responses / self.applied_total, 3) if self.applied_total else None


def _rates(rows: Any) -> list[RateRow]:
    return [RateRow(str(key), int(applied), int(responded)) for key, applied, responded in rows]


async def build(
    session: AsyncSession, user_id: uuid.UUID, now: datetime | None = None
) -> Dashboard:
    now = now or datetime.now(UTC)
    week = now - timedelta(days=7)
    day = now.replace(hour=0, minute=0, second=0, microsecond=0)
    month = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)

    visible = UserJob.state != UserJobState.ARCHIVED
    jobs_found = await session.scalar(
        select(func.count()).select_from(UserJob).where(UserJob.user_id == user_id, visible)
    )
    jobs_week = await session.scalar(
        select(func.count())
        .select_from(UserJob)
        .where(UserJob.user_id == user_id, visible, UserJob.created_at >= week)
    )

    status_rows = await session.execute(
        select(Application.status, func.count())
        .where(Application.user_id == user_id)
        .group_by(Application.status)
    )
    statuses = {s.value: 0 for s in ApplicationStatus}
    for status, count in status_rows.all():
        statuses[ApplicationStatus(status).value] = count
    stages = {key: sum(statuses[s.value] for s in members) for key, members in STAGES.items()}

    applied_total = await session.scalar(
        select(func.count())
        .select_from(Application)
        .where(Application.user_id == user_id, Application.applied_at.is_not(None))
    )
    responses = sum(statuses[s.value] for s in RESPONDED)

    # "Ever reached" from the timeline (an interview that ended in an offer still counts).
    reached_rows = await session.execute(
        select(
            ApplicationStatusHistory.to_status,
            func.count(ApplicationStatusHistory.application_id.distinct()),
        )
        .where(
            ApplicationStatusHistory.user_id == user_id,
            ApplicationStatusHistory.to_status.in_((S.INTERVIEW, S.OFFER, S.REJECTED)),
        )
        .group_by(ApplicationStatusHistory.to_status)
    )
    reached = {ApplicationStatus(s).value: c for s, c in reached_rows.all()}

    sent = Email.status.in_((EmailStatus.SENT, EmailStatus.BOUNCED))
    outbound = (Email.user_id == user_id) & (Email.direction == EmailDirection.OUTBOUND) & sent
    emails_sent = await session.scalar(select(func.count()).select_from(Email).where(outbound))
    emails_today = await session.scalar(
        select(func.count()).select_from(Email).where(outbound, Email.sent_at >= day)
    )
    tasks_running = await session.scalar(
        select(func.count())
        .select_from(Task)
        .where(Task.user_id == user_id, Task.status.in_((TaskStatus.QUEUED, TaskStatus.RUNNING)))
    )
    ai_cost = await session.scalar(
        select(func.coalesce(func.sum(AiCall.cost_usd), 0)).where(
            AiCall.user_id == user_id, AiCall.created_at >= month
        )
    )

    responded_case = func.sum(case((Application.status.in_(RESPONDED), 1), else_=0))
    applied_filter = (Application.user_id == user_id) & Application.applied_at.is_not(None)
    by_source = await session.execute(
        select(Job.source, func.count(), responded_case)
        .join(Job, Job.id == Application.job_id)
        .where(applied_filter)
        .group_by(Job.source)
        .order_by(func.count().desc())
    )
    by_resume = await session.execute(
        select(func.coalesce(ResumeVersion.kind, "none"), func.count(), responded_case)
        .outerjoin(ResumeVersion, ResumeVersion.id == Application.resume_version_id)
        .where(applied_filter)
        .group_by(ResumeVersion.kind)
        .order_by(func.count().desc())
    )

    activity_rows = await session.execute(
        select(ApplicationStatusHistory, Job.title, Job.company)
        .join(Application, Application.id == ApplicationStatusHistory.application_id)
        .join(Job, Job.id == Application.job_id)
        .where(ApplicationStatusHistory.user_id == user_id)
        .order_by(ApplicationStatusHistory.created_at.desc())
        .limit(10)
    )
    activity = [
        Activity(
            application_id=entry.application_id,
            job_title=title,
            company=company,
            to_status=entry.to_status,
            source=entry.source.value,
            note=entry.note,
            at=entry.created_at,
        )
        for entry, title, company in activity_rows.all()
    ]

    return Dashboard(
        jobs_found=jobs_found or 0,
        jobs_new_this_week=jobs_week or 0,
        statuses=statuses,
        stages=stages,
        waiting_for_approval=stages["outbox"],
        applied_total=applied_total or 0,
        responses=responses,
        interviews=reached.get(S.INTERVIEW.value, 0),
        offers=reached.get(S.OFFER.value, 0),
        rejected=reached.get(S.REJECTED.value, 0),
        emails_sent=emails_sent or 0,
        emails_sent_today=emails_today or 0,
        tasks_running=tasks_running or 0,
        ai_cost_month_usd=Decimal(ai_cost or 0),
        by_source=_rates(by_source.all()),
        by_resume=_rates(by_resume.all()),
        activity=activity,
    )
