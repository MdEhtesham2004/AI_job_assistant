"""LinkedIn hiring posts via the Apify actor `harvestapi/linkedin-post-search`.

The actor runs on Apify's infrastructure without the user's LinkedIn account and returns
public posts. We keep only posts in which the author published an email address.
"""

from dataclasses import dataclass
from datetime import datetime
from typing import Any, Literal, Protocol

import httpx
import structlog

from app.core.config import Settings
from app.core.errors import AppError, ExternalServiceError

logger = structlog.get_logger("app.apify")

PostedLimit = Literal["24h", "week", "month"]


class ApifyConfigError(AppError):
    """Not worth retrying: missing/invalid token or no credit left."""

    status_code = 502
    code = "APIFY_UNAVAILABLE"


@dataclass(frozen=True)
class LinkedInPost:
    post_id: str
    url: str
    text: str
    author_name: str | None
    author_headline: str | None
    author_url: str | None
    posted_at: datetime | None


class PostSource(Protocol):
    async def search(
        self, query: str, *, max_posts: int, posted_limit: PostedLimit
    ) -> list[LinkedInPost]: ...


def hiring_query(keyword: str) -> str:
    """Same query as the legacy Module 8: posts that say "hiring", the role and gmail.com."""
    clean = " ".join(keyword.replace('"', " ").split())
    return f'"Hiring" AND "{clean}" AND "gmail.com"'


def _date(value: Any) -> datetime | None:
    raw = value.get("date") if isinstance(value, dict) else value
    if not raw:
        return None
    try:
        return datetime.fromisoformat(str(raw).replace("Z", "+00:00"))
    except ValueError:
        return None


def parse_post(item: dict[str, Any]) -> LinkedInPost | None:
    text = str(item.get("content") or "").strip()
    url = str(item.get("linkedinUrl") or item.get("url") or "")
    if not text or not url:
        return None
    raw_author = item.get("author")
    author: dict[str, Any] = raw_author if isinstance(raw_author, dict) else {}
    return LinkedInPost(
        post_id=str(item.get("id") or url),
        url=url,
        text=text[:6000],
        author_name=(author.get("name") or None),
        author_headline=(author.get("info") or author.get("headline") or None),
        author_url=(author.get("linkedinUrl") or author.get("url") or None),
        posted_at=_date(item.get("postedAt")),
    )


class ApifyPostSource:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings

    async def search(
        self, query: str, *, max_posts: int, posted_limit: PostedLimit
    ) -> list[LinkedInPost]:
        if not self.settings.apify_configured:
            raise ApifyConfigError(
                "LinkedIn post search is not configured (APIFY_TOKEN is missing).",
                code="APIFY_NOT_CONFIGURED",
            )
        url = (
            f"{self.settings.apify_base_url.rstrip('/')}/v2/acts/"
            f"{self.settings.apify_linkedin_actor}/run-sync-get-dataset-items"
        )
        payload = {
            "searchQueries": [query],
            "maxPosts": max_posts,
            "postedLimit": posted_limit,
            "sortBy": "date",
        }
        try:
            async with httpx.AsyncClient(timeout=self.settings.apify_timeout_seconds) as client:
                response = await client.post(
                    url,
                    json=payload,
                    headers={"Authorization": f"Bearer {self.settings.apify_token}"},
                )
        except httpx.HTTPError as exc:
            raise ExternalServiceError(
                "Apify is unreachable.", details={"provider": "apify"}
            ) from exc
        if response.status_code in (401, 403):
            raise ApifyConfigError("Apify rejected the token (check APIFY_TOKEN).")
        if response.status_code == 402:
            raise ApifyConfigError("Apify has no credit left for this run.", code="APIFY_NO_CREDIT")
        if response.status_code not in (200, 201):
            raise ExternalServiceError(
                "Apify returned an error.",
                details={"provider": "apify", "status": response.status_code},
            )
        body = response.json()
        items = body if isinstance(body, list) else []
        posts = [post for item in items if isinstance(item, dict) and (post := parse_post(item))]
        logger.info("apify.posts", query=query, returned=len(items), usable=len(posts))
        return posts
