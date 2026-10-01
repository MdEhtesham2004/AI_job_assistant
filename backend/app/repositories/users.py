from sqlalchemy import select

from app.models.accounts import User
from app.repositories.base import BaseRepository


class UserRepository(BaseRepository[User]):
    model = User

    async def get_by_email(self, email: str) -> User | None:
        # email is citext → comparison is case-insensitive in the database.
        return await self.session.scalar(select(User).where(User.email == email))
