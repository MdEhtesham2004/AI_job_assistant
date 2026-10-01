from app.models.accounts import Profile, UserSettings
from app.repositories.base import OwnedRepository


class ProfileRepository(OwnedRepository[Profile]):
    model = Profile

    async def get_or_create(self) -> Profile:
        profile = await self.get(self.owner_id)
        return profile if profile is not None else await self.add(Profile())


class UserSettingsRepository(OwnedRepository[UserSettings]):
    model = UserSettings

    async def get_or_create(self) -> UserSettings:
        settings = await self.get(self.owner_id)
        return settings if settings is not None else await self.add(UserSettings())
