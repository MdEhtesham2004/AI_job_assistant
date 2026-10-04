from datetime import UTC, datetime

from fastapi import APIRouter, Request, Response, status

from app.api.deps import ApprovedUser, CurrentUser, DbSession
from app.schemas.auth import UserRead
from app.schemas.users import (
    DeleteAccount,
    MeUpdate,
    ProfileRead,
    ProfileUpdate,
    SettingsRead,
    SettingsUpdate,
)
from app.services.account import AccountService
from app.services.account_data import delete_account, export_zip

router = APIRouter(prefix="/users/me", tags=["users"])


@router.get("", response_model=UserRead, summary="The signed-in user (also for pending accounts)")
async def read_me(user: CurrentUser) -> UserRead:
    return UserRead.model_validate(user)


@router.patch("", response_model=UserRead, summary="Update your name")
async def update_me(body: MeUpdate, user: ApprovedUser, db: DbSession) -> UserRead:
    return UserRead.model_validate(await AccountService(db, user).update_name(body.full_name))


@router.get("/profile", response_model=ProfileRead, summary="Your profile")
async def read_profile(user: ApprovedUser, db: DbSession) -> ProfileRead:
    return ProfileRead.model_validate(await AccountService(db, user).get_profile())


@router.put("/profile", response_model=ProfileRead, summary="Replace your profile")
async def update_profile(body: ProfileUpdate, user: ApprovedUser, db: DbSession) -> ProfileRead:
    return ProfileRead.model_validate(await AccountService(db, user).update_profile(body))


@router.get("/settings", response_model=SettingsRead, summary="Your settings")
async def read_settings(user: ApprovedUser, db: DbSession) -> SettingsRead:
    return SettingsRead.model_validate(await AccountService(db, user).get_settings())


@router.patch("/settings", response_model=SettingsRead, summary="Change some settings")
async def update_settings(body: SettingsUpdate, user: ApprovedUser, db: DbSession) -> SettingsRead:
    return SettingsRead.model_validate(await AccountService(db, user).update_settings(body))


# ---------- Phase 14: export / delete ----------


@router.get(
    "/export",
    response_class=Response,
    summary="Download all your data (JSON per table + your files) as a ZIP",
    responses={200: {"content": {"application/zip": {}}}},
)
async def export_my_data(request: Request, user: ApprovedUser, db: DbSession) -> Response:
    content = await export_zip(db, request.app.state.storage, user)
    name = f"my-data-{datetime.now(UTC):%Y-%m-%d}.zip"
    return Response(
        content=content,
        media_type="application/zip",
        headers={
            "Content-Disposition": f'attachment; filename="{name}"',
            "Cache-Control": "private, no-store",
        },
    )


@router.post(
    "/delete",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Delete your account and all your data (password + email confirmation)",
)
async def delete_me(
    body: DeleteAccount, request: Request, response: Response, user: CurrentUser, db: DbSession
) -> None:
    settings = request.app.state.settings
    await delete_account(
        db,
        settings,
        request.app.state.storage,
        user,
        password=body.password,
        confirm_email=body.confirm_email,
    )
    response.delete_cookie(
        settings.refresh_cookie_name,
        path=f"{settings.api_prefix}/auth",
        httponly=True,
        secure=settings.refresh_cookie_secure,
        samesite="strict",
    )
