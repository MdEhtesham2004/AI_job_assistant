from app.models.system import AuditLog
from app.repositories.base import BaseRepository


class AuditLogRepository(BaseRepository[AuditLog]):
    """Append-only: no update/delete helpers are used for audit logs."""

    model = AuditLog
