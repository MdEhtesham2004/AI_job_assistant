"""Celery application (Phase 1 §2.7). Task state lives in PostgreSQL, so no result backend.

Run a worker (Windows needs the solo pool):
    uv run celery -A app.workers.celery_app worker --pool=solo -Q default,ai,pdf,email -l info
"""

from celery import Celery

from app.core.config import get_settings

settings = get_settings()

celery_app = Celery("ai_job_platform", broker=settings.redis_url, include=["app.workers.tasks"])
celery_app.conf.update(
    task_default_queue="default",
    task_acks_late=True,  # a crashed worker leaves the message for another one
    task_reject_on_worker_lost=True,
    worker_prefetch_multiplier=1,
    task_ignore_result=True,
    broker_connection_retry_on_startup=True,
    timezone="UTC",
    beat_schedule={},  # scheduled jobs arrive with saved searches (Phase 8) and replies (Phase 13)
)
