import uuid
from datetime import datetime
from decimal import Decimal

from sqlalchemy import func, select

from app.models.system import AiCall
from app.repositories.base import BaseRepository


class AiCallRepository(BaseRepository[AiCall]):
    model = AiCall

    async def cost_since(self, user_id: uuid.UUID, since: datetime) -> Decimal:
        total = await self.session.scalar(
            select(func.coalesce(func.sum(AiCall.cost_usd), 0)).where(
                AiCall.user_id == user_id, AiCall.created_at >= since
            )
        )
        return Decimal(total or 0)
