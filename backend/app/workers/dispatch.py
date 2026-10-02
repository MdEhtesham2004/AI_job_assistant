import uuid

from app.services.tasks import TASK_QUEUES


class CeleryDispatcher:
    """Sends a committed `tasks` row to its Celery queue."""

    def send(self, task_id: uuid.UUID, task_type: str) -> None:
        from app.workers.celery_app import celery_app

        celery_app.send_task(
            "tasks.execute", args=[str(task_id)], queue=TASK_QUEUES.get(task_type, "default")
        )
