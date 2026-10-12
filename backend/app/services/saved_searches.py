"""Saved searches: CRUD for the user, and the scheduler that runs them (Celery Beat)."""

import uuid
from collections.abc import Sequence
from datetime import UTC, datetime, timedelta

import structlog
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings
from app.core.errors import (
    LimitExceededError,
    NotFoundError,
    PermissionDeniedError,
    ValidationAppError,
)
from app.domain.schedule import ScheduleError, is_due, next_run, validate_cron
from app.models.accounts import Profile, User, UserSettings
from app.models.enums import ApprovalStatus
from app.models.jobs import JobSearchRun, SavedSearch
from app.repositories.jobs import SavedSearchRepository
from app.repositories.profiles import ProfileRepository, UserSettingsRepository
from app.schemas.jobs import JobSearchRequest, SavedSearchCreate, SavedSearchUpdate
from app.services.contacts import start_linkedin_discovery
from app.services.jobs import JobService
from app.services.tasks import TaskDispatcher
from app.services.usage import app_settings

logger = structlog.get_logger("app.saved_searches")

# Phase 19 default for recruiter-email searches: daily 09:00 (user's time zone).
LINKEDIN_DEFAULT_CRON = "0 9 * * *"


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

    async def linkedin_allowed(self) -> bool:
        """Phase 19: scheduled recruiter-email searches are for admin-enabled users only."""
        settings = await UserSettingsRepository(self.session, owner_id=self.user_id).get_or_create()
        return settings.linkedin_schedule_allowed

    async def _check_linkedin(self, max_posts: int) -> None:
        if not await self.linkedin_allowed():
            raise PermissionDeniedError(
                "Scheduled recruiter-email searches are not enabled for your account.",
                code="LINKEDIN_SCHEDULE_NOT_ALLOWED",
            )
        cap = (await app_settings(self.session)).apify_max_posts_per_fetch
        if max_posts > cap:
            raise ValidationAppError(
                f"A LinkedIn fetch can read at most {cap} posts.",
                code="TOO_MANY_POSTS",
                details={"max_posts": cap},
            )

    async def create(self, data: SavedSearchCreate) -> SavedSearch:
        values = data.model_dump()
        if data.kind == "linkedin":
            await self._check_linkedin(data.max_posts)
            if "schedule_cron" not in data.model_fields_set:
                values["schedule_cron"] = LINKEDIN_DEFAULT_CRON
        values["schedule_cron"] = self._cron(values["schedule_cron"])
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
        if saved.kind == "linkedin" and (
            changes.get("is_active") or changes.get("max_posts") is not None
        ):
            await self._check_linkedin(changes.get("max_posts") or saved.max_posts)
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

    async def run_now(self, search_id: uuid.UUID) -> tuple[JobSearchRun | None, uuid.UUID]:
        saved = await self.get(search_id)
        if saved.kind == "linkedin":
            await self._check_linkedin(saved.max_posts)
            saved.last_run_at = datetime.now(UTC)
            task = await start_linkedin_discovery(
                self.session,
                self.user_id,
                self.dispatcher,
                keyword=saved.keywords,
                max_posts=saved.max_posts,
                posted_limit=saved.posted_limit,  # type: ignore[arg-type]
            )
            return None, task.id
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
            SavedSearch.kind,
            UserSettings.linkedin_schedule_allowed,
        )
        .join(User, User.id == SavedSearch.user_id)
        .outerjoin(Profile, Profile.user_id == SavedSearch.user_id)
        .outerjoin(UserSettings, UserSettings.user_id == SavedSearch.user_id)
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
        for search_id, cron, last_run_at, created_at, timezone, kind, allowed in rows.all()
        # Phase 19: recruiter-email searches only while the admin allows it for the user.
        if (kind != "linkedin" or allowed)
        and is_due(cron, last_run_at or created_at, now, timezone)
    ]
    started = 0
    for search_id in due:
        saved = await session.get(SavedSearch, search_id)
        if saved is None:
            continue
        saved.last_run_at = now  # set first: a failing run is not retried every 5 minutes
        try:
            if saved.kind == "linkedin":
                await start_linkedin_discovery(
                    session,
                    saved.user_id,
                    dispatcher,
                    keyword=saved.keywords,
                    max_posts=saved.max_posts,
                    posted_limit=saved.posted_limit,  # type: ignore[arg-type]
                )
            else:
                jobs = JobService(session, saved.user_id, settings=settings, dispatcher=dispatcher)
                await jobs.start_search(
                    search_request(saved, settings.jsearch_date_posted, settings.jsearch_num_pages),
                    saved_search_id=saved.id,
                )
            started += 1
        except Exception:
            logger.exception("saved_search.dispatch_failed", saved_search_id=str(search_id))
            await session.rollback()
    return started
