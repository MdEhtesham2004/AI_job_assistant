"""Phase 14 cost control: shared cache, per-user quotas, usage log, admin view."""

import asyncio
import uuid
from pathlib import Path

import pytest
from fakeredis.aioredis import FakeRedis
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.core.config import Settings
from app.core.errors import LimitExceededError
from app.db.session import create_engine, create_session_factory
from app.integrations.apify import LinkedInPost
from app.services.usage import Meter
from app.workers.runner import Outcome, run_task
from tests.fakes import FakeJobSource, fake_services, make_job
from tests.helpers import db, make_user, set_platform

API = "/api/v1/jobs"


def _run(
    app: FastAPI,
    settings: Settings,
    task_id: str,
    tmp_path: Path,
    source: FakeJobSource,
    redis: FakeRedis,
) -> Outcome:
    async def go() -> Outcome:
        engine = create_engine(settings)
        services = fake_services(
            settings, tmp_path, storage=app.state.storage, job_source=source, redis=redis
        )
        result = await run_task(
            uuid.UUID(task_id),
            settings,
            services=services,
            session_factory=create_session_factory(engine),
        )
        await engine.dispose()
        return result.outcome

    return asyncio.run(go())


def _search(client: TestClient, headers: dict[str, str], keywords: str = "React Native") -> dict:
    response = client.post(f"{API}/search", json={"keywords": keywords}, headers=headers)
    assert response.status_code == 202, response.text
    return response.json()


def test_identical_search_by_another_user_uses_the_shared_cache(
    app: FastAPI, client: TestClient, migrated_database: str, settings: Settings, tmp_path: Path
) -> None:
    _, alice = make_user(client, migrated_database, "alice@example.com")
    _, bob = make_user(client, migrated_database, "bob@example.com")
    source, redis = FakeJobSource([make_job(1), make_job(2)]), FakeRedis(decode_responses=True)

    first = _search(client, alice)
    assert _run(app, settings, first["task_id"], tmp_path, source, redis) is Outcome.SUCCEEDED
    # Different spacing/case is the same query.
    second = _search(client, bob, "  react   NATIVE ")
    assert _run(app, settings, second["task_id"], tmp_path, source, redis) is Outcome.SUCCEEDED

    assert len(source.queries) == 1  # JSearch was called once for both users
    bob_run = client.get(f"{API}/searches/{second['run_id']}", headers=bob).json()
    assert (bob_run["results_count"], bob_run["new_jobs_count"]) == (2, 2)
    rows = db(
        migrated_database,
        "SELECT u.email, p.cached, p.units, p.results FROM provider_calls p "
        "JOIN users u ON u.id = p.user_id ORDER BY p.created_at",
    )
    assert rows == [("alice@example.com", False, 1, 2), ("bob@example.com", True, 0, 2)]

    alice_usage = client.get("/api/v1/usage", headers=alice).json()
    bob_usage = client.get("/api/v1/usage", headers=bob).json()
    assert alice_usage["jsearch_month"] == {"used": 1, "limit": 60, "left": 59}
    assert bob_usage["jsearch_month"]["used"] == 0  # cache hits are free
    assert bob_usage["cached_hits_month"] == 1


def test_monthly_search_quota_blocks_new_searches_but_not_cached_ones(
    app: FastAPI, client: TestClient, migrated_database: str, settings: Settings, tmp_path: Path
) -> None:
    _, alice = make_user(client, migrated_database, "alice@example.com")
    set_platform(migrated_database, jsearch_requests_per_month=1)
    source, redis = FakeJobSource([make_job(1)]), FakeRedis(decode_responses=True)

    used = _search(client, alice, "Python")
    assert _run(app, settings, used["task_id"], tmp_path, source, redis) is Outcome.SUCCEEDED
    blocked = _search(client, alice, "Golang")
    assert _run(app, settings, blocked["task_id"], tmp_path, source, redis) is Outcome.FAILED
    run = client.get(f"{API}/searches/{blocked['run_id']}", headers=alice).json()
    assert run["status"] == "failed"
    assert "1 of your 1 job-search requests" in run["error"]

    # A search someone already ran is served from the cache, even with the quota used up.
    cached = _search(client, alice, "Python")
    assert _run(app, settings, cached["task_id"], tmp_path, source, redis) is Outcome.SUCCEEDED
    assert len(source.queries) == 1  # no API call for the blocked or the cached search
    (failed,) = db(migrated_database, "SELECT count(*) FROM provider_calls WHERE NOT success")[0]
    assert failed == 0  # quota refusals are not provider calls


class CountingPosts:
    """Returns one post per call, or as many as asked for (`fill=True`)."""

    def __init__(self, *, fill: bool = False) -> None:
        self.fill = fill
        self.calls: list[tuple[str, int, str]] = []

    async def search(self, query: str, *, max_posts: int, posted_limit: str) -> list[LinkedInPost]:
        self.calls.append((query, max_posts, posted_limit))
        n = len(self.calls)
        return [
            LinkedInPost(
                f"p{n}-{i}", "https://linkedin.example/p", "hiring", None, None, None, None
            )
            for i in range(max_posts if self.fill else 1)
        ]


def _meter_run(settings: Settings, user_id: str, coro_factory) -> object:  # type: ignore[no-untyped-def]
    async def go() -> object:
        engine = create_engine(settings)
        factory = create_session_factory(engine)
        try:
            async with factory() as session:
                return await coro_factory(session)
        finally:
            await engine.dispose()

    return asyncio.run(go())


def test_apify_cache_recent_keyword_window_and_daily_quota(
    client: TestClient, migrated_database: str, settings: Settings
) -> None:
    user_id, _ = make_user(client, migrated_database, "alice@example.com")
    set_platform(migrated_database, apify_runs_per_day=2)
    posts, redis = CountingPosts(), FakeRedis(decode_responses=True)

    async def fetch(session, *, posted: str = "week", max_posts: int = 15):  # type: ignore[no-untyped-def]
        meter = Meter(session, settings, redis, uuid.UUID(user_id))
        return await meter.linkedin(
            posts, '"Hiring" AND "python"', max_posts=max_posts, posted_limit=posted
        )

    _meter_run(settings, user_id, fetch)
    _meter_run(settings, user_id, fetch)  # same query within 24 h: cache
    assert posts.calls == [('"Hiring" AND "python"', 15, "week")]

    # A new real fetch of a recently fetched keyword only looks at the last 24 h.
    _meter_run(settings, user_id, lambda s: fetch(s, max_posts=10))
    assert posts.calls[-1] == ('"Hiring" AND "python"', 10, "24h")

    # Two real fetches today = the daily limit.
    with pytest.raises(LimitExceededError, match="2 of your 2 LinkedIn fetches today"):
        _meter_run(settings, user_id, lambda s: fetch(s, max_posts=20))
    assert len(posts.calls) == 2


def test_admin_sets_quotas_and_sees_provider_usage(
    app: FastAPI, client: TestClient, migrated_database: str, settings: Settings, tmp_path: Path
) -> None:
    _, admin = make_user(client, migrated_database, "admin@example.com", role="admin")
    _, user = make_user(client, migrated_database, "user@example.com")

    assert (
        client.patch(
            "/api/v1/admin/platform", json={"jsearch_requests_per_month": 5}, headers=user
        ).status_code
        == 403
    )
    changed = client.patch(
        "/api/v1/admin/platform",
        json={"jsearch_requests_per_month": 5, "apify_runs_per_day": 0},
        headers=admin,
    )
    assert changed.status_code == 200, changed.text
    assert changed.json() == {
        "automation_fetch_enabled": False,
        "jsearch_requests_per_month": 5,
        "apify_posts_per_month": 300,
        "apify_runs_per_day": 0,
        "apify_max_posts_per_fetch": 25,
        "jsearch_max_pages": 1,
        "jsearch_allow_load_more": True,
    }
    assert (
        client.patch(
            "/api/v1/admin/platform", json={"apify_posts_per_month": -1}, headers=admin
        ).status_code
        == 422
    )
    (audit,) = db(migrated_database, "SELECT data FROM audit_logs WHERE action = 'platform.quotas'")
    assert audit[0] == {"jsearch_requests_per_month": 5, "apify_runs_per_day": 0}

    source, redis = FakeJobSource([make_job(1)]), FakeRedis(decode_responses=True)
    for headers in (user, admin):
        started = _search(client, headers)
        assert _run(app, settings, started["task_id"], tmp_path, source, redis) is Outcome.SUCCEEDED

    data = client.get("/api/v1/admin/analytics", headers=admin).json()
    (jsearch,) = data["providers"]
    assert (jsearch["provider"], jsearch["calls"], jsearch["cache_hits"]) == ("jsearch", 1, 1)
    assert jsearch["cache_rate"] == 0.5
    by_email = {u["email"]: u["jsearch_requests_month"] for u in data["users"]}
    assert by_email == {"user@example.com": 1, "admin@example.com": 0}
    usage = client.get("/api/v1/usage", headers=user).json()
    assert usage["jsearch_month"] == {"used": 1, "limit": 5, "left": 4}
    assert usage["apify_today"]["limit"] == 0  # 0 = unlimited
    assert usage["apify_today"]["left"] is None
    assert (usage["max_jobs_per_search"], usage["load_more_allowed"]) == (10, True)
    assert usage["max_posts_per_fetch"] == 25
    assert usage["apify_month"] == {"used": 0, "limit": 300, "left": 300}
    bad = client.patch("/api/v1/admin/platform", json={"jsearch_max_pages": 4}, headers=admin)
    assert bad.status_code == 422


def test_linkedin_posts_are_capped_per_fetch_and_by_the_monthly_posts_left(
    client: TestClient, migrated_database: str, settings: Settings
) -> None:
    user_id, user = make_user(client, migrated_database, "alice@example.com")
    set_platform(migrated_database, apify_posts_per_month=30, apify_max_posts_per_fetch=25)
    posts, redis = CountingPosts(fill=True), FakeRedis(decode_responses=True)

    def fetch(keyword: str, max_posts: int) -> object:
        async def go(session):  # type: ignore[no-untyped-def]
            meter = Meter(session, settings, redis, uuid.UUID(user_id))
            return await meter.linkedin(posts, keyword, max_posts=max_posts, posted_limit="week")

        return _meter_run(settings, user_id, go)

    fetch("python", 100)  # automation-style request above the cap → 25
    fetch("golang", 25)  # only 5 posts left this month → asks Apify for 5
    assert [count for _, count, _ in posts.calls] == [25, 5]
    with pytest.raises(LimitExceededError, match="30 of your 30 LinkedIn posts this month"):
        fetch("rust", 25)
    assert len(posts.calls) == 2
    usage = client.get("/api/v1/usage", headers=user).json()
    assert usage["apify_month"] == {"used": 30, "limit": 30, "left": 0}

    # Asking the API for more posts than the admin allows is refused up front.
    client.patch("/api/v1/users/me/settings", json={"linkedin_source_enabled": True}, headers=user)
    too_many = client.post(
        "/api/v1/contacts/discover", json={"keyword": "React", "max_posts": 50}, headers=user
    )
    assert too_many.status_code == 422
    assert too_many.json()["error"]["code"] == "TOO_MANY_POSTS"
