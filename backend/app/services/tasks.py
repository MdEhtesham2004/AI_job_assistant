"""Background tasks: create (then dispatch after commit), read, and expose results."""

import uuid
from collections.abc import Sequence
from typing import Any, Protocol

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings
from app.core.errors import NotFoundError
from app.core.security import FileTokenClaims, create_file_token
from app.models.system import Task
from app.repositories.tasks import TaskRepository

# Which Celery queue runs which task type (Phase 1 §2.7).
TASK_QUEUES: dict[str, str] = {
    "test_pdf": "pdf",
    "test_failure": "default",
    "ai_test": "ai",
    "resume_parse": "ai",
    "resume_ats": "ai",
    "resume_improve": "ai",
    "resume_linkedin": "ai",
    "job_search": "default",
    "job_fetch_page": "default",
    "job_analyze": "ai",
    "job_analyze_batch": "ai",
    "resume_tailor": "ai",
    "cover_letter": "ai",
}


class TaskDispatcher(Protocol):
    def send(self, task_id: uuid.UUID, task_type: str) -> None: ...


class RecordingDispatcher:
    """Used when Celery is disabled (tests): remembers what would have been sent."""

    def __init__(self) -> None:
        self.sent: list[tuple[uuid.UUID, str]] = []

    def send(self, task_id: uuid.UUID, task_type: str) -> None:
        self.sent.append((task_id, task_type))


class TaskService:
    def __init__(
        self, session: AsyncSession, user_id: uuid.UUID, dispatcher: TaskDispatcher
    ) -> None:
        self.session = session
        self.user_id = user_id
        self.dispatcher = dispatcher
        self.tasks = TaskRepository(session, owner_id=user_id)

    async def create(
        self,
        task_type: str,
        payload: dict[str, Any] | None = None,
        *,
        entity_type: str | None = None,
        entity_id: uuid.UUID | None = None,
    ) -> Task:
        if task_type not in TASK_QUEUES:
            raise ValueError(f"Unknown task type: {task_type}")
        task = await self.tasks.add(
            Task(
                type=task_type,
                payload=payload or {},
                entity_type=entity_type,
                entity_id=entity_id,
            )
        )
        await self.session.commit()
        # After commit, so the worker always finds the row (Phase 1 §2.6).
        self.dispatcher.send(task.id, task_type)
        return task

    async def get(self, task_id: uuid.UUID) -> Task:
        task = await self.tasks.get(task_id)
        if task is None:
            raise NotFoundError("Task not found.")
        return task

    async def list(self, *, page: int, page_size: int) -> tuple[Sequence[Task], int]:
        return await self.tasks.page(limit=page_size, offset=(page - 1) * page_size)


def public_result(task: Task, settings: Settings) -> dict[str, Any] | None:
    """Task result for the API: stored file keys become fresh, short-lived download links."""
    if task.result is None:
        return None
    result = dict(task.result)
    file_info = result.pop("file", None)
    if isinstance(file_info, dict) and task.user_id is not None:
        result["file"] = {
            "name": file_info["name"],
            "size": file_info.get("size"),
            "content_type": file_info["content_type"],
            "download_url": download_url(
                settings,
                task.user_id,
                key=str(file_info["key"]),
                filename=str(file_info["name"]),
                content_type=str(file_info["content_type"]),
            ),
        }
    return result


def download_url(
    settings: Settings, owner_id: uuid.UUID, *, key: str, filename: str, content_type: str
) -> str:
    """A short-lived signed link to a stored file (storage keys are never exposed)."""
    token = create_file_token(
        FileTokenClaims(owner_id=owner_id, key=key, filename=filename, content_type=content_type),
        settings.secret_key,
        settings.file_link_minutes,
    )
    return f"{settings.api_prefix}/files/{token}"
