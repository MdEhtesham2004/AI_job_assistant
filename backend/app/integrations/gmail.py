"""Google OAuth + Gmail REST API (Module 08). Plain httpx — no Google SDK needed.

Scopes: gmail.send (send applications) and gmail.readonly (Phase 13 reads replies; also
used to find a sent message again after a crash).
"""

import base64
import contextlib
import html as htmllib
import json
import re
import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from email.utils import parseaddr
from typing import Any
from urllib.parse import urlencode

import httpx
import structlog

from app.core.config import Settings
from app.core.errors import AppError, ExternalServiceError

logger = structlog.get_logger("app.gmail")

AUTH_URL = "https://accounts.google.com/o/oauth2/v2/auth"
SEND_SCOPE = "https://www.googleapis.com/auth/gmail.send"
READ_SCOPE = "https://www.googleapis.com/auth/gmail.readonly"
SCOPES = (SEND_SCOPE, READ_SCOPE)
TIMEOUT = 30.0


class GmailNotConfiguredError(AppError):
    status_code = 503
    code = "GMAIL_NOT_CONFIGURED"
    message = (
        "Gmail is not configured on the server (GOOGLE_CLIENT_ID, GOOGLE_CLIENT_SECRET, "
        "TOKEN_ENCRYPTION_KEY)."
    )


class GmailAuthError(AppError):
    """The grant is gone (revoked, expired refresh token): the user must reconnect."""

    status_code = 409
    code = "GMAIL_RECONNECT"
    message = "Gmail access was revoked or expired. Reconnect Gmail in Settings."


class GmailSendError(AppError):
    """Gmail answered and refused the message — it was certainly not sent."""

    status_code = 502
    code = "GMAIL_SEND_FAILED"


class GmailUncertainError(ExternalServiceError):
    """No answer from Gmail (timeout, network): the message may or may not have gone out."""

    code = "GMAIL_UNCERTAIN"


@dataclass(frozen=True)
class TokenSet:
    access_token: str
    refresh_token: str | None
    expires_at: datetime
    scopes: list[str]


@dataclass(frozen=True)
class SentMessage:
    message_id: str
    thread_id: str


class HistoryExpiredError(AppError):
    """Gmail no longer knows the stored history id: fall back to reading the threads."""

    code = "GMAIL_HISTORY_EXPIRED"


@dataclass(frozen=True)
class MessageRef:
    message_id: str
    thread_id: str
    label_ids: tuple[str, ...] = ()


@dataclass(frozen=True)
class GmailMessage:
    message_id: str
    thread_id: str
    label_ids: tuple[str, ...]
    from_address: str
    from_name: str | None
    to_address: str
    subject: str
    rfc822_message_id: str | None
    received_at: datetime | None
    text: str
    headers: dict[str, str] = field(default_factory=dict)


def _b64(data: str) -> bytes:
    return base64.urlsafe_b64decode(data + "=" * (-len(data) % 4))


def _body_text(payload: dict[str, Any]) -> str:
    """Plain text of a message: the text/plain part, else text/html without tags."""
    plain: list[str] = []
    html: list[str] = []

    def walk(part: dict[str, Any]) -> None:
        mime = str(part.get("mimeType", ""))
        data = (part.get("body") or {}).get("data")
        if data and mime == "text/plain":
            plain.append(_b64(data).decode("utf-8", errors="replace"))
        elif data and mime == "text/html":
            html.append(_b64(data).decode("utf-8", errors="replace"))
        for child in part.get("parts") or []:
            walk(child)

    walk(payload)
    if plain:
        return "\n".join(plain).strip()
    text = re.sub(r"<(script|style)[^>]*>.*?</\1>", " ", "\n".join(html), flags=re.S | re.I)
    text = re.sub(r"<br\s*/?>|</p>|</div>", "\n", text, flags=re.I)
    return htmllib.unescape(re.sub(r"<[^>]+>", " ", text)).strip()


def parse_message(body: dict[str, Any]) -> GmailMessage:
    payload = body.get("payload") or {}
    headers = {
        str(h.get("name", "")).lower(): str(h.get("value", ""))
        for h in payload.get("headers") or []
    }
    name, address = parseaddr(headers.get("from", ""))
    _, to = parseaddr(headers.get("to", ""))
    received: datetime | None = None
    if body.get("internalDate"):
        received = datetime.fromtimestamp(int(body["internalDate"]) / 1000, tz=UTC)
    return GmailMessage(
        message_id=str(body.get("id", "")),
        thread_id=str(body.get("threadId", "")),
        label_ids=tuple(body.get("labelIds") or ()),
        from_address=address.lower(),
        from_name=name or None,
        to_address=to.lower(),
        subject=headers.get("subject", ""),
        rfc822_message_id=headers.get("message-id"),
        received_at=received,
        text=_body_text(payload)[:20_000],
        headers=headers,
    )


def _tokens(body: dict[str, Any], now: datetime) -> TokenSet:
    return TokenSet(
        access_token=str(body["access_token"]),
        refresh_token=body.get("refresh_token"),
        expires_at=now + timedelta(seconds=int(body.get("expires_in", 3600)) - 60),
        scopes=str(body.get("scope", "")).split(),
    )


class GoogleOAuth:
    def __init__(self, settings: Settings) -> None:
        if not settings.gmail_configured:
            raise GmailNotConfiguredError()
        self.settings = settings

    def authorize_url(self, state: str) -> str:
        params = {
            "client_id": self.settings.google_client_id,
            "redirect_uri": self.settings.google_redirect_uri,
            "response_type": "code",
            "scope": " ".join(SCOPES),
            "access_type": "offline",  # we need a refresh token
            "prompt": "consent",  # … every time, even on reconnect
            # No: it would bundle unrelated earlier grants of this Google project (seen live:
            # Drive scopes came along). We ask for exactly the two Gmail scopes.
            "include_granted_scopes": "false",
            "state": state,
        }
        return f"{AUTH_URL}?{urlencode(params)}"

    async def _token_request(self, data: dict[str, str]) -> dict[str, Any]:
        url = self.settings.google_oauth_url.rstrip("/") + "/token"
        try:
            async with httpx.AsyncClient(timeout=TIMEOUT) as client:
                response = await client.post(
                    url,
                    data={
                        "client_id": self.settings.google_client_id,
                        "client_secret": self.settings.google_client_secret,
                        **data,
                    },
                )
        except httpx.HTTPError as exc:
            raise ExternalServiceError("Google is unreachable.") from exc
        body: dict[str, Any] = response.json() if response.content else {}
        if response.status_code == 400 and body.get("error") in (
            "invalid_grant",
            "unauthorized_client",
        ):
            raise GmailAuthError()
        if response.status_code != 200:
            raise ExternalServiceError(
                "Google rejected the token request.",
                details={"status": response.status_code, "error": body.get("error")},
            )
        return body

    async def exchange_code(self, code: str) -> TokenSet:
        body = await self._token_request(
            {
                "code": code,
                "grant_type": "authorization_code",
                "redirect_uri": self.settings.google_redirect_uri,
            }
        )
        return _tokens(body, datetime.now(UTC))

    async def refresh(self, refresh_token: str) -> TokenSet:
        body = await self._token_request(
            {"refresh_token": refresh_token, "grant_type": "refresh_token"}
        )
        tokens = _tokens(body, datetime.now(UTC))
        # Google usually does not send a new refresh token: keep the old one.
        return TokenSet(
            tokens.access_token,
            tokens.refresh_token or refresh_token,
            tokens.expires_at,
            tokens.scopes,
        )

    async def revoke(self, token: str) -> None:
        """Best effort: disconnecting must work even if Google is down."""
        url = self.settings.google_oauth_url.rstrip("/") + "/revoke"
        try:
            async with httpx.AsyncClient(timeout=TIMEOUT) as client:
                await client.post(url, data={"token": token})
        except httpx.HTTPError:
            logger.warning("gmail.revoke_failed")


class GmailApi:
    """Calls for one connected account (`access_token` must be fresh)."""

    def __init__(self, settings: Settings, access_token: str) -> None:
        self.base = settings.gmail_api_url.rstrip("/")
        self.headers = {"Authorization": f"Bearer {access_token}"}

    async def _get(self, path: str, params: dict[str, str] | None = None) -> dict[str, Any]:
        try:
            async with httpx.AsyncClient(timeout=TIMEOUT) as client:
                response = await client.get(self.base + path, params=params, headers=self.headers)
        except httpx.HTTPError as exc:
            raise ExternalServiceError("Gmail is unreachable.") from exc
        if response.status_code == 401:
            raise GmailAuthError()
        if response.status_code != 200:
            raise ExternalServiceError(
                "Gmail returned an error.", details={"status": response.status_code}
            )
        body: dict[str, Any] = response.json()
        return body

    async def profile_email(self) -> str:
        return str((await self._get("/gmail/v1/users/me/profile"))["emailAddress"])

    async def find_sent(
        self, *, to_address: str, header: str, value: str, after: datetime
    ) -> SentMessage | None:
        """Find a message we sent by our own header (reconciliation).

        Gmail replaces the Message-ID we set (seen live), but keeps custom headers — so we
        list recent sent mail to the recipient and compare `X-App-Idempotency-Key`.
        """
        body = await self._get(
            "/gmail/v1/users/me/messages",
            {"q": f"in:sent to:{to_address} after:{int(after.timestamp())}", "maxResults": "20"},
        )
        for item in body.get("messages") or []:
            message = await self._get(
                f"/gmail/v1/users/me/messages/{item['id']}",
                {"format": "metadata", "metadataHeaders": header},
            )
            headers = message.get("payload", {}).get("headers", [])
            if any(
                h.get("name", "").lower() == header.lower() and h.get("value") == value
                for h in headers
            ):
                return SentMessage(str(item["id"]), str(item["threadId"]))
        return None

    # ---------- reading (Phase 13) ----------

    async def profile(self) -> tuple[str, str]:
        """(address, current historyId)."""
        body = await self._get("/gmail/v1/users/me/profile")
        return str(body["emailAddress"]), str(body["historyId"])

    async def history(self, start_history_id: str) -> tuple[list[MessageRef], str]:
        """Messages added since `start_history_id` and the newest history id.

        Raises HistoryExpiredError when Gmail no longer has that point (about a week).
        """
        refs: list[MessageRef] = []
        newest = start_history_id
        page_token: str | None = None
        for _ in range(20):  # at most 20 pages per poll
            params = {
                "startHistoryId": start_history_id,
                "historyTypes": "messageAdded",
                "maxResults": "500",
            }
            if page_token:
                params["pageToken"] = page_token
            try:
                body = await self._get("/gmail/v1/users/me/history", params)
            except ExternalServiceError as exc:
                if exc.details.get("status") == 404:
                    raise HistoryExpiredError() from exc
                raise
            newest = str(body.get("historyId") or newest)
            for entry in body.get("history") or []:
                for added in entry.get("messagesAdded") or []:
                    message = added.get("message") or {}
                    if message.get("id"):
                        refs.append(
                            MessageRef(
                                str(message["id"]),
                                str(message.get("threadId", "")),
                                tuple(message.get("labelIds") or ()),
                            )
                        )
            page_token = body.get("nextPageToken")
            if not page_token:
                break
        return refs, newest

    async def thread_refs(self, thread_id: str) -> list[MessageRef]:
        body = await self._get(f"/gmail/v1/users/me/threads/{thread_id}", {"format": "minimal"})
        return [
            MessageRef(
                str(m["id"]), str(m.get("threadId", thread_id)), tuple(m.get("labelIds") or ())
            )
            for m in body.get("messages") or []
        ]

    async def message(self, message_id: str) -> GmailMessage:
        body = await self._get(f"/gmail/v1/users/me/messages/{message_id}", {"format": "full"})
        return parse_message(body)

    async def header(self, message_id: str, name: str) -> str | None:
        body = await self._get(
            f"/gmail/v1/users/me/messages/{message_id}",
            {"format": "metadata", "metadataHeaders": name},
        )
        for item in body.get("payload", {}).get("headers", []):
            if item.get("name", "").lower() == name.lower():
                return str(item.get("value"))
        return None

    # ---------- sending ----------

    async def send(self, mime: bytes, *, thread_id: str | None = None) -> SentMessage:
        """Upload endpoint: the raw MIME message (attachments up to 35 MB).

        With `thread_id` (follow-ups) a multipart upload carries the thread as metadata.
        """
        url = self.base + "/upload/gmail/v1/users/me/messages/send"
        if thread_id:
            boundary = f"gmail-{uuid.uuid4().hex}"
            content = (
                (
                    f"--{boundary}\r\nContent-Type: application/json; charset=UTF-8\r\n\r\n"
                    f"{json.dumps({'threadId': thread_id})}\r\n"
                    f"--{boundary}\r\nContent-Type: message/rfc822\r\n\r\n"
                ).encode()
                + mime
                + f"\r\n--{boundary}--".encode()
            )
            params = {"uploadType": "multipart"}
            content_type = f"multipart/related; boundary={boundary}"
        else:
            content, params, content_type = mime, {"uploadType": "media"}, "message/rfc822"
        try:
            async with httpx.AsyncClient(timeout=60.0) as client:
                response = await client.post(
                    url,
                    params=params,
                    content=content,
                    headers={**self.headers, "Content-Type": content_type},
                )
        except httpx.HTTPError as exc:
            # The request may have reached Gmail: reconciliation decides later.
            raise GmailUncertainError("Gmail did not answer.") from exc
        if response.status_code == 401:
            raise GmailAuthError()
        if response.status_code >= 500:
            raise GmailUncertainError(
                "Gmail had an internal error.", details={"status": response.status_code}
            )
        if response.status_code != 200:
            reason = ""
            with contextlib.suppress(ValueError):
                reason = str(response.json().get("error", {}).get("message", ""))
            raise GmailSendError(
                f"Gmail refused the email{': ' + reason if reason else '.'}",
                details={"status": response.status_code},
            )
        body = response.json()
        return SentMessage(str(body["id"]), str(body["threadId"]))
