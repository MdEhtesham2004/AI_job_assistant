import uuid
from collections.abc import Sequence
from datetime import datetime

from sqlalchemy import func, select, update

from app.models.system import Notification
from app.repositories.base import OwnedRepository


class NotificationRepository(OwnedRepository[Notification]):
    model = Notification

    async def page(
        self, *, unread_only: bool, limit: int, offset: int
    ) -> tuple[Sequence[Notification], int]:
        query = self.scoped()
        if unread_only:
            query = query.where(Notification.read_at.is_(None))
        total = await self.session.scalar(select(func.count()).select_from(query.subquery()))
        rows = await self.session.scalars(
            query.order_by(Notification.created_at.desc()).limit(limit).offset(offset)
        )
        return rows.all(), total or 0

    async def unread_count(self) -> int:
        query = (
            select(func.count())
            .select_from(Notification)
            .where(Notification.user_id == self.owner_id, Notification.read_at.is_(None))
        )
        return await self.session.scalar(query) or 0

    async def mark_read(self, notification_id: uuid.UUID, at: datetime) -> Notification | None:
        notification = await self.get(notification_id)
        if notification is not None and notification.read_at is None:
            notification.read_at = at
        return notification

    async def mark_all_read(self, at: datetime) -> None:
        await self.session.execute(
            update(Notification)
            .where(Notification.user_id == self.owner_id, Notification.read_at.is_(None))
            .values(read_at=at)
        )
