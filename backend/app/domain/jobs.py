"""Job rules (Feature doc Modules 02 + 03): query, normalized job, description quality, dedupe."""

import hashlib
import re
from dataclasses import dataclass, field
from datetime import datetime
from decimal import Decimal
from enum import StrEnum
from typing import Any, Protocol

from app.models.enums import DescriptionQuality

COMPLETE_MIN_CHARS = 800
PARTIAL_MIN_CHARS = 200
_SECTION_WORDS = re.compile(
    r"responsibilit|requirement|qualification|what you|you will|skills|experience|duties",
    re.IGNORECASE,
)


class Experience(StrEnum):
    """JSearch `job_requirements` values the UI offers."""

    NO_EXPERIENCE = "no_experience"
    UNDER_3_YEARS = "under_3_years_experience"
    MORE_THAN_3_YEARS = "more_than_3_years_experience"
    NO_DEGREE = "no_degree"


@dataclass(frozen=True)
class JobQuery:
    keywords: str
    location: str | None = None
    experience: Experience | None = None
    remote_only: bool = False
    country: str = "in"
    date_posted: str = "week"
    page: int = 1  # first JSearch page to fetch
    num_pages: int = 1

    def text(self) -> str:
        """JSearch works best with the location inside the query: "React Native in Hyderabad"."""
        keywords = " ".join(self.keywords.split())
        return f"{keywords} in {self.location.strip()}" if self.location else keywords


@dataclass
class NormalizedJob:
    source: str
    external_id: str
    title: str
    company: str
    company_domain: str | None = None
    location: str | None = None
    city: str | None = None
    country: str | None = None
    is_remote: bool = False
    employment_type: str | None = None
    description: str | None = None
    apply_url: str | None = None
    posted_at: datetime | None = None
    salary_min: Decimal | None = None
    salary_max: Decimal | None = None
    salary_currency: str | None = None
    raw: dict[str, Any] = field(default_factory=dict)

    @property
    def description_quality(self) -> DescriptionQuality:
        return classify_description(self.description)

    @property
    def dedupe_hash(self) -> str:
        return dedupe_hash(self.company, self.title, self.city)


class JobSource(Protocol):
    """A place jobs come from. New sources (Adzuna, RemoteOK …) only implement this."""

    name: str

    async def search(self, query: JobQuery) -> list[NormalizedJob]: ...


def classify_description(text: str | None) -> DescriptionQuality:
    length = len((text or "").strip())
    if length >= COMPLETE_MIN_CHARS and _SECTION_WORDS.search(text or ""):
        return DescriptionQuality.COMPLETE
    if length >= PARTIAL_MIN_CHARS:
        return DescriptionQuality.PARTIAL
    return DescriptionQuality.MISSING


def _norm(value: str | None) -> str:
    return " ".join((value or "").lower().split())


def dedupe_hash(company: str, title: str, city: str | None) -> str:
    """sha256(lower(company) | lower(title) | lower(city)) — Phase 0 §5.3."""
    key = f"{_norm(company)}|{_norm(title)}|{_norm(city)}"
    return hashlib.sha256(key.encode()).hexdigest()
