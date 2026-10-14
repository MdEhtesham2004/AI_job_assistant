import uuid
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

import structlog
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings
from app.core.errors import (
    AuthenticationError,
    ConflictError,
    PermissionDeniedError,
    ValidationAppError,
)
from app.core.security import (
    InvalidTokenError,
    create_access_token,
    create_password_reset_token,
    decode_password_reset_token,
    generate_refresh_token,
    hash_password,
    hash_token,
    verify_password,
)
from app.models.accounts import AuthRefreshToken, User
from app.models.enums import ActorType, ApprovalStatus
from app.models.system import AuditLog
from app.repositories.audit_logs import AuditLogRepository
from app.repositories.refresh_tokens import RefreshTokenRepository
from app.repositories.users import UserRepository

logger = structlog.get_logger("app.auth")

# Two tabs (or React StrictMode) may refresh with the same cookie at the same moment.
# Reuse within this window is treated as a race, not as theft.
REFRESH_REUSE_GRACE = timedelta(seconds=10)


@dataclass(frozen=True)
class ClientInfo:
    ip_address: str | None = None
    user_agent: str | None = None


@dataclass(frozen=True)
class Session:
    user: User
    access_token: str
    expires_in: int
    refresh_token: str
    refresh_expires_at: datetime


def ensure_can_sign_in(user: User) -> None:
    """Pending users may sign in (to see "awaiting approval"); rejected/deactivated may not."""
    if not user.is_active:
        raise PermissionDeniedError(
            "This account has been deactivated.", code="ACCOUNT_DEACTIVATED"
        )
    if user.approval_status is ApprovalStatus.REJECTED:
        raise PermissionDeniedError(
            "This account request was not approved.", code="ACCOUNT_REJECTED"
        )


def _check_password_policy(password: str, email: str) -> None:
    if password.strip().lower() == email.strip().lower():
        raise ValidationAppError(
            "The password must not be the same as the email address.", code="WEAK_PASSWORD"
        )
    if len(set(password)) < 4:
        raise ValidationAppError("The password is too simple.", code="WEAK_PASSWORD")


class AuthService:
    """Registration, sign-in, token rotation, logout and password changes (Phase 4)."""

    def __init__(self, session: AsyncSession, settings: Settings) -> None:
        self.session = session
        self.settings = settings
        self.users = UserRepository(session)
        self.tokens = RefreshTokenRepository(session)
        self.audit = AuditLogRepository(session)

    # ---------- public use-cases ----------

    async def register(
        self, *, email: str, full_name: str, password: str, client: ClientInfo
    ) -> Session:
        _check_password_policy(password, email)
        if await self.users.get_by_email(email) is not None:
            raise ConflictError("An account with this email already exists.", code="EMAIL_TAKEN")

        user = User(email=email, full_name=full_name, hashed_password=hash_password(password))
        try:
            await self.users.add(user)
        except IntegrityError as exc:  # concurrent registration with the same email
            await self.session.rollback()
            raise ConflictError(
                "An account with this email already exists.", code="EMAIL_TAKEN"
            ) from exc

        self._audit("auth.register", user, client)
        session = await self._start_session(user, client, family_id=uuid.uuid4())
        await self.session.commit()
        return session

    async def login(self, *, email: str, password: str, client: ClientInfo) -> Session:
        user = await self.users.get_by_email(email)
        if not verify_password(password, user.hashed_password if user else None) or user is None:
            if user is not None:
                self._audit("auth.login_failed", user, client)
                await self.session.commit()
            raise AuthenticationError("Incorrect email or password.", code="INVALID_CREDENTIALS")

        ensure_can_sign_in(user)
        user.last_login_at = datetime.now(UTC)
        self._audit("auth.login", user, client)
        session = await self._start_session(user, client, family_id=uuid.uuid4())
        await self.session.commit()
        return session

    async def refresh(self, raw_token: str | None, client: ClientInfo) -> Session:
        if not raw_token:
            raise AuthenticationError("Your session has expired. Please sign in again.")

        now = datetime.now(UTC)
        stored = await self.tokens.get_by_hash(hash_token(raw_token))
        if stored is None:
            raise AuthenticationError("Your session has expired. Please sign in again.")

        if (
            stored.revoked_at is not None
            and stored.replaced_by_id is not None
            and now - stored.revoked_at < REFRESH_REUSE_GRACE
        ):
            # Just rotated by a parallel request: the browser already holds the new cookie.
            raise AuthenticationError(
                "Session refresh in progress, please retry.", code="REFRESH_RACE"
            )

        if stored.revoked_at is not None:
            # A rotated token was used again → probably stolen. Kill the whole chain.
            await self.tokens.revoke_family(stored.family_id, now)
            self.audit_entry(
                "auth.refresh_reuse_detected",
                stored.user_id,
                client,
                data={"family_id": str(stored.family_id)},
            )
            await self.session.commit()
            logger.warning("auth.refresh_reuse_detected", user_id=str(stored.user_id))
            raise AuthenticationError("Your session has expired. Please sign in again.")

        if stored.expires_at <= now:
            raise AuthenticationError("Your session has expired. Please sign in again.")

        user = await self.users.get(stored.user_id)
        if user is None:
            raise AuthenticationError("Your session has expired. Please sign in again.")
        ensure_can_sign_in(user)

        session = await self._start_session(user, client, family_id=stored.family_id)
        new_token = await self.tokens.get_by_hash(hash_token(session.refresh_token))
        stored.revoked_at = now
        stored.replaced_by_id = new_token.id if new_token else None
        await self.session.commit()
        return session

    async def logout(self, raw_token: str | None, client: ClientInfo) -> None:
        if not raw_token:
            return
        stored = await self.tokens.get_by_hash(hash_token(raw_token))
        if stored is None:
            return
        await self.tokens.revoke_family(stored.family_id, datetime.now(UTC))
        self.audit_entry("auth.logout", stored.user_id, client)
        await self.session.commit()

    async def change_password(
        self, user: User, *, current_password: str, new_password: str, client: ClientInfo
    ) -> Session:
        if not verify_password(current_password, user.hashed_password):
            raise ValidationAppError(
                "The current password is incorrect.", code="INVALID_CURRENT_PASSWORD"
            )
        if current_password == new_password:
            raise ValidationAppError(
                "The new password must differ from the current one.", code="WEAK_PASSWORD"
            )
        _check_password_policy(new_password, user.email)

        user.hashed_password = hash_password(new_password)
        # Sign out every other device; this browser gets a fresh session.
        await self.tokens.revoke_all_for_user(user.id, datetime.now(UTC))
        self._audit("auth.password_change", user, client)
        session = await self._start_session(user, client, family_id=uuid.uuid4())
        await self.session.commit()
        return session

    async def request_password_reset(self, email: str, client: ClientInfo) -> str | None:
        """Create a reset token. Returns it so a mail sender (Phase 12) can deliver it.

        The API always answers the same way, whether or not the email exists.
        """
        user = await self.users.get_by_email(email)
        if user is None or not user.is_active:
            return None
        token = create_password_reset_token(
            user.id,
            user.hashed_password,
            self.settings.secret_key,
            self.settings.password_reset_minutes,
        )
        self._audit("auth.password_reset_requested", user, client)
        await self.session.commit()
        return token

    async def reset_password(self, token: str, new_password: str, client: ClientInfo) -> None:
        invalid = ValidationAppError(
            "This reset link is invalid or has expired.", code="INVALID_RESET_TOKEN"
        )
        try:
            claims = decode_password_reset_token(token, self.settings.secret_key)
        except InvalidTokenError as exc:
            raise invalid from exc

        user = await self.users.get(claims.user_id)
        # The token embeds a fingerprint of the old password hash → usable only once.
        if user is None or not claims.matches(user.hashed_password, self.settings.secret_key):
            raise invalid
        _check_password_policy(new_password, user.email)

        user.hashed_password = hash_password(new_password)
        await self.tokens.revoke_all_for_user(user.id, datetime.now(UTC))
        self._audit("auth.password_reset", user, client)
        await self.session.commit()

    # ---------- helpers ----------

    async def _start_session(
        self, user: User, client: ClientInfo, *, family_id: uuid.UUID
    ) -> Session:
        access_token, expires_in = create_access_token(
            user.id, self.settings.secret_key, self.settings.access_token_minutes
        )
        refresh_token = generate_refresh_token()
        expires_at = datetime.now(UTC) + timedelta(days=self.settings.refresh_token_days)
        await self.tokens.add(
            AuthRefreshToken(
                user_id=user.id,
                family_id=family_id,
                token_hash=hash_token(refresh_token),
                expires_at=expires_at,
                user_agent=(client.user_agent or "")[:300] or None,
                ip_address=client.ip_address,
            )
        )
        return Session(
            user=user,
            access_token=access_token,
            expires_in=expires_in,
            refresh_token=refresh_token,
            refresh_expires_at=expires_at,
        )

    def _audit(self, action: str, user: User, client: ClientInfo) -> None:
        self.audit_entry(action, user.id, client)

    def audit_entry(
        self,
        action: str,
        user_id: uuid.UUID,
        client: ClientInfo,
        data: dict[str, str] | None = None,
    ) -> None:
        self.session.add(
            AuditLog(
                user_id=user_id,
                actor_type=ActorType.USER,
                action=action,
                entity_type="user",
                entity_id=user_id,
                data=data,
                ip_address=client.ip_address,
            )
        )
