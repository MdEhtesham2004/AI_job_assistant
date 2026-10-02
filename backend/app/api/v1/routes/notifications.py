import uuid
from typing import Annotated

from fastapi import APIRouter, Query, status

from app.api.deps import ApprovedUser, DbSession
from app.schemas.common import Page
from app.schemas.tasks import NotificationRead, UnreadCount
from app.services.notifications import NotificationService

router = APIRouter(prefix="/notifications", tags=["notifications"])


@router.get("", response_model=Page[NotificationRead], summary="Your notifications, newest first")
async def list_notifications(
    db: DbSession,
    user: ApprovedUser,
    unread_only: bool = False,
    page: Annotated[int, Query(ge=1)] = 1,
    page_size: Annotated[int, Query(ge=1, le=50)] = 10,
) -> Page[NotificationRead]:
    items, total = await NotificationService(db, user.id).list(
        unread_only=unread_only, page=page, page_size=page_size
    )
    return Page(
        items=[NotificationRead.model_validate(n) for n in items],
        total=total,
        page=page,
        page_size=page_size,
    )


@router.get("/unread-count", response_model=UnreadCount, summary="Badge counter")
async def unread_count(db: DbSession, user: ApprovedUser) -> UnreadCount:
    return UnreadCount(unread=await NotificationService(db, user.id).unread_count())


@router.post("/{notification_id}/read", response_model=NotificationRead, summary="Mark as read")
async def mark_read(
    notification_id: uuid.UUID, db: DbSession, user: ApprovedUser
) -> NotificationRead:
    notification = await NotificationService(db, user.id).mark_read(notification_id)
    return NotificationRead.model_validate(notification)


@router.post("/read-all", status_code=status.HTTP_204_NO_CONTENT, summary="Mark all as read")
async def mark_all_read(db: DbSession, user: ApprovedUser) -> None:
    await NotificationService(db, user.id).mark_all_read()
