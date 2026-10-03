from typing import Annotated
from urllib.parse import urlencode

import structlog
from fastapi import APIRouter, Query, Request, status
from fastapi.responses import RedirectResponse

from app.api.deps import ApprovedUser, DbSession
from app.core.errors import AppError
from app.schemas.outreach import GmailConnectRead, GmailStatusRead
from app.services.gmail_account import GmailAccountService, finish_connect, start_connect

logger = structlog.get_logger("app.gmail")

router = APIRouter(prefix="/integrations/gmail", tags=["gmail"])


@router.get("", response_model=GmailStatusRead, summary="Is Gmail connected?")
async def gmail_status(request: Request, db: DbSession, user: ApprovedUser) -> GmailStatusRead:
    found = await GmailAccountService(db, user.id, request.app.state.settings).status()
    return GmailStatusRead(
        configured=found.configured,
        connected=found.connected,
        status=found.status.value if found.status else None,
        account_email=found.account_email,
        can_send=found.can_send,
        can_read=found.can_read,
        connected_at=found.connected_at,
    )


@router.post("/connect", response_model=GmailConnectRead, summary="Start the Google consent")
async def gmail_connect(request: Request, user: ApprovedUser) -> GmailConnectRead:
    state = request.app.state
    return GmailConnectRead(auth_url=await start_connect(state.settings, state.redis, user.id))


@router.get(
    "/callback",
    response_class=RedirectResponse,
    status_code=status.HTTP_302_FOUND,
    summary="Google redirects here after consent (no login: the signed state names the user)",
)
async def gmail_callback(
    request: Request,
    db: DbSession,
    code: Annotated[str | None, Query(max_length=2000)] = None,
    state: Annotated[str | None, Query(max_length=4000)] = None,
    error: Annotated[str | None, Query(max_length=200)] = None,
) -> RedirectResponse:
    settings = request.app.state.settings
    target = settings.frontend_url.rstrip("/") + "/settings?"
    if error or not code or not state:
        message = "Gmail was not connected (consent was cancelled)."
        return RedirectResponse(target + urlencode({"gmail": "error", "message": message}), 302)
    try:
        account = await finish_connect(
            db, settings, request.app.state.redis, code=code, state=state
        )
    except AppError as exc:
        logger.warning("gmail.connect_failed", code=exc.code)
        return RedirectResponse(target + urlencode({"gmail": "error", "message": exc.message}), 302)
    return RedirectResponse(
        target + urlencode({"gmail": "connected", "account": account.account_email}), 302
    )


@router.delete("", status_code=status.HTTP_204_NO_CONTENT, summary="Disconnect Gmail")
async def gmail_disconnect(request: Request, db: DbSession, user: ApprovedUser) -> None:
    await GmailAccountService(db, user.id, request.app.state.settings).disconnect()
