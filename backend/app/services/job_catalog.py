"""Store normalized jobs in the shared catalog and link them to the user (Module 02).

Dedupe, in order:
1. same source + external id → the existing row is refreshed (`last_seen_at`, fields);
2. same company + title + city as an active job seen within `job_dedupe_days` → stored
   as `duplicate` pointing at that job, and the user is linked to the original.
"""

import uuid
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.jobs import NormalizedJob, classify_description
from app.models.enums import JobSource, JobStatus
from app.models.jobs import Job
from app.repositories.jobs import JobRepository, JobSearchRunRepository, UserJobRepository


@dataclass(frozen=True)
class StoreResult:
    results: int
    new_for_user: int
    new_in_catalog: int


async def upsert_job(session: AsyncSession, item: NormalizedJob, dedupe_days: int) -> Job:
    """The catalog job this result belongs to (the original when it is a duplicate)."""
    jobs = JobRepository(session)
    now = datetime.now(UTC)
    source = JobSource(item.source)
    existing = await jobs.by_external_id(source, item.external_id)
    if existing is not None:
        existing.last_seen_at = now
        existing.title, existing.company = item.title, item.company
        existing.apply_url = item.apply_url or existing.apply_url
        existing.posted_at = item.posted_at or existing.posted_at
        if len(item.description or "") > len(existing.description or ""):
            existing.description = item.description
            existing.description_quality = classify_description(item.description)
        existing.raw = item.raw
        await session.flush()
        return await _canonical(session, existing)

    original = await jobs.canonical_for(item.dedupe_hash, now - timedelta(days=dedupe_days))
    created = await jobs.insert_new(
        {
            "source": source,
            "external_id": item.external_id,
            "title": item.title,
            "company": item.company,
            "company_domain": item.company_domain,
            "location": item.location,
            "city": item.city,
            "country": item.country,
            "is_remote": item.is_remote,
            "employment_type": item.employment_type,
            "description": item.description,
            "description_quality": item.description_quality,
            "apply_url": item.apply_url,
            "posted_at": item.posted_at,
            "salary_min": item.salary_min,
            "salary_max": item.salary_max,
            "salary_currency": item.salary_currency,
            "raw": item.raw,
            "dedupe_hash": item.dedupe_hash,
            "status": JobStatus.DUPLICATE if original else JobStatus.ACTIVE,
            "duplicate_of_id": original.id if original else None,
            "first_seen_at": now,
            "last_seen_at": now,
        }
    )
    if created is None:  # inserted concurrently by another worker
        raced = await jobs.by_external_id(source, item.external_id)
        assert raced is not None
        return await _canonical(session, raced)
    return original or created


async def _canonical(session: AsyncSession, job: Job) -> Job:
    if job.status is JobStatus.DUPLICATE and job.duplicate_of_id:
        original = await session.get(Job, job.duplicate_of_id)
        if original is not None:
            return original
    return job


async def store_results(
    session: AsyncSession,
    user_id: uuid.UUID,
    run_id: uuid.UUID,
    items: list[NormalizedJob],
    *,
    dedupe_days: int,
) -> StoreResult:
    user_jobs = UserJobRepository(session, owner_id=user_id)
    runs = JobSearchRunRepository(session, owner_id=user_id)
    added = 0
    new_for_user = 0
    rank = await runs.result_count(run_id)  # "load more" continues after earlier pages
    catalog_before = await JobRepository(session).count()
    for item in items:
        job = await upsert_job(session, item, dedupe_days)
        is_new = await user_jobs.link(job.id)
        # Skips results that collapsed into a job this run already has.
        if not await runs.add_result(run_id, job.id, rank + 1, is_new=is_new):
            continue
        rank += 1
        added += 1
        new_for_user += is_new
    catalog_after = await JobRepository(session).count()
    return StoreResult(added, new_for_user, catalog_after - catalog_before)
