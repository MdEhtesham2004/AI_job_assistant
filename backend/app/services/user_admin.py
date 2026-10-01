import uuid
from collections.abc import Sequence
from datetime import UTC, datetime
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import ConflictError, NotFoundError
from app.models.accounts import User
from app.models.enums import ActorType, ApprovalStatus, UserRole
from app.models.system import AuditLog
from app.repositories.refresh_tokens import RefreshTokenRepository
from app.repositories.users import UserFilter, UserRepository


class UserAdminService:
    """Admin â€º Users: approve or reject sign-ups, (de)activate accounts, change roles."""

    def __init__(self, session: AsyncSession, admin: User) -> None:
        self.session = session
        self.admin = admin
        self.users = UserRepository(session)
        self.tokens = RefreshTokenRepository(session)

    # ---------- queries ----------

    async def list_users(
        self, *, status: UserFilter, query: str | None, page: int, page_size: int
    ) -> tuple[Sequence[User], int]:
        return await self.users.search(
            status=status, query=query, limit=page_size, offset=(page - 1) * page_size
        )

    async def status_counts(self) -> dict[str, int]:
        return await self.users.status_counts()

    async def get_user(self, user_id: uuid.UUID) -> User:
        user = await self.users.get(user_id)
        if user is None:
            raise NotFoundError("User not found.")
        return user

    # ---------- actions ----------

    async def approve(self, user_id: uuid.UUID) -> User:
        user = await self.get_user(user_id)
        if user.approval_status is not ApprovalStatus.APPROVED:
            user.approval_status = ApprovalStatus.APPROVED
            user.approved_by = self.admin.id
            user.approved_at = datetime.now(UTC)
            user.rejection_reason = None
            self._audit("user.approve", user)
            await self._save(user)
        return user

    async def reject(self, user_id: uuid.UUID, reason: str | None) -> User:
        user = await self.get_user(user_id)
        self._forbid_self(user, "reject")
        if user.approval_status is not ApprovalStatus.PENDING:
            raise ConflictError(
                "Only pending accounts can be rejected. Deactivate approved accounts instead.",
                code="INVALID_STATUS",
            )
        user.approval_status = ApprovalStatus.REJECTED
        user.rejection_reason = reason or None
        await self.tokens.revoke_all_for_user(user.id, datetime.now(UTC))
        self._audit("user.reject", user, {"reason": reason} if reason else None)
        await self._save(user)
        return user

    async def deactivate(self, user_id: uuid.UUID) -> User:
        user = await self.get_user(user_id)
        self._forbid_self(user, "deactivate")
        if user.is_active:
            await self._keep_one_admin(user)
            user.is_active = False
            await self.tokens.revoke_all_for_user(user.id, datetime.now(UTC))
            self._audit("user.deactivate", user)
            await self._save(user)
        return user

    async def reactivate(self, user_id: uuid.UUID) -> User:
        user = await self.get_user(user_id)
        if not user.is_active:
            user.is_active = True
            self._audit("user.reactivate", user)
            await self._save(user)
        return user

    async def change_role(self, user_id: uuid.UUID, role: UserRole) -> User:
        user = await self.get_user(user_id)
        self._forbid_self(user, "change the role of")
        if user.role is role:
            return user
        if role is UserRole.ADMIN and (
            user.approval_status is not ApprovalStatus.APPROVED or not user.is_active
        ):
            raise ConflictError(
                "Only approved, active accounts can become admins.", code="INVALID_STATUS"
            )
        if role is UserRole.USER:
            await self._keep_one_admin(user)

        previous = user.role
        user.role = role
        user.is_superuser = role is UserRole.ADMIN
        self._audit("user.change_role", user, {"from": previous.value, "to": role.value})
        await self._save(user)
        return user

    async def _save(self, user: User) -> None:
        await self.session.commit()
        # updated_at is set by the database on UPDATE; reload it before the response reads it.
        await self.session.refresh(user)

    # ---------- rules ----------

    def _forbid_self(self, user: User, action: str) -> None:
        if user.id == self.admin.id:
            raise ConflictError(f"You cannot {action} your own account.", code="CANNOT_MODIFY_SELF")

    async def _keep_one_admin(self, user: User) -> None:
        if user.role is UserRole.ADMIN and await self.users.count_active_admins() <= 1:
            raise ConflictError("At least one active admin must remain.", code="LAST_ADMIN")

    def _audit(self, action: str, user: User, data: dict[str, Any] | None = None) -> None:
        self.session.add(
            AuditLog(
                user_id=self.admin.id,
                actor_type=ActorType.ADMIN,
                action=action,
                entity_type="user",
                entity_id=user.id,
                data=data,
            )
        )
