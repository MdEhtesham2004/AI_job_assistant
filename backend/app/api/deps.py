from collections.abc import AsyncIterator
from typing import Annotated

from fastapi import Depends, Request
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession

from app.core.config import Settings
from app.db.session import session_scope


def get_app_settings(request: Request) -> Settings:
    """Settings the running app was created with (overridable per app instance in tests)."""
    settings: Settings = request.app.state.settings
    return settings


def get_engine(request: Request) -> AsyncEngine:
    engine: AsyncEngine = request.app.state.engine
    return engine


async def get_db(request: Request) -> AsyncIterator[AsyncSession]:
    """One database session per request (Phase 1 §2.6 unit of work)."""
    async for session in session_scope(request.app.state.session_factory):
        yield session


SettingsDep = Annotated[Settings, Depends(get_app_settings)]
EngineDep = Annotated[AsyncEngine, Depends(get_engine)]
DbSession = Annotated[AsyncSession, Depends(get_db)]
