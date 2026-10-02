import asyncio
import uuid

from celery import Task as CeleryTask

from app.core.config import get_settings
from app.workers.celery_app import celery_app
from app.workers.runner import Outcome, run_task


@celery_app.task(bind=True, name="tasks.execute", max_retries=None)
def execute(self: CeleryTask, task_id: str) -> str:
    """Run one `tasks` row. Retry limits are enforced by the runner (attempts column)."""
    result = asyncio.run(run_task(uuid.UUID(task_id), get_settings()))
    if result.outcome is Outcome.RETRY:
        raise self.retry(countdown=result.retry_in)
    return result.outcome.value
