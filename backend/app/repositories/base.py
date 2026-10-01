import uuid
from collections.abc import Sequence
from typing import Any

from sqlalchemy import ColumnElement, Select, func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import InstrumentedAttribute

from app.db.base import Base


class BaseRepository[ModelT: Base]:
    """Database access for one model. Repositories never commit — services own transactions.

    For tables that belong to a user, use `OwnedRepository` instead: it applies the
    `user_id` filter to every query, so one user can never read another user's rows.
    """

    model: type[ModelT]

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def get(self, id_: uuid.UUID) -> ModelT | None:
        return await self.session.get(self.model, id_)

    async def list(self, *, limit: int = 100, offset: int = 0) -> Sequence[ModelT]:
        result = await self.session.scalars(select(self.model).limit(limit).offset(offset))
        return result.all()

    async def count(self) -> int:
        return await self.session.scalar(select(func.count()).select_from(self.model)) or 0

    async def add(self, instance: ModelT) -> ModelT:
        self.session.add(instance)
        await self.session.flush()
        return instance

    async def update(self, instance: ModelT, **values: Any) -> ModelT:
        for key, value in values.items():
            setattr(instance, key, value)
        await self.session.flush()
        return instance


class OwnedRepository[ModelT: Base](BaseRepository[ModelT]):
    """Repository for user-owned rows (Phase 1 §2.2, Phase 5 isolation rule).

    Every read is scoped to `owner_id`. A row owned by someone else behaves exactly like a
    row that does not exist (the API turns that into 404, never 403).
    """

    owner_column: str = "user_id"

    def __init__(self, session: AsyncSession, owner_id: uuid.UUID) -> None:
        super().__init__(session)
        self.owner_id = owner_id

    def _owned(self) -> ColumnElement[bool]:
        owner: InstrumentedAttribute[uuid.UUID] = getattr(self.model, self.owner_column)
        return owner == self.owner_id

    def scoped(self) -> Select[Any]:
        return select(self.model).where(self._owned())

    async def get(self, id_: uuid.UUID) -> ModelT | None:
        primary_key = self.model.__mapper__.primary_key[0]
        instance: ModelT | None = await self.session.scalar(self.scoped().where(primary_key == id_))
        return instance

    async def list(self, *, limit: int = 100, offset: int = 0) -> Sequence[ModelT]:
        result = await self.session.scalars(self.scoped().limit(limit).offset(offset))
        rows: Sequence[ModelT] = result.all()
        return rows

    async def count(self) -> int:
        query = select(func.count()).select_from(self.model).where(self._owned())
        return await self.session.scalar(query) or 0

    async def add(self, instance: ModelT) -> ModelT:
        setattr(instance, self.owner_column, self.owner_id)  # owner is never taken from input
        return await super().add(instance)
