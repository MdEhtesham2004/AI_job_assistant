"""Connect / disconnect the user's Gmail and hand out fresh access tokens (Module 08).

Tokens are encrypted before they reach the database. The OAuth `state` is a signed,
short-lived token carrying the user id and a one-time nonce kept in Redis.
"""

import secrets
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime

from redis.asyncio import Redis
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings
from app.core.crypto import TokenCipher
from app.core.errors import AppError, ValidationAppError
from app.core.security import InvalidTokenError, create_oauth_state, decode_oauth_state
from app.integrations.gmail import (
    SCOPES,
    SEND_SCOPE,
    GmailApi,
    GmailAuthError,
    GoogleOAuth,
    TokenSet,
)
from app.models.enums import OAuthStatus
from app.models.outreach import OAuthAccount
from app.repositories.outreach import GOOGLE, OAuthAccountRepository
from app.services.notifications import notify

NONCE_PREFIX = "oauth:gmail:nonce:"
NONCE_TTL = 600


class GmailNotConnectedError(AppError):
    status_code = 409
    code = "GMAIL_NOT_CONNECTED"
    message = "Connect Gmail in Settings first."


@dataclass(frozen=True)
class GmailStatus:
    configured: bool
    connected: bool
    status: OAuthStatus | None = None
    account_email: str | None = None
    can_send: bool = False
    can_read: bool = False
    connected_at: datetime | None = None


async def start_connect(settings: Settings, redis: Redis, user_id: uuid.UUID) -> str:
    """The Google consent URL for this user."""
    oauth = GoogleOAuth(settings)
    nonce = secrets.token_urlsafe(24)
    await redis.set(NONCE_PREFIX + nonce, str(user_id), ex=NONCE_TTL)
    return oauth.authorize_url(create_oauth_state(user_id, nonce, settings.secret_key))


async def finish_connect(
    session: AsyncSession, settings: Settings, redis: Redis, *, code: str, state: str
) -> OAuthAccount:
    """Google redirected back: check the state, swap the code for tokens, store them."""
    try:
        user_id, nonce = decode_oauth_state(state, settings.secret_key)
    except InvalidTokenError as exc:
        raise ValidationAppError("The Gmail connection link expired. Try again.") from exc
    # One-time: a replayed callback finds no nonce.
    owner = await redis.getdel(NONCE_PREFIX + nonce)
    if owner is None or (owner.decode() if isinstance(owner, bytes) else owner) != str(user_id):
        raise ValidationAppError("The Gmail connection link was already used. Try again.")

    oauth = GoogleOAuth(settings)
    tokens = await oauth.exchange_code(code)
    if SEND_SCOPE not in tokens.scopes:
        await oauth.revoke(tokens.access_token)
        raise ValidationAppError(
            "Permission to send email was not granted. Connect again and tick "
            "'Send email on your behalf'.",
            code="GMAIL_SCOPE_MISSING",
        )
    email = await GmailApi(settings, tokens.access_token).profile_email()
    cipher = TokenCipher.from_settings(settings)
    accounts = OAuthAccountRepository(session, owner_id=user_id)
    account = await accounts.google(for_update=True)
    if account is None:
        account = await accounts.add(
            OAuthAccount(
                provider=GOOGLE,
                account_email=email,
                access_token_enc=cipher.encrypt(tokens.access_token),
                refresh_token_enc=cipher.encrypt(tokens.refresh_token)
                if tokens.refresh_token
                else None,
                scopes=tokens.scopes,
                expires_at=tokens.expires_at,
                status=OAuthStatus.CONNECTED,
            )
        )
    else:
        _store(account, tokens, cipher)
        account.account_email = email
        account.status = OAuthStatus.CONNECTED
        account.created_at = datetime.now(UTC)  # "connected since"
    notify(
        session,
        user_id,
        type="gmail_connected",
        title=f"Gmail connected: {email}",
        link="/settings",
    )
    await session.commit()
    return account


def _store(account: OAuthAccount, tokens: TokenSet, cipher: TokenCipher) -> None:
    account.access_token_enc = cipher.encrypt(tokens.access_token)
    if tokens.refresh_token:
        account.refresh_token_enc = cipher.encrypt(tokens.refresh_token)
    account.expires_at = tokens.expires_at
    if tokens.scopes:
        account.scopes = tokens.scopes


class GmailAccountService:
    def __init__(self, session: AsyncSession, user_id: uuid.UUID, settings: Settings) -> None:
        self.session = session
        self.user_id = user_id
        self.settings = settings
        self.accounts = OAuthAccountRepository(session, owner_id=user_id)

    async def status(self) -> GmailStatus:
        account = await self.accounts.google()
        if account is None:
            return GmailStatus(configured=self.settings.gmail_configured, connected=False)
        return GmailStatus(
            configured=self.settings.gmail_configured,
            connected=account.status is OAuthStatus.CONNECTED,
            status=account.status,
            account_email=account.account_email,
            can_send=SEND_SCOPE in account.scopes,
            can_read=SCOPES[1] in account.scopes,
            connected_at=account.created_at,
        )

    async def disconnect(self) -> None:
        account = await self.accounts.google()
        if account is None:
            return
        if self.settings.gmail_configured:
            try:
                cipher = TokenCipher.from_settings(self.settings)
                token = (
                    cipher.decrypt(account.refresh_token_enc)
                    if account.refresh_token_enc
                    else cipher.decrypt(account.access_token_enc)
                )
                await GoogleOAuth(self.settings).revoke(token)
            except AppError:
                pass  # disconnecting locally still works
        await self.session.delete(account)
        await self.session.commit()

    async def connected(self) -> OAuthAccount:
        account = await self.accounts.google()
        if account is None or account.status is not OAuthStatus.CONNECTED:
            raise GmailNotConnectedError()
        return account

    async def api(self) -> tuple[GmailApi, OAuthAccount]:
        """A Gmail client with a fresh access token (refreshed and saved when needed)."""
        account = await self.connected()
        cipher = TokenCipher.from_settings(self.settings)
        if account.expires_at is None or account.expires_at <= datetime.now(UTC):
            if account.refresh_token_enc is None:
                await self._mark(account, OAuthStatus.EXPIRED)
                raise GmailAuthError()
            try:
                tokens = await GoogleOAuth(self.settings).refresh(
                    cipher.decrypt(account.refresh_token_enc)
                )
            except GmailAuthError:
                await self._mark(account, OAuthStatus.REVOKED)
                raise
            _store(account, tokens, cipher)
            await self.session.commit()
        return GmailApi(self.settings, cipher.decrypt(account.access_token_enc)), account

    async def mark_revoked(self) -> None:
        account = await self.accounts.google()
        if account is not None:
            await self._mark(account, OAuthStatus.REVOKED)

    async def _mark(self, account: OAuthAccount, status: OAuthStatus) -> None:
        account.status = status
        notify(
            self.session,
            self.user_id,
            type="gmail_disconnected",
            title="Gmail needs to be reconnected",
            body="Google no longer accepts the saved access. Emails wait until you reconnect.",
            link="/settings",
        )
        await self.session.commit()
