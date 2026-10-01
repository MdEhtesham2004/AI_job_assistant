import asyncio

from alembic import command
from alembic.autogenerate import compare_metadata
from alembic.migration import MigrationContext
from sqlalchemy import inspect, text
from sqlalchemy.ext.asyncio import AsyncEngine, create_async_engine
from sqlalchemy.pool import NullPool

from app.core.config import Settings
from app.db.base import Base
from tests.conftest import alembic_config

EXPECTED_TABLES = {"users", "tasks", "audit_logs"}


def _tables(database_url: str) -> set[str]:
    async def inspect_tables() -> set[str]:
        engine = create_async_engine(database_url, poolclass=NullPool)
        async with engine.connect() as conn:
            names = await conn.run_sync(lambda sync_conn: inspect(sync_conn).get_table_names())
        await engine.dispose()
        return set(names) - {"alembic_version"}

    return asyncio.run(inspect_tables())


async def test_models_match_the_migrated_schema(engine: AsyncEngine) -> None:
    """Guards against model changes without a migration (same as `alembic check`)."""

    def diff(sync_conn):  # type: ignore[no-untyped-def]
        context = MigrationContext.configure(sync_conn, opts={"compare_type": True})
        return compare_metadata(context, Base.metadata)

    async with engine.connect() as conn:
        differences = await conn.run_sync(diff)

    assert differences == []


def test_downgrade_and_upgrade_round_trip(settings: Settings, migrated_database: str) -> None:
    # Sync test: Alembic's env.py runs its own event loop.
    config = alembic_config(migrated_database)

    command.downgrade(config, "base")
    assert _tables(migrated_database) == set()

    command.upgrade(config, "head")
    assert _tables(migrated_database) == EXPECTED_TABLES


async def test_required_extensions_are_installed(engine: AsyncEngine) -> None:
    async with engine.connect() as conn:
        result = await conn.scalars(
            text("SELECT extname FROM pg_extension WHERE extname IN ('pgcrypto', 'citext')")
        )
        assert set(result.all()) == {"pgcrypto", "citext"}
