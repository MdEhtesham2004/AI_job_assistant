import structlog
from fastapi import APIRouter, Request, Response, status

from app.api.deps import ClientDep, CurrentUser, DbSession, RateLimiterDep, SettingsDep
from app.core.config import Settings
from app.schemas.auth import (
    ChangePasswordRequest,
    ForgotPasswordRequest,
    LoginRequest,
    MessageResponse,
    RegisterRequest,
    ResetPasswordRequest,
    SessionResponse,
    UserRead,
)
from app.services.auth import AuthService, ClientInfo, Session

router = APIRouter(prefix="/auth", tags=["auth"])
logger = structlog.get_logger("app.auth")

FORGOT_PASSWORD_MESSAGE = "If an account exists for this email, a reset link has been sent."


def _cookie_path(settings: Settings) -> str:
    return f"{settings.api_prefix}/auth"


def _session_response(response: Response, session: Session, settings: Settings) -> SessionResponse:
    response.set_cookie(
        key=settings.refresh_cookie_name,
        value=session.refresh_token,
        max_age=settings.refresh_token_days * 24 * 3600,
        path=_cookie_path(settings),
        httponly=True,
        secure=settings.refresh_cookie_secure,
        samesite="strict",
    )
    return SessionResponse(
        access_token=session.access_token,
        expires_in=session.expires_in,
        user=UserRead.model_validate(session.user),
    )


def _client_key(client: ClientInfo, action: str) -> str:
    return f"{action}:{client.ip_address or 'unknown'}"


@router.post(
    "/register",
    response_model=SessionResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create an account (starts as pending until an admin approves it)",
)
async def register(
    body: RegisterRequest,
    response: Response,
    db: DbSession,
    settings: SettingsDep,
    client: ClientDep,
    limiter: RateLimiterDep,
) -> SessionResponse:
    limiter.check(_client_key(client, "register"), limit=5, window_seconds=300)
    session = await AuthService(db, settings).register(
        email=body.email, full_name=body.full_name, password=body.password, client=client
    )
    return _session_response(response, session, settings)


@router.post("/login", response_model=SessionResponse, summary="Sign in")
async def login(
    body: LoginRequest,
    response: Response,
    db: DbSession,
    settings: SettingsDep,
    client: ClientDep,
    limiter: RateLimiterDep,
) -> SessionResponse:
    limiter.check(_client_key(client, "login"), limit=10, window_seconds=60)
    session = await AuthService(db, settings).login(
        email=body.email, password=body.password, client=client
    )
    return _session_response(response, session, settings)


@router.post(
    "/refresh",
    response_model=SessionResponse,
    summary="Exchange the refresh cookie for a new access token (rotates the cookie)",
)
async def refresh(
    request: Request,
    response: Response,
    db: DbSession,
    settings: SettingsDep,
    client: ClientDep,
    limiter: RateLimiterDep,
) -> SessionResponse:
    limiter.check(_client_key(client, "refresh"), limit=60, window_seconds=60)
    raw_token = request.cookies.get(settings.refresh_cookie_name)
    session = await AuthService(db, settings).refresh(raw_token, client)
    return _session_response(response, session, settings)


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT, summary="Sign out")
async def logout(
    request: Request,
    response: Response,
    db: DbSession,
    settings: SettingsDep,
    client: ClientDep,
) -> Response:
    await AuthService(db, settings).logout(
        request.cookies.get(settings.refresh_cookie_name), client
    )
    response.status_code = status.HTTP_204_NO_CONTENT
    response.delete_cookie(
        settings.refresh_cookie_name,
        path=_cookie_path(settings),
        httponly=True,
        secure=settings.refresh_cookie_secure,
        samesite="strict",
    )
    return response


@router.post(
    "/change-password",
    response_model=SessionResponse,
    summary="Change password (signs out all other devices)",
)
async def change_password(
    body: ChangePasswordRequest,
    response: Response,
    user: CurrentUser,
    db: DbSession,
    settings: SettingsDep,
    client: ClientDep,
) -> SessionResponse:
    session = await AuthService(db, settings).change_password(
        user,
        current_password=body.current_password,
        new_password=body.new_password,
        client=client,
    )
    return _session_response(response, session, settings)


@router.post(
    "/forgot-password",
    response_model=MessageResponse,
    status_code=status.HTTP_202_ACCEPTED,
    summary="Request a password-reset link (email delivery arrives in Phase 12)",
)
async def forgot_password(
    body: ForgotPasswordRequest,
    db: DbSession,
    settings: SettingsDep,
    client: ClientDep,
    limiter: RateLimiterDep,
) -> MessageResponse:
    limiter.check(_client_key(client, "forgot"), limit=5, window_seconds=300)
    token = await AuthService(db, settings).request_password_reset(body.email, client)
    if token and settings.app_env == "development":
        # No mail sender yet (Phase 12). Development only: show the token in the server log.
        logger.info("auth.password_reset_token_dev_only", reset_token=token)
    return MessageResponse(message=FORGOT_PASSWORD_MESSAGE)


@router.post("/reset-password", response_model=MessageResponse, summary="Set a new password")
async def reset_password(
    body: ResetPasswordRequest,
    db: DbSession,
    settings: SettingsDep,
    client: ClientDep,
    limiter: RateLimiterDep,
) -> MessageResponse:
    limiter.check(_client_key(client, "reset"), limit=10, window_seconds=300)
    await AuthService(db, settings).reset_password(body.token, body.new_password, client)
    return MessageResponse(message="Your password has been changed. Please sign in.")
