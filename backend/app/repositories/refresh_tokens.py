import uuid
from datetime import datetime

from sqlalchemy import select, update

from app.models.accounts import AuthRefreshToken
from app.repositories.base import BaseRepository


class RefreshTokenRepository(BaseRepository[AuthRefreshToken]):
    model = AuthRefreshToken

    async def get_by_hash(self, token_hash: str) -> AuthRefreshToken | None:
        return await self.session.scalar(
            select(AuthRefreshToken).where(AuthRefreshToken.token_hash == token_hash)
        )

    async def revoke_family(self, family_id: uuid.UUID, at: datetime) -> None:
        await self.session.execute(
            update(AuthRefreshToken)
            .where(AuthRefreshToken.family_id == family_id, AuthRefreshToken.revoked_at.is_(None))
            .values(revoked_at=at)
        )

    async def revoke_all_for_user(self, user_id: uuid.UUID, at: datetime) -> None:
        await self.session.execute(
            update(AuthRefreshToken)
            .where(AuthRefreshToken.user_id == user_id, AuthRefreshToken.revoked_at.is_(None))
            .values(revoked_at=at)
        )
