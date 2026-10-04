"""Celery application (Phase 1 §2.7). Task state lives in PostgreSQL, so no result backend.

Run a worker (Windows needs the solo pool):
    uv run celery -A app.workers.celery_app worker --pool=solo -Q default,ai,pdf,email -l info
Run the scheduler (saved searches, scheduled emails; exactly one beat process):
    uv run celery -A app.workers.celery_app beat -l info
"""

from celery import Celery

from app.core.config import get_settings
from app.core.monitoring import init_sentry

settings = get_settings()
init_sentry(settings, component="worker")  # no-op without SENTRY_DSN

celery_app = Celery("ai_job_platform", broker=settings.redis_url, include=["app.workers.tasks"])
celery_app.conf.update(
    task_default_queue="default",
    task_acks_late=True,  # a crashed worker leaves the message for another one
    task_reject_on_worker_lost=True,
    worker_prefetch_multiplier=1,
    task_ignore_result=True,
    broker_connection_retry_on_startup=True,
    timezone="UTC",
    beat_schedule={
        # Phase 8: start saved searches whose cron time has passed (in the user's time zone).
        "saved-searches-due": {
            "task": "tasks.dispatch_saved_searches",
            "schedule": 300.0,
            "options": {"queue": "default", "expires": 290},
        },
        # Phase 12: approved emails whose send time has come (cap + gap respected).
        "outbox-due": {
            "task": "tasks.dispatch_outbox",
            "schedule": 60.0,
            "options": {"queue": "email", "expires": 55},
        },
        # Phase 13: replies / bounces / follow-ups / no-response. (Automation has no
        # schedule: it runs only when the user clicks "Automate" — admin decision.)
        "replies-poll": {
            "task": "tasks.poll_replies",
            "schedule": 300.0,
            "options": {"queue": "default", "expires": 290},
        },
    },
)
