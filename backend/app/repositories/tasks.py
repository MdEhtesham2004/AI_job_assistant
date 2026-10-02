import uuid
from collections.abc import Sequence

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.enums import TaskStatus
from app.models.system import Task
from app.repositories.base import OwnedRepository


class TaskRepository(OwnedRepository[Task]):
    """Background tasks of one user."""

    model = Task

    async def page(self, *, limit: int, offset: int) -> tuple[Sequence[Task], int]:
        total = await self.count()
        rows = await self.session.scalars(
            self.scoped().order_by(Task.created_at.desc()).limit(limit).offset(offset)
        )
        return rows.all(), total

    async def active_for(self, entity_type: str, entity_id: uuid.UUID) -> Sequence[Task]:
        """Queued or running tasks working on one entity (e.g. a resume version)."""
        rows = await self.session.scalars(
            self.scoped()
            .where(
                Task.entity_type == entity_type,
                Task.entity_id == entity_id,
                Task.status.in_([TaskStatus.QUEUED, TaskStatus.RUNNING]),
            )
            .order_by(Task.created_at)
        )
        return rows.all()


async def task_counts(session: AsyncSession) -> dict[str, int]:
    """System-wide counts per status for Admin › System (not owner-scoped)."""
    rows = await session.execute(select(Task.status, func.count()).group_by(Task.status))
    counts = {status.value: 0 for status in TaskStatus}
    for status, count in rows.all():
        counts[TaskStatus(status).value] = count
    return counts
