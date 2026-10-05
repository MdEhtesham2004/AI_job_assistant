import asyncio
from collections.abc import AsyncIterator, Iterator
from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from cryptography.fernet import Fernet
from fakeredis.aioredis import FakeRedis
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import text
from sqlalchemy.engine import make_url
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, create_async_engine
from sqlalchemy.pool import NullPool

import app.models  # noqa: F401  (registers all tables)
from app.core.config import Settings
from app.db.base import Base
from app.main import create_app

BACKEND_DIR = Path(__file__).resolve().parents[1]
TABLES = tuple(sorted(Base.metadata.tables))  # wiped after every test
TEST_SECRET_KEY = "test-secret-key-for-automated-tests-only-0123456789"


@pytest.fixture(scope="session")
def settings(tmp_path_factory: pytest.TempPathFactory) -> Settings:
    base = Settings()  # reads backend/.env
    url = make_url(base.test_database_url)
    # Safety: the suite wipes this database — never run it against real data.
    if not (url.database or "").endswith("_test"):
        pytest.exit(f"TEST_DATABASE_URL must point to a *_test database, got {url.database!r}")
    return Settings(
        app_env="test",
        log_json=False,
        log_level="WARNING",
        database_url=base.test_database_url,
        test_database_url=base.test_database_url,
        secret_key=TEST_SECRET_KEY,
        cookie_secure=False,  # TestClient talks plain http
        # Phase 6: no real broker, storage in a temp folder, fake external services.
        celery_enabled=False,
        storage_local_path=str(tmp_path_factory.mktemp("storage")),
        gotenberg_url="http://gotenberg.test",
        ai_base_url="https://ai.test/v1",
        ai_api_key="test-ai-key",
        ai_model_default="test/model",
        # Phase 8: never call the real JSearch from tests.
        jsearch_api_key="test-jsearch-key",
        jsearch_base_url="https://jsearch.test",
        # Voice services: never the real keys from backend/.env (tests set their own).
        realtime_api_key="",
        gemini_api_key="",
    )


@pytest.fixture
def gmail_settings(settings: Settings) -> Settings:
    """Phase 12/13: Gmail configured against fake Google endpoints (respx)."""
    return settings.model_copy(
        update={
            "google_client_id": "client-id",
            "google_client_secret": "client-secret",
            "token_encryption_key": Fernet.generate_key().decode(),
            "google_oauth_url": "https://oauth.test",
            "gmail_api_url": "https://gmail.test",
            "send_jitter_seconds": 0,
        }
    )


def alembic_config(database_url: str) -> Config:
    config = Config(str(BACKEND_DIR / "alembic.ini"))
    config.set_main_option("sqlalchemy.url", database_url)
    config.attributes["configure_logger"] = False
    return config


async def _truncate(database_url: str) -> None:
    engine = create_async_engine(database_url, poolclass=NullPool)
    async with engine.begin() as conn:
        await conn.execute(text(f"TRUNCATE {', '.join(TABLES)} RESTART IDENTITY CASCADE"))
    await engine.dispose()


@pytest.fixture(scope="session")
def migrated_database(settings: Settings) -> str:
    """Rebuild the test database from scratch through the migrations, once per test run."""
    config = alembic_config(settings.database_url)
    command.downgrade(config, "base")
    command.upgrade(config, "head")
    return settings.database_url


@pytest.fixture(autouse=True)
def clean_tables(migrated_database: str) -> Iterator[None]:
    yield
    asyncio.run(_truncate(migrated_database))


@pytest.fixture
def app(settings: Settings, migrated_database: str) -> FastAPI:
    application = create_app(settings)
    application.state.redis = FakeRedis(decode_responses=True)
    return application


@pytest.fixture
def client(app: FastAPI) -> Iterator[TestClient]:
    with TestClient(app, raise_server_exceptions=False) as test_client:
        yield test_client


@pytest.fixture
async def engine(migrated_database: str) -> AsyncIterator[AsyncEngine]:
    test_engine = create_async_engine(migrated_database, poolclass=NullPool)
    yield test_engine
    await test_engine.dispose()


@pytest.fixture
async def session(engine: AsyncEngine) -> AsyncIterator[AsyncSession]:
    async with AsyncSession(engine, expire_on_commit=False) as db_session:
        yield db_session
