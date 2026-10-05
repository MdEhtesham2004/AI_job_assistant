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

    # --- Job search (Phase 8) ---
    jsearch_api_key: str = Field(
        default="",
        repr=False,
        validation_alias=AliasChoices("JSEARCH_API_KEY", "RAPIDAPI_KEY"),
    )
    jsearch_base_url: str = "https://jsearch.p.rapidapi.com"
    jsearch_search_path: str = "/search-v2"
    jsearch_country: str = "in"
    jsearch_num_pages: int = Field(default=1, ge=1, le=3)
    jsearch_date_posted: Literal["all", "today", "3days", "week", "month"] = "week"
    jsearch_timeout_seconds: float = 30.0
    # Cross-source duplicates: same company + title + city seen within this many days.
    job_dedupe_days: int = 30
    # JSearch quota protection.
    max_active_saved_searches: int = 5
    saved_search_min_interval_minutes: int = 60
    job_page_fetch_timeout_seconds: float = 10.0

    # --- Gmail + outreach (Phase 12) ---
    google_client_id: str = Field(
        default="", validation_alias=AliasChoices("GOOGLE_CLIENT_ID", "CLIENT_ID")
    )
    google_client_secret: str = Field(
        default="",
        repr=False,
        validation_alias=AliasChoices("GOOGLE_CLIENT_SECRET", "CLIENT_SECRET"),
    )
    google_redirect_uri: str = "http://localhost:8000/api/v1/integrations/gmail/callback"
    # Where the browser goes after the Google consent screen.
    frontend_url: str = "http://localhost:5173"
    # Fernet key (urlsafe base64, 32 bytes) for OAuth tokens at rest.
    token_encryption_key: str = Field(default="", repr=False)
    gmail_api_url: str = "https://gmail.googleapis.com"
    google_oauth_url: str = "https://oauth2.googleapis.com"
    # LinkedIn hiring posts via Apify (harvestapi/linkedin-post-search).
    apify_token: str = Field(
        default="", repr=False, validation_alias=AliasChoices("APIFY_TOKEN", "APIFY_API_KEY")
    )
    apify_base_url: str = "https://api.apify.com"
    apify_linkedin_actor: str = "harvestapi~linkedin-post-search"
    apify_max_posts: int = Field(default=50, ge=1, le=200)
    apify_timeout_seconds: float = 300.0
    # Hold sends until this local time when the daily cap was reached.
    send_window_start_hour: int = 9
    send_jitter_seconds: int = 30

    # --- AI mock interview (Phase 15): OpenAI Realtime, speech-to-speech over WebRTC ---
    # A real OpenAI key (platform.openai.com). Not OPENAI_API_KEY: that name is read as the
    # OpenRouter key above.
    realtime_api_key: str = Field(
        default="", repr=False, validation_alias=AliasChoices("OPENAI_REALTIME_API_KEY")
    )
    realtime_base_url: str = "https://api.openai.com/v1"
    realtime_model: str = "gpt-realtime-mini"
    realtime_voice: str = "marin"
    realtime_transcription_model: str = "gpt-4o-mini-transcribe"
    # Short-lived browser token: only long enough to connect (the call itself may run on).
    realtime_token_seconds: int = Field(default=120, ge=10, le=7200)
    # Rough price for the cost estimate (USD per interview minute; 0 = unknown).
    realtime_cost_per_minute_usd: float = Field(default=0.10, ge=0)

    # Gemini Live (Google AI Studio key): the alternative voice service, WebSocket-based.
    gemini_api_key: str = Field(
        default="", repr=False, validation_alias=AliasChoices("GEMINI_API_KEY")
    )
    gemini_base_url: str = "https://generativelanguage.googleapis.com"
    gemini_live_model: str = "gemini-2.5-flash-native-audio-latest"
    gemini_live_voice: str = "Aoede"  # a warm, friendly prebuilt voice
    gemini_cost_per_minute_usd: float = Field(default=0.04, ge=0)
    # Which service runs the interviewer: auto = Gemini when its key is set, else OpenAI.
    interview_voice_provider: Literal["auto", "gemini", "openai"] = "auto"

    @property
    def voice_provider(self) -> Literal["gemini", "openai"]:
        if self.interview_voice_provider != "auto":
            return self.interview_voice_provider
        return "gemini" if self.gemini_api_key else "openai"

    # --- Daily best-matches digest (Phase 16) ---
    digest_score_cap: int = Field(default=20, ge=0, le=200)  # AI scores per user per day
    digest_max_jobs: int = Field(default=5, ge=1, le=20)

    # --- Paid data APIs: cost control (Phase 14) ---
    # Identical searches within this window reuse stored results (shared by all users).
    jsearch_cache_hours: float = Field(default=12, ge=0)
    apify_cache_hours: float = Field(default=24, ge=0)
    # A keyword fetched (for real) this recently is searched for the last 24 h only.
    apify_recent_hours: float = Field(default=48, ge=0)
    # Optional Apify spending cap per run (pay-per-event actors; 0 = no cap sent).
    apify_max_charge_usd: float = Field(default=0, ge=0)
    # Price estimates for Admin › Analytics (your plan's prices; 0 = show units only).
    jsearch_cost_per_request_usd: float = Field(default=0, ge=0)
    apify_cost_per_1000_posts_usd: float = Field(default=0, ge=0)
    # Admins are notified when the JSearch plan has fewer requests left than this.
    jsearch_quota_alert_below: int = Field(default=25, ge=0)
    # Saved searches only run for users seen in the last N days (0 = always).
    saved_search_active_days: int = Field(default=14, ge=0)

    # --- Production hardening (Phase 14) ---
    # Requests per minute per client IP for the whole API (0 = off).
    api_rate_limit_per_minute: int = Field(default=600, ge=0)
    # Largest request body accepted (resumes and CSV imports are 5 MB).
    max_request_bytes: int = Field(default=10 * 1024 * 1024, ge=0)
    # Error monitoring: active only when a DSN is set.
    sentry_dsn: str = Field(default="", repr=False)
    sentry_traces_sample_rate: float = Field(default=0.0, ge=0, le=1)

    @property
    def gmail_configured(self) -> bool:
        return bool(
            self.google_client_id and self.google_client_secret and self.token_encryption_key
        )

    @property
    def apify_configured(self) -> bool:
        return bool(self.apify_token)

    @property
    def jsearch_configured(self) -> bool:
        return bool(self.jsearch_api_key)

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
