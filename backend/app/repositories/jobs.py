import uuid
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any

from sqlalchemy import ColumnElement, Select, func, or_, select
from sqlalchemy.dialects.postgresql import insert

from app.models.enums import JobSource, JobStatus, JobVisibility, UserJobState
from app.models.jobs import Job, JobSearchResult, JobSearchRun, SavedSearch, UserJob
from app.repositories.base import BaseRepository, OwnedRepository

# "Inbox" view: everything the user has not put away.
OPEN_STATES = (UserJobState.NEW, UserJobState.SAVED, UserJobState.ANALYZED)


class JobRepository(BaseRepository[Job]):
    """The shared job catalog (not user-owned). Users reach jobs through `user_jobs`."""

    model = Job

    async def by_external_id(self, source: JobSource, external_id: str) -> Job | None:
        result: Job | None = await self.session.scalar(
            select(Job).where(Job.source == source, Job.external_id == external_id)
        )
        return result

    async def canonical_for(self, dedupe_hash: str, since: datetime) -> Job | None:
        """An active public job with the same company/title/city seen recently."""
        result: Job | None = await self.session.scalar(
            select(Job)
            .where(
                Job.dedupe_hash == dedupe_hash,
                Job.status == JobStatus.ACTIVE,
                Job.visibility == JobVisibility.PUBLIC,
                Job.last_seen_at >= since,
            )
            .order_by(Job.first_seen_at)
            .limit(1)
        )
        return result

    async def insert_new(self, values: dict[str, Any]) -> Job | None:
        """Insert unless (source, external_id) exists (a parallel worker won the race)."""
        job_id = await self.session.scalar(
            insert(Job)
            .values(**values)
            .on_conflict_do_nothing(index_elements=["source", "external_id"])
            .returning(Job.id)
        )
        return await self.session.get(Job, job_id) if job_id else None

    async def visible(self, job_id: uuid.UUID, user_id: uuid.UUID) -> Job | None:
        """Read rule (Phase 0 §5.3): public jobs, or private jobs the user created."""
        result: Job | None = await self.session.scalar(
            select(Job).where(
                Job.id == job_id,
                or_(Job.visibility == JobVisibility.PUBLIC, Job.created_by_user_id == user_id),
            )
        )
        return result


@dataclass(frozen=True)
class JobFilters:
    state: UserJobState | None = None  # None → open states (new, saved, analyzed)
    source: JobSource | None = None
    posted_within_days: int | None = None
    q: str | None = None
    location: str | None = None
    remote_only: bool = False
    sort: str = "posted"  # posted | found | company


class UserJobRepository(OwnedRepository[UserJob]):
    model = UserJob

    async def for_job(self, job_id: uuid.UUID) -> UserJob | None:
        result: UserJob | None = await self.session.scalar(
            self.scoped().where(UserJob.job_id == job_id)
        )
        return result

    async def link(self, job_id: uuid.UUID) -> bool:
        """Add the job to the user's list. True if it is new for this user."""
        created = await self.session.scalar(
            insert(UserJob)
            .values(user_id=self.owner_id, job_id=job_id)
            .on_conflict_do_nothing(index_elements=["user_id", "job_id"])
            .returning(UserJob.id)
        )
        return created is not None

    def _filtered(self, filters: JobFilters) -> Select[UserJob, Job]:
        query = select(UserJob, Job).join(Job, Job.id == UserJob.job_id).where(self._owned())
        if filters.state is None:
            query = query.where(UserJob.state.in_(OPEN_STATES))
        else:
            query = query.where(UserJob.state == filters.state)
        if filters.source:
            query = query.where(Job.source == filters.source)
        if filters.posted_within_days:
            since = func.now() - timedelta(days=filters.posted_within_days)
            query = query.where(func.coalesce(Job.posted_at, Job.first_seen_at) >= since)
        if filters.q:
            pattern = f"%{_escape_like(filters.q.strip())}%"
            query = query.where(
                or_(Job.title.ilike(pattern, escape="\\"), Job.company.ilike(pattern, escape="\\"))
            )
        if filters.location:
            query = query.where(
                Job.location.ilike(f"%{_escape_like(filters.location.strip())}%", escape="\\")
            )
        if filters.remote_only:
            query = query.where(Job.is_remote.is_(True))
        return query

    async def page(
        self, filters: JobFilters, *, limit: int, offset: int
    ) -> tuple[Sequence[tuple[UserJob, Job]], int]:
        query = self._filtered(filters)
        total = await self.session.scalar(select(func.count()).select_from(query.subquery())) or 0
        order: list[ColumnElement[Any]]
        if filters.sort == "found":
            order = [UserJob.first_found_at.desc()]
        elif filters.sort == "company":
            order = [Job.company.asc(), Job.title.asc()]
        else:
            order = [Job.posted_at.desc().nulls_last(), UserJob.first_found_at.desc()]
        rows = await self.session.execute(
            query.order_by(*order, Job.id).limit(limit).offset(offset)
        )
        return [(user_job, job) for user_job, job in rows.all()], total

    async def state_counts(self) -> dict[str, int]:
        rows = await self.session.execute(
            select(UserJob.state, func.count()).where(self._owned()).group_by(UserJob.state)
        )
        counts = {state.value: 0 for state in UserJobState}
        for state, count in rows.all():
            counts[UserJobState(state).value] = count
        return counts


def _escape_like(value: str) -> str:
    return value.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")


class SavedSearchRepository(OwnedRepository[SavedSearch]):
    model = SavedSearch

    async def all(self) -> Sequence[SavedSearch]:
        rows = await self.session.scalars(self.scoped().order_by(SavedSearch.created_at))
        return rows.all()

    async def active_count(self) -> int:
        query = (
            select(func.count())
            .select_from(SavedSearch)
            .where(self._owned(), SavedSearch.is_active.is_(True))
        )
        return await self.session.scalar(query) or 0


class JobSearchRunRepository(OwnedRepository[JobSearchRun]):
    model = JobSearchRun

    async def recent(self, limit: int) -> Sequence[JobSearchRun]:
        rows = await self.session.scalars(
            self.scoped().order_by(JobSearchRun.created_at.desc()).limit(limit)
        )
        return rows.all()

    async def results(self, run_id: uuid.UUID) -> Sequence[tuple[Job, UserJob | None, bool]]:
        """Jobs of one run (owner-checked by the caller): job, this user's state, is_new."""
        rows = await self.session.execute(
            select(Job, UserJob, JobSearchResult.is_new)
            .join(JobSearchResult, JobSearchResult.job_id == Job.id)
            .outerjoin(UserJob, (UserJob.job_id == Job.id) & (UserJob.user_id == self.owner_id))
            .where(JobSearchResult.search_run_id == run_id)
            .order_by(JobSearchResult.rank)
        )
        return [(job, user_job, is_new) for job, user_job, is_new in rows.all()]

    async def add_result(
        self, run_id: uuid.UUID, job_id: uuid.UUID, rank: int, *, is_new: bool
    ) -> bool:
        """False when the job is already in this run (e.g. repeated on a later page)."""
        added = await self.session.scalar(
            insert(JobSearchResult)
            .values(search_run_id=run_id, job_id=job_id, rank=rank, is_new=is_new)
            .on_conflict_do_nothing()
            .returning(JobSearchResult.job_id)
        )
        return added is not None

    async def result_count(self, run_id: uuid.UUID) -> int:
        query = select(func.count()).where(JobSearchResult.search_run_id == run_id)
        return await self.session.scalar(query) or 0


async def active_saved_searches(session: Any) -> Sequence[SavedSearch]:
    """All active saved searches of all users (for the scheduler; not owner-scoped)."""
    rows = await session.scalars(select(SavedSearch).where(SavedSearch.is_active.is_(True)))
    result: Sequence[SavedSearch] = rows.all()
    return result
