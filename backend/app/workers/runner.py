"""Runs one `tasks` row: status, progress, retries, result, notification.

Celery-agnostic so it can be tested directly. Handlers are async and reuse the same
services and repositories as the API.
"""

import uuid
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import StrEnum
from typing import Any

import structlog
from redis.asyncio import Redis
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.core.config import Settings
from app.core.errors import AppError, ExternalServiceError
from app.core.redis import create_redis
from app.db.session import create_engine, create_session_factory
from app.integrations.ai import AiClient
from app.integrations.gotenberg import GotenbergClient
from app.integrations.storage import Storage, create_storage
from app.models.enums import NotificationSeverity, TaskStatus
from app.models.system import Task
from app.services.notifications import notify

logger = structlog.get_logger("app.worker")

# Wait before retry 1, 2, 3 … (seconds).
RETRY_DELAYS = (10, 30, 90)


class RetryableTaskError(Exception):
    """A temporary failure: the task is tried again (external service down, timeout …)."""


@dataclass
class Services:
    settings: Settings
    storage: Storage
    gotenberg: GotenbergClient
    ai: AiClient
    redis: Redis | None = None

    @classmethod
    def from_settings(cls, settings: Settings) -> "Services":
        redis = create_redis(settings)
        return cls(
            settings=settings,
            storage=create_storage(settings),
            gotenberg=GotenbergClient.from_settings(settings),
            ai=AiClient(settings, redis),
            redis=redis,
        )


@dataclass
class TaskContext:
    task: Task
    session: AsyncSession
    services: Services
    _progress_log: list[int] = field(default_factory=list)

    @property
    def user_id(self) -> uuid.UUID | None:
        return self.task.user_id

    async def progress(self, percent: int) -> None:
        self.task.progress = max(0, min(100, percent))
        self._progress_log.append(self.task.progress)
        await self.session.commit()


Handler = Callable[[TaskContext], Awaitable[dict[str, Any]]]
HANDLERS: dict[str, Handler] = {}


@dataclass(frozen=True)
class TaskDescription:
    title: str
    link: str = "/tasks"


DESCRIPTIONS: dict[str, TaskDescription] = {}


def handler(task_type: str, title: str, link: str = "/tasks") -> Callable[[Handler], Handler]:
    def register(func: Handler) -> Handler:
        HANDLERS[task_type] = func
        DESCRIPTIONS[task_type] = TaskDescription(title, link)
        return func

    return register


class Outcome(StrEnum):
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    RETRY = "retry"
    SKIPPED = "skipped"


@dataclass(frozen=True)
class RunResult:
    outcome: Outcome
    retry_in: int = 0


async def run_task(
    task_id: uuid.UUID,
    settings: Settings,
    *,
    services: Services | None = None,
    session_factory: async_sessionmaker[AsyncSession] | None = None,
) -> RunResult:
    import app.workers.handlers  # noqa: F401  (registers all handlers)

    services = services or Services.from_settings(settings)
    engine = None
    if session_factory is None:
        engine = create_engine(settings)
        session_factory = create_session_factory(engine)
    try:
        async with session_factory() as session:
            return await _run(task_id, session, services, settings)
    finally:
        if engine is not None:
            await engine.dispose()


async def _run(
    task_id: uuid.UUID, session: AsyncSession, services: Services, settings: Settings
) -> RunResult:
    task = await session.get(Task, task_id)
    if task is None or task.status in (TaskStatus.SUCCEEDED, TaskStatus.CANCELLED):
        return RunResult(Outcome.SKIPPED)  # duplicate delivery or deleted row

    log = logger.bind(task_id=str(task.id), task_type=task.type, attempt=task.attempts + 1)
    task.status = TaskStatus.RUNNING
    task.attempts += 1
    task.started_at = task.started_at or datetime.now(UTC)
    task.error = None
    await session.commit()

    description = DESCRIPTIONS.get(task.type, TaskDescription(task.type))
    try:
        func = HANDLERS.get(task.type)
        if func is None:
            raise ValueError(f"No handler for task type {task.type!r}")
        result = await func(TaskContext(task=task, session=session, services=services))
    except (RetryableTaskError, ExternalServiceError) as exc:
        message = exc.message if isinstance(exc, AppError) else str(exc)
        if task.attempts <= settings.task_max_retries:
            delay = RETRY_DELAYS[min(task.attempts - 1, len(RETRY_DELAYS) - 1)]
            task.status = TaskStatus.QUEUED
            task.error = f"Attempt {task.attempts} failed: {message} Retrying in {delay}s."
            await session.commit()
            log.warning("task.retry", error=message, retry_in=delay)
            return RunResult(Outcome.RETRY, retry_in=delay)
        return await _fail(task, session, description, message, log)
    except Exception as exc:  # unexpected: do not retry
        log.exception("task.crashed")
        message = exc.message if isinstance(exc, AppError) else "Unexpected error."
        return await _fail(task, session, description, message, log)

    task.status = TaskStatus.SUCCEEDED
    task.progress = 100
    task.result = result
    task.finished_at = datetime.now(UTC)
    if task.user_id is not None:
        notify(
            session,
            task.user_id,
            type="task_succeeded",
            title=f"{description.title} finished",
            link=description.link,
            severity=NotificationSeverity.SUCCESS,
        )
    await session.commit()
    log.info("task.succeeded")
    return RunResult(Outcome.SUCCEEDED)


async def _fail(
    task: Task,
    session: AsyncSession,
    description: TaskDescription,
    message: str,
    log: Any,
) -> RunResult:
    task.status = TaskStatus.FAILED
    task.error = message
    task.finished_at = datetime.now(UTC)
    if task.user_id is not None:
        notify(
            session,
            task.user_id,
            type="task_failed",
            title=f"{description.title} failed",
            body=message,
            link=description.link,
            severity=NotificationSeverity.ERROR,
        )
    await session.commit()
    log.error("task.failed", error=message)
    return RunResult(Outcome.FAILED)
