"""Admin › System: health of every dependency the platform uses."""

import asyncio
from collections.abc import Awaitable, Callable
from datetime import UTC, datetime
from time import perf_counter
from typing import Any

import structlog
from redis.asyncio import Redis
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession

from app.core.config import Settings
from app.integrations.gotenberg import GotenbergClient
from app.integrations.storage import Storage
from app.repositories.tasks import task_counts
from app.schemas.tasks import ServiceCheck, SystemStatus
from app.services.health import HealthService

logger = structlog.get_logger("app.system")
CHECK_TIMEOUT = 4.0


async def _timed(check: Callable[[], Awaitable[dict[str, Any] | None]]) -> ServiceCheck:
    started = perf_counter()
    try:
        async with asyncio.timeout(CHECK_TIMEOUT):
            details = await check() or {}
    except Exception as exc:
        logger.warning("system.check_failed", error_type=type(exc).__name__)
        return ServiceCheck(status="error", details={"error": type(exc).__name__})
    details["latency_ms"] = round((perf_counter() - started) * 1000, 1)
    return ServiceCheck(status="ok", details=details)


def _ping_workers() -> list[str]:
    from app.workers.celery_app import celery_app

    replies = celery_app.control.ping(timeout=1.5) or []
    return sorted(name for reply in replies for name in reply)


class SystemStatusService:
    def __init__(
        self,
        *,
        settings: Settings,
        engine: AsyncEngine,
        session: AsyncSession,
        redis: Redis,
        storage: Storage,
        gotenberg: GotenbergClient,
    ) -> None:
        self.settings = settings
        self.engine = engine
        self.session = session
        self.redis = redis
        self.storage = storage
        self.gotenberg = gotenberg

    async def status(self) -> SystemStatus:
        database = await HealthService(self.engine).check_database()

        async def redis_check() -> dict[str, Any]:
            await self.redis.ping()
            return {}

        async def worker_check() -> dict[str, Any]:
            workers = await asyncio.to_thread(_ping_workers)
            if not workers:
                raise RuntimeError("No worker answered")
            return {"workers": workers}

        async def storage_check() -> dict[str, Any]:
            await self.storage.check()
            return {"backend": self.storage.name}

        async def gotenberg_check() -> dict[str, Any]:
            await self.gotenberg.check()
            return {}

        services: dict[str, ServiceCheck] = {
            "api": ServiceCheck(status="ok", details={"version": self.settings.app_version}),
            "database": ServiceCheck(status=database.status, details=database.details),
            "redis": await _timed(redis_check),
            "worker": (
                await _timed(worker_check)
                if self.settings.celery_enabled
                else ServiceCheck(status="disabled")
            ),
            "storage": await _timed(storage_check),
            "gotenberg": await _timed(gotenberg_check),
            "ai": (
                ServiceCheck(
                    status="ok",
                    details={
                        "model": self.settings.ai_model_default,
                        "base_url": self.settings.ai_base_url,
                    },
                )
                if self.settings.ai_configured
                else ServiceCheck(status="not_configured")
            ),
        }
        degraded = any(check.status == "error" for check in services.values())
        return SystemStatus(
            status="degraded" if degraded else "ok",
            checked_at=datetime.now(UTC),
            services=services,
            tasks=await task_counts(self.session),
        )
