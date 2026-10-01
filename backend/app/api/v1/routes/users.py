from fastapi import APIRouter

from app.api.deps import ApprovedUser, CurrentUser, DbSession
from app.schemas.auth import UserRead
from app.schemas.users import MeUpdate, ProfileRead, ProfileUpdate, SettingsRead, SettingsUpdate
from app.services.account import AccountService

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
