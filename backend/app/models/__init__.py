"""Import every model module here so Alembic autogenerate sees all tables."""

from app.models.accounts import User
from app.models.system import AuditLog, Task

__all__ = ["AuditLog", "Task", "User"]
