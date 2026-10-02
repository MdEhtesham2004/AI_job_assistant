from functools import lru_cache
from typing import Literal

from pydantic import AliasChoices, Field, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application settings, read from environment variables (and `.env` in development)."""

    model_config = SettingsConfigDict(
        env_file=".env", env_file_encoding="utf-8", extra="ignore", populate_by_name=True
    )

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

    # --- Infrastructure (Phase 6) ---
    redis_url: str = "redis://localhost:6379/0"
    # Tests and simple local runs can skip the broker: tasks are recorded but not sent.
    celery_enabled: bool = True
    task_max_retries: int = 3

    # File storage: "local" (development, tests) or "s3" (production, e.g. Cloudflare R2).
    storage_backend: Literal["local", "s3"] = "local"
    storage_local_path: str = "storage"
    file_link_minutes: int = 15

    gotenberg_url: str = "http://localhost:3000"
    gotenberg_timeout_seconds: float = 60.0

    # Any OpenAI-compatible chat-completions API (OpenRouter by default).
    ai_base_url: str = "https://openrouter.ai/api/v1"
    ai_api_key: str = Field(
        default="",
        repr=False,
        validation_alias=AliasChoices("AI_API_KEY", "OPENROUTER_API_KEY", "OPENAI_API_KEY"),
    )
    ai_model_default: str = "openai/gpt-oss-120b"
    # Hard limit for one AI request (the whole response, not only between bytes).
    ai_timeout_seconds: float = 120.0
    ai_max_output_tokens: int = 8000
    # Reasoning models (e.g. gpt-oss): low effort is enough for extraction and scoring.
    ai_reasoning_effort: Literal["low", "medium", "high"] | None = "low"
    # OpenRouter provider routing. "throughput" avoids slow hosts that loop on strict JSON
    # (measured in Phase 7: cheapest-first routing sometimes took > 90 s per call).
    ai_provider_sort: Literal["price", "throughput", "latency"] | None = "throughput"
    ai_cache_ttl_seconds: int = 7 * 24 * 3600

    # --- Resumes (Phase 7) ---
    resume_max_bytes: int = 5 * 1024 * 1024
    # Resume text sent to the AI is cut to this many characters (cost control).
    resume_ai_max_chars: int = 20_000

    @property
    def ai_configured(self) -> bool:
        return bool(self.ai_api_key)

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
