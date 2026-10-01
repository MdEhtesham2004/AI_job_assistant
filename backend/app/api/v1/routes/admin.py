import uuid
from typing import Annotated

from fastapi import APIRouter, Query

from app.api.deps import AdminUser, DbSession
from app.repositories.users import UserFilter
from app.schemas.admin import AdminUserRead, RejectRequest, RoleUpdate, UserStatusCounts
from app.schemas.common import Page
from app.services.user_admin import UserAdminService

router = APIRouter(prefix="/admin/users", tags=["admin"])


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
    return Page(
        items=[AdminUserRead.model_validate(u) for u in users],
        total=total,
        page=page,
        page_size=page_size,
    )


@router.get("/counts", response_model=UserStatusCounts, summary="Number of accounts per status")
async def user_counts(admin: AdminUser, db: DbSession) -> UserStatusCounts:
    return UserStatusCounts(**await UserAdminService(db, admin).status_counts())


@router.get("/{user_id}", response_model=AdminUserRead, summary="One account")
async def get_user(user_id: uuid.UUID, admin: AdminUser, db: DbSession) -> AdminUserRead:
    return AdminUserRead.model_validate(await UserAdminService(db, admin).get_user(user_id))


@router.post("/{user_id}/approve", response_model=AdminUserRead, summary="Approve a sign-up")
async def approve(user_id: uuid.UUID, admin: AdminUser, db: DbSession) -> AdminUserRead:
    return AdminUserRead.model_validate(await UserAdminService(db, admin).approve(user_id))


@router.post("/{user_id}/reject", response_model=AdminUserRead, summary="Reject a sign-up")
async def reject(
    user_id: uuid.UUID, body: RejectRequest, admin: AdminUser, db: DbSession
) -> AdminUserRead:
    user = await UserAdminService(db, admin).reject(user_id, body.reason)
    return AdminUserRead.model_validate(user)


@router.post("/{user_id}/deactivate", response_model=AdminUserRead, summary="Deactivate")
async def deactivate(user_id: uuid.UUID, admin: AdminUser, db: DbSession) -> AdminUserRead:
    return AdminUserRead.model_validate(await UserAdminService(db, admin).deactivate(user_id))


@router.post("/{user_id}/reactivate", response_model=AdminUserRead, summary="Reactivate")
async def reactivate(user_id: uuid.UUID, admin: AdminUser, db: DbSession) -> AdminUserRead:
    return AdminUserRead.model_validate(await UserAdminService(db, admin).reactivate(user_id))


@router.patch("/{user_id}/role", response_model=AdminUserRead, summary="Change role")
async def change_role(
    user_id: uuid.UUID, body: RoleUpdate, admin: AdminUser, db: DbSession
) -> AdminUserRead:
    user = await UserAdminService(db, admin).change_role(user_id, body.role)
    return AdminUserRead.model_validate(user)
