from collections.abc import AsyncIterator

from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.pool import NullPool

from app.core.config import Settings


def create_engine(settings: Settings, database_url: str | None = None) -> AsyncEngine:
    url = database_url or settings.database_url
    if settings.app_env == "test":
        # Tests run requests on different event loops; pooled asyncpg connections are loop-bound.
        return create_async_engine(url, echo=settings.database_echo, poolclass=NullPool)
    return create_async_engine(
        url,
        echo=settings.database_echo,
        pool_size=settings.database_pool_size,
        pool_pre_ping=True,
    )


def create_session_factory(engine: AsyncEngine) -> async_sessionmaker[AsyncSession]:
    return async_sessionmaker(engine, expire_on_commit=False, autoflush=False)


async def session_scope(factory: async_sessionmaker[AsyncSession]) -> AsyncIterator[AsyncSession]:
    """One session per request; rolled back if the request fails before committing."""
    async with factory() as session:
        try:
            yield session
        except Exception:
            await session.rollback()
            raise
