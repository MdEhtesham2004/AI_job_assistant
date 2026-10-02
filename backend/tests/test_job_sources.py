"""Phase 8 units: job rules, schedules, JSearch client, public page reading."""

import base64
import json
from datetime import UTC, datetime

import httpx
import pytest
import respx

from app.core.config import Settings
from app.core.errors import ExternalServiceError
from app.domain.jobs import Experience, JobQuery, classify_description, dedupe_hash
from app.domain.schedule import ScheduleError, is_due, next_run, validate_cron
from app.integrations import job_page
from app.integrations.job_page import PageFetchError, extract_description, fetch_job_description
from app.integrations.jsearch import (
    JobSourceConfigError,
    JSearchSource,
    normalize,
    stable_job_id,
)
from app.models.enums import DescriptionQuality
from tests.fakes import LONG_JD

SEARCH_URL = "https://jsearch.test/search-v2"


@pytest.fixture
def jsearch_settings(settings: Settings) -> Settings:
    return settings.model_copy(
        update={"jsearch_api_key": "test-key", "jsearch_base_url": "https://jsearch.test"}
    )


# ---------- rules ----------


def test_description_quality() -> None:
    assert classify_description(LONG_JD) is DescriptionQuality.COMPLETE
    assert classify_description("x" * 900) is DescriptionQuality.PARTIAL  # long, no sections
    assert classify_description("Build apps. " * 30) is DescriptionQuality.PARTIAL
    assert classify_description("Apply now!") is DescriptionQuality.MISSING
    assert classify_description(None) is DescriptionQuality.MISSING


def test_dedupe_hash_ignores_case_and_spacing() -> None:
    assert dedupe_hash("ACME  Apps", "React Native Dev", "Pune") == dedupe_hash(
        "acme apps", "react native  dev", "PUNE"
    )
    assert dedupe_hash("Acme", "Dev", "Pune") != dedupe_hash("Acme", "Dev", "Delhi")


def test_query_puts_location_into_the_text() -> None:
    assert JobQuery("React  Native", "Hyderabad").text() == "React Native in Hyderabad"
    assert JobQuery("React Native").text() == "React Native"


# ---------- schedules ----------


def test_cron_validation() -> None:
    assert validate_cron(" 0  8 * * * ", 60) == "0 8 * * *"
    with pytest.raises(ScheduleError, match="5-part"):
        validate_cron("daily", 60)
    with pytest.raises(ScheduleError, match="Invalid"):
        validate_cron("61 8 * * *", 60)
    with pytest.raises(ScheduleError, match="at most once every 60 minutes"):
        validate_cron("*/15 * * * *", 60)


def test_schedule_uses_the_users_time_zone() -> None:
    created = datetime(2026, 10, 2, 0, 0, tzinfo=UTC)  # 05:30 in India
    upcoming = next_run("0 8 * * *", created, "Asia/Kolkata")

    assert upcoming == datetime(2026, 10, 2, 2, 30, tzinfo=UTC)  # 08:00 IST
    assert not is_due(
        "0 8 * * *", created, datetime(2026, 10, 2, 2, 29, tzinfo=UTC), "Asia/Kolkata"
    )
    assert is_due("0 8 * * *", created, datetime(2026, 10, 2, 2, 31, tzinfo=UTC), "Asia/Kolkata")


# ---------- JSearch ----------

SAMPLE = {
    "job_id": "abc123",
    "job_title": "React Native Developer",
    "employer_name": "ABC Technologies",
    "employer_website": "https://www.abctech.com",
    "job_employment_type": "FULLTIME",
    "job_apply_link": "https://abctech.com/careers/1",
    "job_description": LONG_JD,
    "job_is_remote": False,
    "job_posted_at_datetime_utc": "2026-09-28T10:00:00.000Z",
    "job_city": "Hyderabad",
    "job_state": "Telangana",
    "job_country": "IN",
    "job_location": "Hyderabad, Telangana",
    "job_min_salary": 1200000,
    "job_max_salary": None,
}


def test_normalize_maps_jsearch_fields() -> None:
    job = normalize(SAMPLE)

    assert job is not None
    assert (job.external_id, job.title, job.company) == (
        "abc123",
        "React Native Developer",
        "ABC Technologies",
    )
    assert job.company_domain == "abctech.com"
    assert job.city == "Hyderabad" and job.country == "IN"
    assert job.posted_at == datetime(2026, 9, 28, 10, 0, tzinfo=UTC)
    assert str(job.salary_min) == "1200000" and job.salary_max is None
    assert job.description_quality is DescriptionQuality.COMPLETE
    assert normalize({**SAMPLE, "employer_name": ""}) is None  # unusable results are dropped


def test_search_v2_ids_keep_only_their_stable_part() -> None:
    def v2_id(token: str) -> str:
        return base64.b64encode(f"QXxYtznOLB_2MMtzAAAAAA==:{token}".encode()).decode()

    first = normalize({**SAMPLE, "job_id": v2_id("EswBCowBQUpp")})
    again = normalize({**SAMPLE, "job_id": v2_id("EssBCowBQUpp")})  # same job, next request

    assert first is not None and again is not None
    assert first.external_id == again.external_id == "QXxYtznOLB_2MMtzAAAAAA=="
    assert first.raw["job_id"] == v2_id("EswBCowBQUpp")  # original kept in raw
    assert stable_job_id("abc123") == "abc123"  # classic /search ids unchanged


@respx.mock
async def test_jsearch_sends_the_query_and_key(jsearch_settings: Settings) -> None:
    route = respx.get(SEARCH_URL).mock(
        return_value=httpx.Response(200, json={"status": "OK", "data": [SAMPLE, {"x": 1}]})
    )
    query = JobQuery(
        "React Native", "Hyderabad", Experience.UNDER_3_YEARS, remote_only=True, num_pages=2
    )

    jobs = await JSearchSource(jsearch_settings).search(query)

    assert [j.external_id for j in jobs] == ["abc123"]
    request = route.calls.last.request
    assert request.headers["x-rapidapi-key"] == "test-key"
    assert request.headers["x-rapidapi-host"] == "jsearch.test"
    params = dict(request.url.params)
    assert params["query"] == "React Native in Hyderabad"
    assert params["country"] == "in" and params["date_posted"] == "week"
    assert params["num_pages"] == "2"
    assert params["work_from_home"] == "true"
    assert params["job_requirements"] == "under_3_years_experience"


@respx.mock
async def test_jsearch_accepts_wrapped_results(jsearch_settings: Settings) -> None:
    respx.get(SEARCH_URL).mock(return_value=httpx.Response(200, json={"data": {"jobs": [SAMPLE]}}))

    assert len(await JSearchSource(jsearch_settings).search(JobQuery("x y"))) == 1


@respx.mock
@pytest.mark.parametrize(
    ("status", "error", "code"),
    [
        (401, JobSourceConfigError, "JOB_SOURCE_UNAVAILABLE"),
        (429, JobSourceConfigError, "JSEARCH_QUOTA"),
        (503, ExternalServiceError, "EXTERNAL_SERVICE_ERROR"),  # retried by the worker
    ],
)
async def test_jsearch_errors(
    jsearch_settings: Settings, status: int, error: type[Exception], code: str
) -> None:
    respx.get(SEARCH_URL).mock(return_value=httpx.Response(status, json={}))

    with pytest.raises(error) as exc:
        await JSearchSource(jsearch_settings).search(JobQuery("x y"))

    assert exc.value.code == code  # type: ignore[attr-defined]


async def test_jsearch_without_key(settings: Settings) -> None:
    with pytest.raises(JobSourceConfigError) as exc:
        await JSearchSource(settings.model_copy(update={"jsearch_api_key": ""})).search(
            JobQuery("x y")
        )
    assert exc.value.code == "JSEARCH_NOT_CONFIGURED"


# ---------- public page ----------


def test_extract_prefers_json_ld_job_posting() -> None:
    posting = {
        "@context": "https://schema.org",
        "@type": "JobPosting",
        "description": "<p>Build apps</p><ul><li>React</li></ul>",
    }
    html = (
        "<html><body><nav>Menu</nav><main>Other text</main>"
        f'<script type="application/ld+json">{json.dumps({"@graph": [posting]})}</script>'
        "</body></html>"
    )

    assert extract_description(html) == "Build apps\n\nReact"


def test_extract_falls_back_to_main_text() -> None:
    html = (
        "<html><head><style>.x{}</style></head><body><header>Logo</header>"
        "<main><h1>Developer</h1><p>Responsibilities: ship apps.</p><script>x()</script></main>"
        "<footer>(c)</footer></body></html>"
    )

    text = extract_description(html)

    assert "Responsibilities: ship apps." in text
    assert "Logo" not in text and "x()" not in text and "(c)" not in text


async def test_private_addresses_are_refused(settings: Settings) -> None:
    with pytest.raises(PageFetchError, match="private network"):
        await fetch_job_description("http://127.0.0.1/job", settings)
    with pytest.raises(PageFetchError, match="not a web address"):
        await fetch_job_description("file:///etc/passwd", settings)


@respx.mock
async def test_robots_txt_is_respected(settings: Settings, monkeypatch: pytest.MonkeyPatch) -> None:
    async def public(url: str) -> None:
        return None

    monkeypatch.setattr(job_page, "_check_public", public)
    respx.get("https://careers.test/robots.txt").mock(
        return_value=httpx.Response(200, text="User-agent: *\nDisallow: /jobs/")
    )
    page = respx.get("https://careers.test/jobs/1").mock(return_value=httpx.Response(200))

    with pytest.raises(PageFetchError, match="robots.txt"):
        await fetch_job_description("https://careers.test/jobs/1", settings)
    assert not page.called


@respx.mock
async def test_page_is_read_when_allowed(
    settings: Settings, monkeypatch: pytest.MonkeyPatch
) -> None:
    async def public(url: str) -> None:
        return None

    monkeypatch.setattr(job_page, "_check_public", public)
    respx.get("https://careers.test/robots.txt").mock(return_value=httpx.Response(404))
    respx.get("https://careers.test/jobs/1").mock(
        return_value=httpx.Response(
            200,
            html=f"<html><body><article><p>{LONG_JD}</p></article></body></html>",
        )
    )

    text = await fetch_job_description("https://careers.test/jobs/1", settings)

    assert text.startswith("Responsibilities: build and ship")


@respx.mock
async def test_login_walls_are_reported(
    settings: Settings, monkeypatch: pytest.MonkeyPatch
) -> None:
    async def public(url: str) -> None:
        return None

    monkeypatch.setattr(job_page, "_check_public", public)
    respx.get("https://careers.test/robots.txt").mock(return_value=httpx.Response(404))
    respx.get("https://careers.test/jobs/1").mock(return_value=httpx.Response(403))

    with pytest.raises(PageFetchError, match="login"):
        await fetch_job_description("https://careers.test/jobs/1", settings)
