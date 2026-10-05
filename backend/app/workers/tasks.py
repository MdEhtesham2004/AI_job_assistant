import asyncio
import uuid
from datetime import UTC, datetime

from celery import Task as CeleryTask

from app.core.config import Settings, get_settings
from app.core.redis import create_redis
from app.db.session import create_engine, create_session_factory
from app.services.system_status import SCHEDULER_TICK_KEY
from app.workers.celery_app import celery_app
from app.workers.runner import Outcome, run_task


@celery_app.task(bind=True, name="tasks.execute", max_retries=None)
def execute(self: CeleryTask, task_id: str) -> str:
    """Run one `tasks` row. Retry limits are enforced by the runner (attempts column)."""
    result = asyncio.run(run_task(uuid.UUID(task_id), get_settings()))
    if result.outcome is Outcome.RETRY:
        raise self.retry(countdown=result.retry_in)
    return result.outcome.value


async def _dispatch_saved_searches(settings: Settings) -> int:
    from app.services.saved_searches import dispatch_due_searches
    from app.workers.dispatch import CeleryDispatcher

    now = datetime.now(UTC)
    redis = create_redis(settings)
    engine = create_engine(settings)
    try:
        # Heartbeat for Admin › System.
        await redis.set(SCHEDULER_TICK_KEY, now.isoformat(), ex=3600)
        async with create_session_factory(engine)() as session:
            return await dispatch_due_searches(session, settings, CeleryDispatcher(), now)
    finally:
        await engine.dispose()
        await redis.aclose()


async def _dispatch_digests(settings: Settings) -> int:
    from app.services.hunt import dispatch_digests
    from app.workers.dispatch import CeleryDispatcher

    engine = create_engine(settings)
    try:
        async with create_session_factory(engine)() as session:
            return await dispatch_digests(session, settings, CeleryDispatcher(), datetime.now(UTC))
    finally:
        await engine.dispose()


@celery_app.task(name="tasks.dispatch_digests")
def dispatch_digests() -> int:
    """Celery Beat, every 15 minutes: start today's digest for users whose hour has come."""
    return asyncio.run(_dispatch_digests(get_settings()))


@celery_app.task(name="tasks.dispatch_saved_searches")
def dispatch_saved_searches() -> int:
    """Celery Beat, every 5 minutes: start saved searches that are due."""
    return asyncio.run(_dispatch_saved_searches(get_settings()))


async def _dispatch_outbox(settings: Settings) -> dict[str, int]:
    from app.integrations.storage import create_storage
    from app.services.outreach import dispatch_outbox
    from app.workers.dispatch import CeleryDispatcher

    engine = create_engine(settings)
    try:
        async with create_session_factory(engine)() as session:
            return await dispatch_outbox(
                session, settings, CeleryDispatcher(), create_storage(settings), datetime.now(UTC)
            )
    finally:
        await engine.dispose()


async def _poll_replies(settings: Settings) -> dict[str, object]:
    from app.integrations.ai import AiClient
    from app.services.replies import poll_all

    redis = create_redis(settings)
    engine = create_engine(settings)
    try:
        async with create_session_factory(engine)() as session:
            return await poll_all(session, settings, AiClient(settings, redis))
    finally:
        await engine.dispose()
        await redis.aclose()


@celery_app.task(name="tasks.poll_replies")
def poll_replies() -> dict[str, object]:
    """Celery Beat, every 5 minutes: new replies, bounces, follow-up drafts, no-response."""
    return asyncio.run(_poll_replies(get_settings()))


@celery_app.task(name="tasks.dispatch_outbox")
def dispatch_outbox() -> dict[str, int]:
    """Celery Beat, every minute: send approved emails that are due; repair stuck sends."""
    return asyncio.run(_dispatch_outbox(get_settings()))
