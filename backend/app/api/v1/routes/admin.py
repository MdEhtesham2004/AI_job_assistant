import uuid
from collections.abc import Sequence
from typing import Annotated

from fastapi import APIRouter, Query
from sqlalchemy import select

from app.api.deps import AdminUser, DbSession
from app.models.accounts import User, UserSettings
from app.models.enums import ActorType
from app.models.system import AuditLog
from app.repositories.profiles import UserSettingsRepository
from app.repositories.users import UserFilter
from app.schemas.admin import (
    AdminUserRead,
    PermissionsUpdate,
    RejectRequest,
    RoleUpdate,
    UserStatusCounts,
)
from app.schemas.common import Page
from app.services.user_admin import UserAdminService

router = APIRouter(prefix="/admin/users", tags=["admin"])


async def _read(db: DbSession, users: Sequence[User]) -> list[AdminUserRead]:
    """Users plus their admin-controlled permissions (kept in user_settings)."""
    ids = [u.id for u in users]
    allowed = set(
        (
            await db.scalars(
                select(UserSettings.user_id).where(
                    UserSettings.user_id.in_(ids), UserSettings.linkedin_schedule_allowed.is_(True)
                )
            )
        ).all()
    )
    return [
        AdminUserRead.model_validate(u).model_copy(
            update={"linkedin_schedule_allowed": u.id in allowed}
        )
        for u in users
    ]


async def _one(db: DbSession, user: User) -> AdminUserRead:
    return (await _read(db, [user]))[0]


@router.get("", response_model=Page[AdminUserRead], summary="List accounts (pending first)")
async def list_users(
    admin: AdminUser,
    db: DbSession,
    status: UserFilter = UserFilter.ALL,
    q: Annotated[str | None, Query(max_length=100)] = None,
    page: Annotated[int, Query(ge=1)] = 1,
    page_size: Annotated[int, Query(ge=1, le=100)] = 20,
) -> Page[AdminUserRead]:
    users, total = await UserAdminService(db, admin).list_users(
        status=status, query=q, page=page, page_size=page_size
    )
    return Page(items=await _read(db, users), total=total, page=page, page_size=page_size)


@router.get("/counts", response_model=UserStatusCounts, summary="Number of accounts per status")
async def user_counts(admin: AdminUser, db: DbSession) -> UserStatusCounts:
    return UserStatusCounts(**await UserAdminService(db, admin).status_counts())


@router.get("/{user_id}", response_model=AdminUserRead, summary="One account")
async def get_user(user_id: uuid.UUID, admin: AdminUser, db: DbSession) -> AdminUserRead:
    return await _one(db, await UserAdminService(db, admin).get_user(user_id))


@router.post("/{user_id}/approve", response_model=AdminUserRead, summary="Approve a sign-up")
async def approve(user_id: uuid.UUID, admin: AdminUser, db: DbSession) -> AdminUserRead:
    return await _one(db, await UserAdminService(db, admin).approve(user_id))


@router.post("/{user_id}/reject", response_model=AdminUserRead, summary="Reject a sign-up")
async def reject(
    user_id: uuid.UUID, body: RejectRequest, admin: AdminUser, db: DbSession
) -> AdminUserRead:
    return await _one(db, await UserAdminService(db, admin).reject(user_id, body.reason))


@router.post("/{user_id}/deactivate", response_model=AdminUserRead, summary="Deactivate")
async def deactivate(user_id: uuid.UUID, admin: AdminUser, db: DbSession) -> AdminUserRead:
    return await _one(db, await UserAdminService(db, admin).deactivate(user_id))


@router.post("/{user_id}/reactivate", response_model=AdminUserRead, summary="Reactivate")
async def reactivate(user_id: uuid.UUID, admin: AdminUser, db: DbSession) -> AdminUserRead:
    return await _one(db, await UserAdminService(db, admin).reactivate(user_id))


@router.patch("/{user_id}/role", response_model=AdminUserRead, summary="Change role")
async def change_role(
    user_id: uuid.UUID, body: RoleUpdate, admin: AdminUser, db: DbSession
) -> AdminUserRead:
    return await _one(db, await UserAdminService(db, admin).change_role(user_id, body.role))


@router.patch(
    "/{user_id}/permissions",
    response_model=AdminUserRead,
    summary="Per-user features (Phase 19: scheduled recruiter-email searches)",
)
async def change_permissions(
    user_id: uuid.UUID, body: PermissionsUpdate, admin: AdminUser, db: DbSession
) -> AdminUserRead:
    user = await UserAdminService(db, admin).get_user(user_id)
    settings = await UserSettingsRepository(db, owner_id=user.id).get_or_create()
    if settings.linkedin_schedule_allowed != body.linkedin_schedule_allowed:
        settings.linkedin_schedule_allowed = body.linkedin_schedule_allowed
        db.add(
            AuditLog(
                user_id=admin.id,
                actor_type=ActorType.ADMIN,
                action="user.permissions",
                entity_type="user",
                entity_id=user.id,
                data={"linkedin_schedule_allowed": body.linkedin_schedule_allowed},
            )
        )
        await db.commit()
        await db.refresh(user)
    return await _one(db, user)
