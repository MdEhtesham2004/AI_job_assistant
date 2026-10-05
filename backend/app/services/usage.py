"""Cost control for the paid data APIs (Phase 14): shared cache, per-user quotas, metering.

Every JSearch search and Apify LinkedIn search goes through a *metered* source:
1. **Shared cache** — an identical query (any user) inside the cache window reuses the
   stored results: no API call, no quota used. A short lock makes simultaneous identical
   searches (e.g. two saved searches) share one call.
2. **Quota** — a real call is refused once the user's monthly (and, for Apify, daily)
   allowance from Settings › Platform is used up. Cache hits are always allowed.
3. **Log** — each call, cached or not, is a `provider_calls` row (units, results, latency,
   estimated cost, JSearch plan quota left) for the quotas and Admin › Analytics.
4. Apify: a keyword fetched for real in the last `apify_recent_hours` is searched for the
   last 24 h only (older posts were already read).
"""

import asyncio
import dataclasses
import hashlib
import json
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from time import perf_counter
from typing import Any

import structlog
from redis.asyncio import Redis
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings
from app.core.errors import AppError, LimitExceededError
from app.domain.jobs import JobQuery, JobSource, NormalizedJob
from app.integrations.apify import LinkedInPost, PostedLimit, PostSource
from app.models.accounts import User
from app.models.enums import UserRole
from app.models.system import AppSettings, ProviderCall
from app.repositories.interviews import InterviewRepository
from app.services.notifications import notify

logger = structlog.get_logger("app.usage")

JSEARCH = "jsearch"
APIFY = "apify"
LOCK_SECONDS = 90
ALERT_KEY = "usage:alert:jsearch-quota"


# ---------- (de)serialisation for the cache ----------


def _encode(value: Any) -> Any:
    if isinstance(value, datetime):
        return {"__dt": value.isoformat()}
    if isinstance(value, Decimal):
        return {"__dec": str(value)}
    return value


def _decode(value: Any) -> Any:
    if isinstance(value, dict) and "__dt" in value:
        return datetime.fromisoformat(value["__dt"])
    if isinstance(value, dict) and "__dec" in value:
        return Decimal(value["__dec"])
    return value


def _dump(items: list[Any]) -> str:
    return json.dumps(
        [{k: _encode(v) for k, v in dataclasses.asdict(item).items()} for item in items]
    )


def _load[T](raw: str, cls: type[T]) -> list[T]:
    return [cls(**{k: _decode(v) for k, v in row.items()}) for row in json.loads(raw)]


def _key(provider: str, query: dict[str, Any]) -> str:
    raw = json.dumps(query, sort_keys=True, default=str)
    return f"{provider}:{hashlib.sha256(raw.encode()).hexdigest()[:32]}"


def _norm(text: str | None) -> str:
    return " ".join((text or "").lower().split())


# ---------- quotas ----------


async def app_settings(session: AsyncSession) -> AppSettings:
    row = await session.get(AppSettings, 1)
    if row is None:
        row = AppSettings(id=1)
        session.add(row)
        await session.flush()
    return row


def _month_start(now: datetime) -> datetime:
    return now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)


def _next_month(now: datetime) -> datetime:
    start = _month_start(now)
    return (start + timedelta(days=32)).replace(day=1)


async def _used(
    session: AsyncSession, user_id: uuid.UUID, provider: str, since: datetime, *, units: bool
) -> int:
    measure = func.coalesce(func.sum(ProviderCall.units), 0) if units else func.count()
    value = await session.scalar(
        select(measure).where(
            ProviderCall.user_id == user_id,
            ProviderCall.provider == provider,
            ProviderCall.cached.is_(False),
            ProviderCall.success.is_(True),
            ProviderCall.created_at >= since,
        )
    )
    return int(value or 0)


@dataclass(frozen=True)
class Quota:
    used: int
    limit: int  # 0 = unlimited

    @property
    def left(self) -> int | None:
        return None if self.limit == 0 else max(0, self.limit - self.used)


@dataclass(frozen=True)
class Usage:
    jsearch_month: Quota  # requests (one per page)
    apify_month: Quota  # LinkedIn posts returned (what Apify bills)
    apify_today: Quota  # LinkedIn fetches (runs)
    interviews_month: Quota  # mock interviews (Phase 15)
    resets_at: datetime
    cached_hits_month: int


async def user_usage(
    session: AsyncSession, user_id: uuid.UUID, now: datetime | None = None
) -> Usage:
    now = now or datetime.now(UTC)
    limits = await app_settings(session)
    month = _month_start(now)
    day = now.replace(hour=0, minute=0, second=0, microsecond=0)
    cached_hits = await session.scalar(
        select(func.count()).where(
            ProviderCall.user_id == user_id,
            ProviderCall.cached.is_(True),
            ProviderCall.created_at >= month,
        )
    )
    return Usage(
        jsearch_month=Quota(
            await _used(session, user_id, JSEARCH, month, units=True),
            limits.jsearch_requests_per_month,
        ),
        apify_month=Quota(
            await _used(session, user_id, APIFY, month, units=True), limits.apify_posts_per_month
        ),
        apify_today=Quota(
            await _used(session, user_id, APIFY, day, units=False), limits.apify_runs_per_day
        ),
        interviews_month=Quota(
            await InterviewRepository(session, owner_id=user_id).counted_since(month),
            limits.interviews_per_month,
        ),
        resets_at=_next_month(now),
        cached_hits_month=int(cached_hits or 0),
    )


async def check_quota(
    session: AsyncSession, user_id: uuid.UUID, provider: str, *, units: int = 1
) -> None:
    usage = await user_usage(session, user_id)
    resets = f"{usage.resets_at:%d %b}"
    if provider == JSEARCH:
        quota = usage.jsearch_month
        if quota.left is not None and quota.left < units:
            raise LimitExceededError(
                f"You used {quota.used} of your {quota.limit} job-search requests this month "
                f"(resets on {resets}). Searches someone ran recently still work — they are free.",
                code="SEARCH_QUOTA_REACHED",
            )
        return
    for quota, what, when in (
        (usage.apify_today, "LinkedIn fetches today", "tomorrow"),
        (usage.apify_month, "LinkedIn posts this month", resets),
    ):
        if quota.left is not None and quota.left < 1:
            raise LimitExceededError(
                f"You used {quota.used} of your {quota.limit} {what} (more on {when}). "
                "Keywords someone fetched in the last day still work — they are free.",
                code="FETCH_QUOTA_REACHED",
            )


# ---------- the meter ----------


class Meter:
    def __init__(
        self,
        session: AsyncSession,
        settings: Settings,
        redis: Redis | None,
        user_id: uuid.UUID | None,
    ) -> None:
        self.session = session
        self.settings = settings
        self.redis = redis
        self.user_id = user_id

    async def _cached(self, key: str) -> str | None:
        if self.redis is None:
            return None
        value = await self.redis.get(f"provider-cache:{key}")
        return value.decode() if isinstance(value, bytes) else value

    async def _lock(self, key: str) -> bool:
        """Wait (up to LOCK_SECONDS) while another worker runs the same query."""
        if self.redis is None:
            return False
        lock = f"provider-lock:{key}"
        for _ in range(LOCK_SECONDS):
            if await self.redis.set(lock, "1", nx=True, ex=LOCK_SECONDS):
                return True
            await asyncio.sleep(1)
            if await self._cached(key):
                return False
        return False

    async def _unlock(self, key: str) -> None:
        if self.redis is not None:
            await self.redis.delete(f"provider-lock:{key}")

    async def _log(self, provider: str, key: str, query: dict[str, Any], **values: Any) -> None:
        self.session.add(
            ProviderCall(
                user_id=self.user_id, provider=provider, cache_key=key, query=query, **values
            )
        )
        await self.session.commit()

    async def _run[T](
        self,
        provider: str,
        query: dict[str, Any],
        ttl_hours: float,
        cls: type[T],
        units_of: Any,
        cost_of: Any,
        call: Any,
        quota_units: int,
    ) -> list[T]:
        key = _key(provider, query)
        if raw := await self._cached(key):
            items = _load(raw, cls)
            await self._log(provider, key, query, cached=True, results=len(items))
            return items
        locked = await self._lock(key)
        try:
            if raw := await self._cached(key):  # filled while we waited
                items = _load(raw, cls)
                await self._log(provider, key, query, cached=True, results=len(items))
                return items
            if self.user_id is not None:
                await check_quota(self.session, self.user_id, provider, units=quota_units)
            await self.session.commit()  # no transaction held open during the API call
            started = perf_counter()
            try:
                items, extra = await call()
            except AppError as exc:
                await self._log(
                    provider,
                    key,
                    query,
                    success=False,
                    error=exc.message[:500],
                    latency_ms=round((perf_counter() - started) * 1000),
                )
                raise
            units = units_of(items)
            await self._log(
                provider,
                key,
                query,
                units=units,
                results=len(items),
                cost_usd=Decimal(str(round(cost_of(units), 4))),
                latency_ms=round((perf_counter() - started) * 1000),
                **extra,
            )
            if self.redis is not None and ttl_hours > 0:
                await self.redis.set(
                    f"provider-cache:{key}", _dump(items), ex=int(ttl_hours * 3600)
                )
            return items
        finally:
            if locked:
                await self._unlock(key)

    # ----- JSearch -----

    async def jsearch(self, source: JobSource, query: JobQuery) -> list[NormalizedJob]:
        normalized = {
            "keywords": _norm(query.keywords),
            "location": _norm(query.location),
            "experience": query.experience.value if query.experience else None,
            "remote_only": query.remote_only,
            "country": query.country.lower(),
            "date_posted": query.date_posted,
            "page": query.page,
            "num_pages": query.num_pages,
        }
        price = self.settings.jsearch_cost_per_request_usd

        async def call() -> tuple[list[NormalizedJob], dict[str, Any]]:
            items = await source.search(query)
            remaining = getattr(source, "last_quota_remaining", None)
            await self._alert_quota(remaining)
            return items, {"quota_remaining": remaining}

        return await self._run(
            JSEARCH,
            normalized,
            self.settings.jsearch_cache_hours,
            NormalizedJob,
            lambda _items: query.num_pages,  # JSearch bills one request per page
            lambda units: units * price,
            call,
            quota_units=query.num_pages,
        )

    async def _alert_quota(self, remaining: int | None) -> None:
        """Tell the admins (once a day) when the JSearch plan is nearly used up."""
        threshold = self.settings.jsearch_quota_alert_below
        if remaining is None or remaining >= threshold or self.redis is None:
            return
        if not await self.redis.set(ALERT_KEY, "1", nx=True, ex=86400):
            return
        admins = (
            await self.session.scalars(select(User.id).where(User.role == UserRole.ADMIN))
        ).all()
        for admin_id in admins:
            notify(
                self.session,
                admin_id,
                type="usage_jsearch_quota",
                title=f"JSearch plan: only {remaining} requests left",
                body="Searches will fail when it reaches 0. Upgrade the RapidAPI plan or wait "
                "for the monthly reset; cached searches keep working.",
                link="/admin/analytics",
            )
        logger.warning("usage.jsearch_quota_low", remaining=remaining)

    # ----- Apify -----

    async def _recent_real_fetch(self, keyword_query: str) -> bool:
        hours = self.settings.apify_recent_hours
        if hours <= 0:
            return False
        found = await self.session.scalar(
            select(func.count()).where(
                ProviderCall.provider == APIFY,
                ProviderCall.cached.is_(False),
                ProviderCall.success.is_(True),
                ProviderCall.query["search"].astext == keyword_query,
                ProviderCall.created_at >= datetime.now(UTC) - timedelta(hours=hours),
            )
        )
        return bool(found)

    async def linkedin(
        self, source: PostSource, query: str, *, max_posts: int, posted_limit: PostedLimit
    ) -> list[LinkedInPost]:
        search = _norm(query)

        def key(count: int, limit: PostedLimit) -> dict[str, Any]:
            return {"search": search, "max_posts": count, "posted_limit": limit}

        # Admin cap per fetch (Settings › Platform).
        count = min(max_posts, (await app_settings(self.session)).apify_max_posts_per_fetch)
        effective: PostedLimit = posted_limit
        if not await self._cached(_key(APIFY, key(count, posted_limit))):
            # Never ask for more posts than the user has left this month (Apify bills per post).
            if self.user_id is not None:
                left = (await user_usage(self.session, self.user_id)).apify_month.left
                if left is not None and 0 < left < count:
                    count = left
            # Recently fetched → only the newest posts are new: search the last 24 h.
            if posted_limit != "24h" and await self._recent_real_fetch(search):
                effective = "24h"
        normalized = key(count, effective)
        price = self.settings.apify_cost_per_1000_posts_usd

        async def call() -> tuple[list[LinkedInPost], dict[str, Any]]:
            return (
                await source.search(query, max_posts=count, posted_limit=effective),
                {},
            )

        return await self._run(
            APIFY,
            normalized,
            self.settings.apify_cache_hours,
            LinkedInPost,
            len,  # Apify bills per post returned
            lambda units: units * price / 1000,
            call,
            quota_units=1,
        )


@dataclass
class MeteredJobSource:
    """JobSource that goes through the Meter (drop-in for the worker)."""

    meter: Meter
    source: JobSource
    name: str = JSEARCH

    async def search(self, query: JobQuery) -> list[NormalizedJob]:
        return await self.meter.jsearch(self.source, query)


@dataclass
class MeteredPostSource:
    meter: Meter
    source: PostSource

    async def search(
        self, query: str, *, max_posts: int, posted_limit: PostedLimit
    ) -> list[LinkedInPost]:
        return await self.meter.linkedin(
            self.source, query, max_posts=max_posts, posted_limit=posted_limit
        )


# ---------- admin view ----------


@dataclass(frozen=True)
class ProviderStats:
    provider: str
    calls: int
    cache_hits: int
    units: int
    cost_usd: Decimal
    failed: int

    @property
    def cache_rate(self) -> float | None:
        total = self.calls + self.cache_hits
        return round(self.cache_hits / total, 3) if total else None


async def provider_stats(
    session: AsyncSession, now: datetime | None = None
) -> tuple[list[ProviderStats], int | None]:
    """This month per provider, and the JSearch plan's last known requests-left."""
    now = now or datetime.now(UTC)
    month = _month_start(now)
    rows = await session.execute(
        select(
            ProviderCall.provider,
            func.count().filter(ProviderCall.cached.is_(False), ProviderCall.success.is_(True)),
            func.count().filter(ProviderCall.cached.is_(True)),
            func.coalesce(func.sum(ProviderCall.units), 0),
            func.coalesce(func.sum(ProviderCall.cost_usd), 0),
            func.count().filter(ProviderCall.success.is_(False)),
        )
        .where(ProviderCall.created_at >= month)
        .group_by(ProviderCall.provider)
        .order_by(ProviderCall.provider)
    )
    stats = [
        ProviderStats(p, int(calls), int(hits), int(units), Decimal(cost), int(failed))
        for p, calls, hits, units, cost, failed in rows.all()
    ]
    remaining = await session.scalar(
        select(ProviderCall.quota_remaining)
        .where(ProviderCall.provider == JSEARCH, ProviderCall.quota_remaining.is_not(None))
        .order_by(ProviderCall.created_at.desc())
        .limit(1)
    )
    return stats, remaining


async def provider_units_by_user(
    session: AsyncSession, now: datetime | None = None
) -> dict[uuid.UUID, dict[str, int]]:
    month = _month_start(now or datetime.now(UTC))
    rows = await session.execute(
        select(
            ProviderCall.user_id,
            ProviderCall.provider,
            func.coalesce(func.sum(ProviderCall.units), 0),
        )
        .where(
            ProviderCall.created_at >= month,
            ProviderCall.cached.is_(False),
            ProviderCall.user_id.is_not(None),
        )
        .group_by(ProviderCall.user_id, ProviderCall.provider)
    )
    result: dict[uuid.UUID, dict[str, int]] = {}
    for user_id, provider, units in rows.all():
        if user_id is not None:
            result.setdefault(user_id, {})[provider] = int(units)
    return result
