from dataclasses import dataclass
from datetime import UTC, datetime

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import ValidationAppError
from app.core.security import hash_password
from app.models.accounts import User
from app.models.enums import ActorType, ApprovalStatus, UserRole
from app.models.system import AuditLog
from app.repositories.audit_logs import AuditLogRepository
from app.repositories.users import UserRepository

MIN_PASSWORD_LENGTH = 12


@dataclass(frozen=True)
class SeedResult:
    user: User
    created: bool


class AdminSeedService:
    """Creates the first admin account, or promotes an existing account to admin. Idempotent."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self.users = UserRepository(session)
        self.audit = AuditLogRepository(session)

    async def ensure_admin(self, *, email: str, full_name: str, password: str) -> SeedResult:
        email = email.strip()
        if "@" not in email:
            raise ValidationAppError("A valid email address is required.")
        if len(password) < MIN_PASSWORD_LENGTH:
            raise ValidationAppError(
                f"The admin password must be at least {MIN_PASSWORD_LENGTH} characters."
            )

        now = datetime.now(UTC)
        user = await self.users.get_by_email(email)
        created = user is None

        if user is None:
            user = await self.users.add(
                User(
                    email=email,
                    full_name=full_name.strip() or "Administrator",
                    hashed_password=hash_password(password),
                    role=UserRole.ADMIN,
                    approval_status=ApprovalStatus.APPROVED,
                    approved_at=now,
                    is_active=True,
                    is_superuser=True,
                    is_verified=True,
                )
            )
        else:
            # Existing account: promote and approve, but never overwrite its password.
            await self.users.update(
                user,
                role=UserRole.ADMIN,
                approval_status=ApprovalStatus.APPROVED,
                approved_at=user.approved_at or now,
                is_active=True,
                is_superuser=True,
            )

        await self.audit.add(
            AuditLog(
                user_id=user.id,
                actor_type=ActorType.SYSTEM,
                action="user.seed_admin",
                entity_type="user",
                entity_id=user.id,
                data={"created": created},
            )
        )
        await self.session.commit()
        return SeedResult(user=user, created=created)
