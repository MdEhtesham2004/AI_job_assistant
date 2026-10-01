from app.models.system import Task
from app.repositories.base import OwnedRepository


class TaskRepository(OwnedRepository[Task]):
    """User-owned background tasks (API arrives in Phase 6)."""

    model = Task
