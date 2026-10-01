import asyncio
from functools import lru_cache
from pathlib import Path
from time import perf_counter

import structlog
from alembic.config import Config
from alembic.script import ScriptDirectory
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine

from app.schemas.health import HealthCheck

logger = structlog.get_logger("app.health")

DB_CHECK_TIMEOUT_SECONDS = 3.0
_ALEMBIC_INI = Path(__file__).resolve().parents[2] / "alembic.ini"


@lru_cache
def expected_migration_head() -> str | None:
    """Latest migration revision shipped with this code (None if migrations are unavailable)."""
    try:
        return ScriptDirectory.from_config(Config(str(_ALEMBIC_INI))).get_current_head()
    except Exception:  # pragma: no cover - only when files are missing from a deployment
        return None


class HealthService:
    def __init__(self, engine: AsyncEngine) -> None:
        self.engine = engine

    async def check_database(self) -> HealthCheck:
        started = perf_counter()
        try:
            async with asyncio.timeout(DB_CHECK_TIMEOUT_SECONDS):
                async with self.engine.connect() as conn:
                    await conn.execute(text("SELECT 1"))
                    has_version_table = await conn.scalar(
                        text("SELECT to_regclass('public.alembic_version') IS NOT NULL")
                    )
                    revision = (
                        await conn.scalar(text("SELECT version_num FROM alembic_version"))
                        if has_version_table
                        else None
                    )
                    tables = await conn.scalar(
                        text(
                            "SELECT count(*) FROM information_schema.tables "
                            "WHERE table_schema = 'public' AND table_name <> 'alembic_version'"
                        )
                    )
        except Exception as exc:
            # Never expose connection strings or driver internals to the client.
            logger.warning("health.database_unavailable", error_type=type(exc).__name__)
            return HealthCheck(status="error", details={"error": "Database unreachable"})

        head = expected_migration_head()
        return HealthCheck(
            status="ok",
            details={
                "revision": revision,
                "head": head,
                "up_to_date": revision is not None and revision == head,
                "tables": tables,
                "latency_ms": round((perf_counter() - started) * 1000, 1),
            },
        )
