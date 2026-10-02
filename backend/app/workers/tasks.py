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


@celery_app.task(name="tasks.dispatch_saved_searches")
def dispatch_saved_searches() -> int:
    """Celery Beat, every 5 minutes: start saved searches that are due."""
    return asyncio.run(_dispatch_saved_searches(get_settings()))
