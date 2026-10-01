from decimal import Decimal
from typing import Annotated
from zoneinfo import available_timezones

from pydantic import (
    AnyHttpUrl,
    BaseModel,
    ConfigDict,
    Field,
    StringConstraints,
    field_validator,
    model_validator,
)

from app.schemas.auth import FullName

_TIMEZONES = frozenset(available_timezones())

ShortText = Annotated[str, StringConstraints(strip_whitespace=True, max_length=120)]
Phone = Annotated[str, StringConstraints(strip_whitespace=True, max_length=30)]


class MeUpdate(BaseModel):
    full_name: FullName


# ---------- profile ----------


class ProfileLinks(BaseModel):
    linkedin: AnyHttpUrl | None = None
    github: AnyHttpUrl | None = None
    portfolio: AnyHttpUrl | None = None


class ProfileRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    phone: str | None
    location: str | None
    headline: str | None
    links: dict[str, str]
    timezone: str


class ProfileUpdate(BaseModel):
    phone: Phone | None = None
    location: ShortText | None = None
    headline: Annotated[str, StringConstraints(strip_whitespace=True, max_length=220)] | None = None
    links: ProfileLinks = Field(default_factory=ProfileLinks)
    timezone: str = "Asia/Kolkata"

    @field_validator("timezone")
    @classmethod
    def _known_timezone(cls, value: str) -> str:
        if value not in _TIMEZONES:
            raise ValueError("Unknown time zone.")
        return value

    @field_validator("phone", "location", "headline")
    @classmethod
    def _blank_to_none(cls, value: str | None) -> str | None:
        return value or None

    def links_dict(self) -> dict[str, str]:
        return {key: str(url) for key, url in self.links.model_dump().items() if url is not None}


# ---------- settings ----------

Percent = Annotated[int, Field(ge=0, le=100)]
WEIGHT_KEYS = ("skills", "experience", "technology", "education", "location")


class ScoreWeights(BaseModel):
    skills: Percent
    experience: Percent
    technology: Percent
    education: Percent
    location: Percent

    @model_validator(mode="after")
    def _sum_to_100(self) -> "ScoreWeights":
        if sum(getattr(self, key) for key in WEIGHT_KEYS) != 100:
            raise ValueError("Score weights must add up to 100.")
        return self


class SettingsRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    threshold_use_master: int
    threshold_tailor: int
    score_weights: ScoreWeights
    auto_analyze_new_jobs: bool
    daily_send_cap: int
    send_interval_seconds: int
    recipient_cooldown_days: int
    follow_up_days: int
    no_response_days: int
    linkedin_source_enabled: bool
    automation_enabled: bool
    automation_min_score: int
    monthly_ai_budget_usd: Decimal


class SettingsUpdate(BaseModel):
    """Partial update: only the fields sent are changed."""

    threshold_use_master: Percent | None = None
    threshold_tailor: Percent | None = None
    score_weights: ScoreWeights | None = None
    auto_analyze_new_jobs: bool | None = None
    daily_send_cap: Annotated[int, Field(ge=0, le=500)] | None = None
    send_interval_seconds: Annotated[int, Field(ge=30, le=3600)] | None = None
    recipient_cooldown_days: Annotated[int, Field(ge=0, le=365)] | None = None
    follow_up_days: Annotated[int, Field(ge=0, le=60)] | None = None
    no_response_days: Annotated[int, Field(ge=1, le=180)] | None = None
    linkedin_source_enabled: bool | None = None
    automation_enabled: bool | None = None
    automation_min_score: Percent | None = None
    monthly_ai_budget_usd: Annotated[Decimal, Field(ge=0, le=1000, decimal_places=2)] | None = None
