"""JSearch (RapidAPI) job source. Code calls JSearch; the AI never rewrites its results."""

import base64
from datetime import UTC, datetime
from decimal import Decimal, InvalidOperation
from typing import Any
from urllib.parse import urlparse

import httpx
import structlog

from app.core.config import Settings
from app.core.errors import AppError, ExternalServiceError
from app.domain.jobs import JobQuery, NormalizedJob

logger = structlog.get_logger("app.jsearch")


class JobSourceConfigError(AppError):
    """Not worth retrying: missing/invalid key or exhausted quota."""

    status_code = 502
    code = "JOB_SOURCE_UNAVAILABLE"


class JSearchSource:
    name = "jsearch"

    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        # RapidAPI's "requests left on the plan" after the last call (cost control).
        self.last_quota_remaining: int | None = None

    def params(self, query: JobQuery) -> dict[str, str]:
        params = {
            "query": query.text(),
            "page": str(query.page),
            "num_pages": str(query.num_pages),
            "country": query.country,
            "date_posted": query.date_posted,
        }
        if query.remote_only:
            params["work_from_home"] = "true"
        if query.experience:
            params["job_requirements"] = query.experience.value
        return params

    async def search(self, query: JobQuery) -> list[NormalizedJob]:
        if not self.settings.jsearch_configured:
            raise JobSourceConfigError(
                "Job search is not configured (JSEARCH_API_KEY is missing).",
                code="JSEARCH_NOT_CONFIGURED",
            )
        host = urlparse(self.settings.jsearch_base_url).netloc
        try:
            async with httpx.AsyncClient(timeout=self.settings.jsearch_timeout_seconds) as client:
                response = await client.get(
                    self.settings.jsearch_base_url.rstrip("/") + self.settings.jsearch_search_path,
                    params=self.params(query),
                    headers={
                        "x-rapidapi-key": self.settings.jsearch_api_key,
                        "x-rapidapi-host": host,
                    },
                )
        except httpx.HTTPError as exc:
            raise ExternalServiceError(
                "JSearch is unreachable.", details={"provider": "jsearch"}
            ) from exc

        if response.status_code in (401, 403):
            raise JobSourceConfigError(
                "JSearch rejected the API key (check JSEARCH_API_KEY and your RapidAPI plan).",
                details={"status": response.status_code},
            )
        if response.status_code == 429:
            raise JobSourceConfigError(
                "JSearch quota or rate limit reached. Try again later.",
                code="JSEARCH_QUOTA",
                details={"status": 429},
            )
        if response.status_code != 200:
            raise ExternalServiceError(
                "JSearch returned an error.",
                details={"provider": "jsearch", "status": response.status_code},
            )
        remaining = response.headers.get("x-ratelimit-requests-remaining")
        self.last_quota_remaining = int(remaining) if remaining and remaining.isdigit() else None
        jobs = [job for item in _items(response.json()) if (job := normalize(item))]
        logger.info(
            "jsearch.results",
            query=query.text(),
            page=query.page,
            num_pages=query.num_pages,
            count=len(jobs),
            # RapidAPI quota left on the plan (shows how many requests a call really used).
            quota_remaining=response.headers.get("x-ratelimit-requests-remaining"),
        )
        return jobs


def _items(body: Any) -> list[dict[str, Any]]:
    data = body.get("data") if isinstance(body, dict) else None
    if isinstance(data, dict):  # some API versions wrap the list
        data = data.get("jobs") or data.get("data")
    return [item for item in data or [] if isinstance(item, dict)]


def _text(value: Any) -> str | None:
    if value is None:
        return None
    text = " ".join(str(value).split()) if not isinstance(value, str) else value.strip()
    return text or None


def _decimal(value: Any) -> Decimal | None:
    if value in (None, ""):
        return None
    try:
        number = Decimal(str(value))
    except InvalidOperation:
        return None
    return number if number.is_finite() and abs(number) < Decimal("1e10") else None


def _domain(url: Any) -> str | None:
    text = _text(url)
    if not text:
        return None
    host = urlparse(text if "//" in text else f"https://{text}").netloc.lower()
    return host.removeprefix("www.") or None


def _posted(item: dict[str, Any]) -> datetime | None:
    iso = item.get("job_posted_at_datetime_utc")
    if isinstance(iso, str) and iso:
        try:
            parsed = datetime.fromisoformat(iso.replace("Z", "+00:00"))
            return parsed if parsed.tzinfo else parsed.replace(tzinfo=UTC)
        except ValueError:
            pass
    timestamp = item.get("job_posted_at_timestamp")
    if isinstance(timestamp, int | float) and timestamp > 0:
        return datetime.fromtimestamp(timestamp, UTC)
    return None


def stable_job_id(job_id: str) -> str:
    """search-v2 ids are base64("<stable id>:<per-request token>") — keep the stable part.

    Measured live (Phase 8): the same job came back with a new id on every call; only the
    part before ":" stayed the same. Classic `/search` ids have no token and are kept as is.
    """
    try:
        decoded = base64.urlsafe_b64decode(job_id + "=" * (-len(job_id) % 4)).decode("ascii")
    except (ValueError, UnicodeDecodeError):
        return job_id
    stable, separator, token = decoded.partition(":")
    return stable if separator and stable and token else job_id


def normalize(item: dict[str, Any]) -> NormalizedJob | None:
    """One JSearch result → NormalizedJob. Results without id, title or company are dropped."""
    raw_id = _text(item.get("job_id"))
    external_id = stable_job_id(raw_id) if raw_id else None
    title = _text(item.get("job_title"))
    company = _text(item.get("employer_name"))
    if not (external_id and title and company):
        return None
    city = _text(item.get("job_city"))
    country = _text(item.get("job_country"))
    location = _text(item.get("job_location")) or ", ".join(
        v for v in [city, _text(item.get("job_state")), country] if v
    )
    employment = item.get("job_employment_type") or item.get("job_employment_types")
    if isinstance(employment, list):
        employment = ", ".join(str(e) for e in employment)
    currency = _text(item.get("job_salary_currency"))
    return NormalizedJob(
        source="jsearch",
        external_id=external_id,
        title=title,
        company=company,
        company_domain=_domain(item.get("employer_website")),
        location=location or None,
        city=city,
        country=country.upper() if country and len(country) == 2 else None,
        is_remote=bool(item.get("job_is_remote")),
        employment_type=_text(employment),
        description=(item.get("job_description") or "").strip() or None,
        apply_url=_text(item.get("job_apply_link")),
        posted_at=_posted(item),
        salary_min=_decimal(item.get("job_min_salary")),
        salary_max=_decimal(item.get("job_max_salary")),
        salary_currency=currency.upper() if currency and len(currency) == 3 else None,
        raw=item,
    )
