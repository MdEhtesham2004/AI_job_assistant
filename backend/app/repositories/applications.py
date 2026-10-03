import uuid
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Any

from sqlalchemy import ColumnElement, func, or_, select

from app.models.applications import Application, ApplicationStatusHistory
from app.models.enums import ApplicationChannel, ApplicationStatus
from app.models.jobs import Job
from app.repositories.base import OwnedRepository
from app.repositories.jobs import _escape_like


@dataclass(frozen=True)
class ApplicationFilters:
    statuses: tuple[ApplicationStatus, ...] = ()
    channel: ApplicationChannel | None = None
    q: str | None = None
    sort: str = "updated"  # updated | applied | company


class ApplicationRepository(OwnedRepository[Application]):
    model = Application

    async def for_job(self, job_id: uuid.UUID) -> Application | None:
        result: Application | None = await self.session.scalar(
            self.scoped().where(Application.job_id == job_id)
        )
        return result

    async def page(
        self, filters: ApplicationFilters, *, limit: int, offset: int
    ) -> tuple[Sequence[tuple[Application, Job]], int]:
        query = (
            select(Application, Job).join(Job, Job.id == Application.job_id).where(self._owned())
        )
        if filters.statuses:
            query = query.where(Application.status.in_(filters.statuses))
        if filters.channel:
            query = query.where(Application.channel == filters.channel)
        if filters.q:
            pattern = f"%{_escape_like(filters.q.strip())}%"
            query = query.where(
                or_(Job.title.ilike(pattern, escape="\\"), Job.company.ilike(pattern, escape="\\"))
            )
        total = await self.session.scalar(select(func.count()).select_from(query.subquery())) or 0
        order: list[ColumnElement[Any]]
        if filters.sort == "applied":
            order = [Application.applied_at.desc().nulls_last()]
        elif filters.sort == "company":
            order = [Job.company.asc(), Job.title.asc()]
        else:
            order = [Application.last_status_at.desc()]
        rows = await self.session.execute(
            query.order_by(*order, Application.id).limit(limit).offset(offset)
        )
        return [(application, job) for application, job in rows.all()], total

    async def status_counts(self) -> dict[str, int]:
        rows = await self.session.execute(
            select(Application.status, func.count())
            .where(self._owned())
            .group_by(Application.status)
        )
        counts = {status.value: 0 for status in ApplicationStatus}
        for status, count in rows.all():
            counts[ApplicationStatus(status).value] = count
        return counts

    async def by_job_ids(self, job_ids: Sequence[uuid.UUID]) -> dict[uuid.UUID, Application]:
        if not job_ids:
            return {}
        rows = await self.session.scalars(self.scoped().where(Application.job_id.in_(job_ids)))
        return {application.job_id: application for application in rows.all()}


class ApplicationHistoryRepository(OwnedRepository[ApplicationStatusHistory]):
    model = ApplicationStatusHistory

    async def for_application(
        self, application_id: uuid.UUID
    ) -> Sequence[ApplicationStatusHistory]:
        rows = await self.session.scalars(
            self.scoped()
            .where(ApplicationStatusHistory.application_id == application_id)
            .order_by(ApplicationStatusHistory.created_at, ApplicationStatusHistory.id)
        )
        return rows.all()
