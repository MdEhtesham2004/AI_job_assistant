"""Saved searches: CRUD for the user, and the scheduler that runs them (Celery Beat)."""

import uuid
from collections.abc import Sequence
from datetime import UTC, datetime, timedelta

import structlog
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings
from app.core.errors import LimitExceededError, NotFoundError, ValidationAppError
from app.domain.schedule import ScheduleError, is_due, next_run, validate_cron
from app.models.accounts import Profile, User
from app.models.enums import ApprovalStatus
from app.models.jobs import JobSearchRun, SavedSearch
from app.repositories.jobs import SavedSearchRepository
from app.repositories.profiles import ProfileRepository
from app.schemas.jobs import JobSearchRequest, SavedSearchCreate, SavedSearchUpdate
from app.services.jobs import JobService
from app.services.tasks import TaskDispatcher

logger = structlog.get_logger("app.saved_searches")


def search_request(saved: SavedSearch, date_posted: str, num_pages: int = 1) -> JobSearchRequest:
    return JobSearchRequest(
        num_pages=num_pages,
        keywords=saved.keywords,
        location=saved.location,
        experience=saved.experience,  # type: ignore[arg-type]
        remote_only=saved.remote_only,
        country=saved.country,
        date_posted=date_posted,  # type: ignore[arg-type]
    )


class SavedSearchService:
    def __init__(
        self,
        session: AsyncSession,
        user_id: uuid.UUID,
        *,
        settings: Settings,
        dispatcher: TaskDispatcher,
    ) -> None:
        self.session = session
        self.user_id = user_id
        self.settings = settings
        self.dispatcher = dispatcher
        self.searches = SavedSearchRepository(session, owner_id=user_id)

    async def timezone(self) -> str:
        profile = await ProfileRepository(self.session, owner_id=self.user_id).get(self.user_id)
        return profile.timezone if profile else "UTC"

    def next_run_at(self, saved: SavedSearch, timezone: str) -> datetime | None:
        if not saved.is_active:
            return None
        return next_run(saved.schedule_cron, saved.last_run_at or saved.created_at, timezone)

    def _cron(self, expression: str) -> str:
        try:
            return validate_cron(expression, self.settings.saved_search_min_interval_minutes)
        except ScheduleError as exc:
            raise ValidationAppError(str(exc), code="INVALID_SCHEDULE") from exc

    async def _check_active_limit(self) -> None:
        if await self.searches.active_count() >= self.settings.max_active_saved_searches:
            raise LimitExceededError(
                f"You can have at most {self.settings.max_active_saved_searches} active saved "
                "searches (each run uses the job-search quota). Pause one first.",
                code="SAVED_SEARCH_LIMIT",
            )

    async def list(self) -> Sequence[SavedSearch]:
        return await self.searches.all()

    async def get(self, search_id: uuid.UUID) -> SavedSearch:
        saved = await self.searches.get(search_id)
        if saved is None:
            raise NotFoundError("Saved search not found.")
        return saved

    async def create(self, data: SavedSearchCreate) -> SavedSearch:
        values = data.model_dump()
        values["schedule_cron"] = self._cron(data.schedule_cron)
        values["country"] = data.country.lower()
        if data.is_active:
            await self._check_active_limit()
        saved = await self.searches.add(SavedSearch(**values))
        await self.session.commit()
        await self.session.refresh(saved)
        return saved

    async def update(self, search_id: uuid.UUID, data: SavedSearchUpdate) -> SavedSearch:
        saved = await self.get(search_id)
        changes = data.model_dump(exclude_unset=True)
        if changes.get("schedule_cron") is not None:
            changes["schedule_cron"] = self._cron(changes["schedule_cron"])
        if changes.get("is_active") and not saved.is_active:
            await self._check_active_limit()
            saved.last_run_at = datetime.now(UTC)  # resuming does not trigger a missed run
        for key, value in changes.items():
            if value is None and key in ("name", "keywords", "remote_only", "country", "is_active"):
                continue  # required fields cannot be cleared
            setattr(saved, key, value.lower() if key == "country" else value)
        await self.session.commit()
        await self.session.refresh(saved)
        return saved

    async def delete(self, search_id: uuid.UUID) -> None:
        saved = await self.get(search_id)
        await self.session.delete(saved)  # past runs keep their results (saved_search_id → NULL)
        await self.session.commit()

    async def run_now(self, search_id: uuid.UUID) -> tuple[JobSearchRun, uuid.UUID]:
        saved = await self.get(search_id)
        saved.last_run_at = datetime.now(UTC)
        jobs = JobService(
            self.session, self.user_id, settings=self.settings, dispatcher=self.dispatcher
        )
        run, task = await jobs.start_search(
            search_request(
                saved, self.settings.jsearch_date_posted, self.settings.jsearch_num_pages
            ),
            saved_search_id=saved.id,
        )
        return run, task.id


async def dispatch_due_searches(
    session: AsyncSession, settings: Settings, dispatcher: TaskDispatcher, now: datetime
) -> int:
    """Start every saved search whose next scheduled time has passed. Returns how many."""
    rows = await session.execute(
        select(
            SavedSearch.id,
            SavedSearch.schedule_cron,
            SavedSearch.last_run_at,
            SavedSearch.created_at,
            Profile.timezone,
        )
        .join(User, User.id == SavedSearch.user_id)
        .outerjoin(Profile, Profile.user_id == SavedSearch.user_id)
        .where(
            SavedSearch.is_active.is_(True),
            User.is_active.is_(True),
            User.approval_status == ApprovalStatus.APPROVED,
            # Cost control (Phase 14): pause saved searches of users who stopped visiting.
            *(
                [
                    func.coalesce(User.last_login_at, User.created_at)
                    >= now - timedelta(days=settings.saved_search_active_days)
                ]
                if settings.saved_search_active_days
                else []
            ),
        )
    )
    due = [
        search_id
        for search_id, cron, last_run_at, created_at, timezone in rows.all()
        if is_due(cron, last_run_at or created_at, now, timezone)
    ]
    started = 0
    for search_id in due:
        saved = await session.get(SavedSearch, search_id)
        if saved is None:
            continue
        saved.last_run_at = now  # set first: a failing run is not retried every 5 minutes
        jobs = JobService(session, saved.user_id, settings=settings, dispatcher=dispatcher)
        try:
            await jobs.start_search(
                search_request(saved, settings.jsearch_date_posted, settings.jsearch_num_pages),
                saved_search_id=saved.id,
            )
            started += 1
        except Exception:
            logger.exception("saved_search.dispatch_failed", saved_search_id=str(search_id))
            await session.rollback()
    return started
