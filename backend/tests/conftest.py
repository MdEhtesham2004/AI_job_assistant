import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.core.config import Settings
from app.main import create_app


@pytest.fixture
def settings() -> Settings:
    return Settings(app_env="test", log_json=False, log_level="WARNING")


@pytest.fixture
def app(settings: Settings) -> FastAPI:
    return create_app(settings)


@pytest.fixture
def client(app: FastAPI) -> TestClient:
    return TestClient(app, raise_server_exceptions=False)
