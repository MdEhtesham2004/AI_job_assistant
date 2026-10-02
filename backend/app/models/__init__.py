"""Import every model module here so Alembic autogenerate sees all tables."""

from app.models.accounts import AuthRefreshToken, Profile, User, UserSettings
from app.models.system import AiCall, AuditLog, Notification, Task

__all__ = [
    "AiCall",
    "AuditLog",
    "AuthRefreshToken",
    "Notification",
    "Profile",
    "Task",
    "User",
    "UserSettings",
]
