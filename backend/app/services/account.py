from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import ValidationAppError
from app.models.accounts import Profile, User, UserSettings
from app.repositories.profiles import ProfileRepository, UserSettingsRepository
from app.schemas.users import ProfileUpdate, SettingsUpdate


class AccountService:
    """The signed-in user's own name, profile and settings (always scoped to that user)."""

    def __init__(self, session: AsyncSession, user: User) -> None:
        self.session = session
        self.user = user
        self.profiles = ProfileRepository(session, owner_id=user.id)
        self.settings = UserSettingsRepository(session, owner_id=user.id)

    async def update_name(self, full_name: str) -> User:
        self.user.full_name = full_name
        await self.session.commit()
        return self.user

    async def get_profile(self) -> Profile:
        profile = await self.profiles.get_or_create()
        await self.session.commit()
        return profile

    async def update_profile(self, data: ProfileUpdate) -> Profile:
        profile = await self.profiles.get_or_create()
        await self.profiles.update(
            profile,
            phone=data.phone,
            location=data.location,
            headline=data.headline,
            links=data.links_dict(),
            timezone=data.timezone,
        )
        await self.session.commit()
        return profile

    async def get_settings(self) -> UserSettings:
        settings = await self.settings.get_or_create()
        await self.session.commit()
        return settings

    async def update_settings(self, data: SettingsUpdate) -> UserSettings:
        settings = await self.settings.get_or_create()
        changes = data.model_dump(exclude_none=True)
        if "score_weights" in changes and data.score_weights is not None:
            changes["score_weights"] = data.score_weights.model_dump()

        use_master = changes.get("threshold_use_master", settings.threshold_use_master)
        tailor = changes.get("threshold_tailor", settings.threshold_tailor)
        if tailor >= use_master:
            raise ValidationAppError(
                "The 'tailor' threshold must be lower than the 'use master resume' threshold.",
                code="INVALID_THRESHOLDS",
            )

        await self.settings.update(settings, **changes)
        await self.session.commit()
        return settings
