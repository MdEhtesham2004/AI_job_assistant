from collections.abc import Sequence
from enum import StrEnum

from sqlalchemy import ColumnElement, and_, func, or_, select

from app.models.accounts import User
from app.models.enums import ApprovalStatus, UserRole
from app.repositories.base import BaseRepository


class UserFilter(StrEnum):
    """Admin › Users tabs. `deactivated` overrides the approval status."""

    ALL = "all"
    PENDING = "pending"
    APPROVED = "approved"
    REJECTED = "rejected"
    DEACTIVATED = "deactivated"


def _filter_condition(status: UserFilter) -> ColumnElement[bool] | None:
    if status is UserFilter.DEACTIVATED:
        return User.is_active.is_(False)
    if status is UserFilter.ALL:
        return None
    return and_(User.is_active.is_(True), User.approval_status == ApprovalStatus(status.value))


class UserRepository(BaseRepository[User]):
    model = User

    async def get_by_email(self, email: str) -> User | None:
        # email is citext → comparison is case-insensitive in the database.
        return await self.session.scalar(select(User).where(User.email == email))

    async def search(
        self, *, status: UserFilter, query: str | None, limit: int, offset: int
    ) -> tuple[Sequence[User], int]:
        conditions: list[ColumnElement[bool]] = []
        if (condition := _filter_condition(status)) is not None:
            conditions.append(condition)
        if query:
            pattern = f"%{query.strip()}%"
            conditions.append(or_(User.email.ilike(pattern), User.full_name.ilike(pattern)))

        total = await self.session.scalar(select(func.count()).select_from(User).where(*conditions))
        # Pending first (they need action), then newest.
        pending_first = (User.approval_status == ApprovalStatus.PENDING).desc()
        rows = await self.session.scalars(
            select(User)
            .where(*conditions)
            .order_by(pending_first, User.created_at.desc())
            .limit(limit)
            .offset(offset)
        )
        return rows.all(), total or 0

    async def status_counts(self) -> dict[str, int]:
        counts = {}
        for status in UserFilter:
            query = select(func.count()).select_from(User)
            if (condition := _filter_condition(status)) is not None:
                query = query.where(condition)
            counts[status.value] = await self.session.scalar(query) or 0
        return counts

    async def count_active_admins(self) -> int:
        query = (
            select(func.count())
            .select_from(User)
            .where(
                User.role == UserRole.ADMIN,
                User.is_active.is_(True),
                User.approval_status == ApprovalStatus.APPROVED,
            )
        )
        return await self.session.scalar(query) or 0
