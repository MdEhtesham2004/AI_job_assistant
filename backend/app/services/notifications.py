import uuid
from collections.abc import Sequence
from datetime import UTC, datetime

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import NotFoundError
from app.models.enums import NotificationSeverity
from app.models.system import Notification
from app.repositories.notifications import NotificationRepository


def notify(
    session: AsyncSession,
    user_id: uuid.UUID,
    *,
    type: str,
    title: str,
    body: str | None = None,
    link: str | None = None,
    severity: NotificationSeverity = NotificationSeverity.INFO,
) -> Notification:
    """Add a notification to the current transaction (the caller commits)."""
    notification = Notification(
        user_id=user_id, type=type, title=title, body=body, link=link, severity=severity
    )
    session.add(notification)
    return notification


class NotificationService:
    def __init__(self, session: AsyncSession, user_id: uuid.UUID) -> None:
        self.session = session
        self.notifications = NotificationRepository(session, owner_id=user_id)

    async def list(
        self, *, unread_only: bool, page: int, page_size: int, category: str | None = None
    ) -> tuple[Sequence[Notification], int]:
        return await self.notifications.page(
            unread_only=unread_only,
            limit=page_size,
            offset=(page - 1) * page_size,
            category=category,
        )

    async def unread_count(self) -> int:
        return await self.notifications.unread_count()

    async def mark_read(self, notification_id: uuid.UUID) -> Notification:
        notification = await self.notifications.mark_read(notification_id, datetime.now(UTC))
        if notification is None:
            raise NotFoundError("Notification not found.")
        await self.session.commit()
        await self.session.refresh(notification)
        return notification

    async def mark_all_read(self) -> None:
        await self.notifications.mark_all_read(datetime.now(UTC))
        await self.session.commit()
