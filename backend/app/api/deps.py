import ipaddress
from collections.abc import AsyncIterator
from typing import Annotated

from fastapi import Depends, Request
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession

from app.core.config import Settings
from app.core.errors import AuthenticationError, PermissionDeniedError
from app.core.rate_limit import SlidingWindowRateLimiter
from app.core.security import InvalidTokenError, decode_access_token
from app.db.session import session_scope
from app.models.accounts import User
from app.models.enums import ApprovalStatus, UserRole
from app.repositories.users import UserRepository
from app.services.auth import ClientInfo, ensure_can_sign_in


def get_app_settings(request: Request) -> Settings:
    """Settings the running app was created with (overridable per app instance in tests)."""
    settings: Settings = request.app.state.settings
    return settings


def get_engine(request: Request) -> AsyncEngine:
    engine: AsyncEngine = request.app.state.engine
    return engine


async def get_db(request: Request) -> AsyncIterator[AsyncSession]:
    """One database session per request (Phase 1 §2.6 unit of work)."""
    async for session in session_scope(request.app.state.session_factory):
        yield session


def get_rate_limiter(request: Request) -> SlidingWindowRateLimiter:
    limiter: SlidingWindowRateLimiter = request.app.state.rate_limiter
    return limiter


def get_client_info(request: Request) -> ClientInfo:
    host = request.client.host if request.client else None
    try:
        ip = str(ipaddress.ip_address(host)) if host else None
    except ValueError:
        ip = None
    return ClientInfo(ip_address=ip, user_agent=request.headers.get("user-agent"))


SettingsDep = Annotated[Settings, Depends(get_app_settings)]
EngineDep = Annotated[AsyncEngine, Depends(get_engine)]
DbSession = Annotated[AsyncSession, Depends(get_db)]
RateLimiterDep = Annotated[SlidingWindowRateLimiter, Depends(get_rate_limiter)]
ClientDep = Annotated[ClientInfo, Depends(get_client_info)]

_bearer = HTTPBearer(auto_error=False)


async def get_current_user(
    db: DbSession,
    settings: SettingsDep,
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(_bearer)],
) -> User:
    """Any signed-in user, including accounts still waiting for approval."""
    if credentials is None:
        raise AuthenticationError()
    try:
        user_id = decode_access_token(credentials.credentials, settings.secret_key)
    except InvalidTokenError as exc:
        if exc.expired:
            raise AuthenticationError("Your session has expired.", code="TOKEN_EXPIRED") from exc
        raise AuthenticationError("Invalid access token.", code="INVALID_TOKEN") from exc

    user = await UserRepository(db).get(user_id)
    if user is None:
        raise AuthenticationError("Invalid access token.", code="INVALID_TOKEN")
    ensure_can_sign_in(user)  # deactivated/rejected accounts lose access immediately
    return user


CurrentUser = Annotated[User, Depends(get_current_user)]


async def require_approved_user(user: CurrentUser) -> User:
    """Feature routes: the account must be approved by an admin."""
    if user.approval_status is not ApprovalStatus.APPROVED:
        raise PermissionDeniedError(
            "Your account is waiting for admin approval.", code="ACCOUNT_PENDING"
        )
    return user


ApprovedUser = Annotated[User, Depends(require_approved_user)]


async def require_admin(user: ApprovedUser) -> User:
    if user.role is not UserRole.ADMIN:
        # Phase 1 §3.4 error table: 403 ADMIN_REQUIRED (the UI shows its 404 page).
        raise PermissionDeniedError("Administrator access required.", code="ADMIN_REQUIRED")
    return user


AdminUser = Annotated[User, Depends(require_admin)]
