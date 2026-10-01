from functools import lru_cache
from typing import Literal

from pydantic import Field, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application settings, read from environment variables (and `.env` in development)."""

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    app_name: str = "AI Job Application Platform"
    app_env: Literal["development", "test", "production"] = "development"
    app_version: str = "0.1.0"
    api_prefix: str = "/api/v1"

    log_level: str = "INFO"
    log_json: bool = True

    # JSON list in the environment, e.g. CORS_ORIGINS='["http://localhost:5173"]'
    cors_origins: list[str] = Field(default_factory=lambda: ["http://localhost:5173"])

    # postgresql+asyncpg://user:password@host:5432/dbname
    database_url: str = "postgresql+asyncpg://app:app@localhost:5432/jobs"
    database_pool_size: int = 5
    database_echo: bool = False
    # Used only by the automated tests; never point this at real data.
    test_database_url: str = "postgresql+asyncpg://app:app@localhost:5432/jobs_test"

    # --- Authentication (Phase 4) ---
    # Signs access tokens and reset tokens. Required: at least 32 characters.
    secret_key: str = Field(default="", repr=False)
    access_token_minutes: int = 15
    refresh_token_days: int = 14
    password_reset_minutes: int = 30
    refresh_cookie_name: str = "refresh_token"
    # None → secure cookies everywhere except development.
    cookie_secure: bool | None = None

    @property
    def refresh_cookie_secure(self) -> bool:
        return (
            self.cookie_secure if self.cookie_secure is not None else self.app_env != "development"
        )

    @model_validator(mode="after")
    def _require_secret_key(self) -> "Settings":
        if len(self.secret_key) < 32:
            raise ValueError("SECRET_KEY must be set and at least 32 characters long.")
        return self


@lru_cache
def get_settings() -> Settings:
    return Settings()
