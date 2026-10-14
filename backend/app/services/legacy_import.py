"""Import the legacy n8n Google Sheets from CSV exports (Phase 14, admin decision).

Two layouts are detected by their headers:
- **job list** (`discord-job-assistant-job-list`): Search Date, Job Title, Company, Location,
  Best Fit Role, Apply Link, Match Score, Matching Skills, Missing Skills → private jobs
  (source `legacy_sheet`, state *saved*). The sheet has no description: paste one later to
  score the job.
- **LinkedIn Leads** (legacy Module 8): email, author_name, author_headline, post_url,
  posted_at, job_title, company, location, post_text, status, sent_at … → private jobs
  (source `linkedin_post`, the post as description) + **pending** contacts (source
  `legacy_import`, post as evidence). Leads the old system already emailed say so in the
  evidence, so nobody is written to twice by accident.
Headers are matched loosely ("Job Title" = "job_title" = "title"). Re-importing the same
file adds nothing new.
"""

import csv
import hashlib
import io
import re
import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import ValidationAppError
from app.domain.contacts import FREE_MAIL, domain_of, excerpt, find_emails, is_valid_syntax
from app.domain.jobs import classify_description, dedupe_hash
from app.integrations.mail_dns import DomainChecker
from app.models.enums import (
    ContactSource,
    JobSource,
    JobVisibility,
    UserJobState,
)
from app.models.jobs import Job
from app.repositories.jobs import JobRepository, UserJobRepository
from app.repositories.outreach import ContactRepository, DoNotContactRepository
from app.services.contacts import UNKNOWN_COMPANY, _set_verification, verify_address

MAX_BYTES = 5 * 1024 * 1024
MAX_ROWS = 5000

# canonical field → accepted header spellings (lower-case, spaces/underscores ignored)
ALIASES: dict[str, tuple[str, ...]] = {
    "title": ("jobtitle", "title", "role", "position", "bestfitrole"),
    "company": ("company", "companyname", "employer"),
    "location": ("location", "city", "joblocation"),
    "url": ("applylink", "applyurl", "joblink", "url", "link", "posturl"),
    "posted": ("postedat", "dateposted", "posted", "searchdate", "date", "foundat"),
    "description": ("posttext", "description", "jobdescription", "jd", "jdsummary"),
    "email": ("email", "hremail", "contactemail", "recruiteremail"),
    "name": ("authorname", "name", "contactname", "recruiter", "hrname"),
    "headline": ("authorheadline", "headline", "contactrole", "designation"),
    "status": ("status",),
    "sent_at": ("sentat", "emailedat"),
    "score": ("matchscore", "score"),
    "matching": ("matchingskills", "skills"),
    "missing": ("missingskills",),
    "keyword": ("keyword",),
}


def _norm(header: str) -> str:
    return re.sub(r"[^a-z0-9]", "", header.lower())


def _columns(headers: list[str]) -> dict[str, str]:
    """canonical field → the CSV header that holds it (first match wins)."""
    normalised = {_norm(h): h for h in headers}
    found: dict[str, str] = {}
    for key, spellings in ALIASES.items():
        for spelling in spellings:
            if spelling in normalised:
                found[key] = normalised[spelling]
                break
    return found


def _date(value: str) -> datetime | None:
    value = (value or "").strip()
    if not value:
        return None
    for parse in (
        lambda v: datetime.fromisoformat(v.replace("Z", "+00:00")),
        lambda v: datetime.strptime(v, "%d/%m/%Y"),
        lambda v: datetime.strptime(v, "%m/%d/%Y"),
        lambda v: datetime.strptime(v, "%Y-%m-%d %H:%M:%S"),
    ):
        try:
            parsed = parse(value)
            return parsed if parsed.tzinfo else parsed.replace(tzinfo=UTC)
        except ValueError:
            continue
    return None


@dataclass
class ImportResult:
    kind: str = ""
    rows: int = 0
    jobs_created: int = 0
    jobs_existing: int = 0
    contacts_created: int = 0
    contacts_existing: int = 0
    already_emailed: int = 0
    skipped: list[str] = field(default_factory=list)

    def as_dict(self) -> dict[str, Any]:
        return {**self.__dict__, "skipped": self.skipped[:20], "skipped_count": len(self.skipped)}


def read_csv(data: bytes) -> tuple[list[str], list[dict[str, str]]]:
    if len(data) > MAX_BYTES:
        raise ValidationAppError("The file is larger than 5 MB.", code="FILE_TOO_LARGE")
    text = None
    for encoding in ("utf-8-sig", "cp1252"):
        try:
            text = data.decode(encoding)
            break
        except UnicodeDecodeError:
            continue
    if text is None:
        raise ValidationAppError("The file is not a readable CSV.", code="BAD_CSV")
    reader = csv.DictReader(io.StringIO(text))
    if not reader.fieldnames:
        raise ValidationAppError("The CSV has no header row.", code="BAD_CSV")
    rows = []
    for index, row in enumerate(reader):
        if index >= MAX_ROWS:
            break
        rows.append({k: (v or "").strip() for k, v in row.items() if k})
    return list(reader.fieldnames), rows


async def import_csv(
    session: AsyncSession, user_id: uuid.UUID, data: bytes, checker: DomainChecker
) -> ImportResult:
    headers, rows = read_csv(data)
    columns = _columns(headers)
    if "title" not in columns and "email" not in columns:
        raise ValidationAppError(
            "Not a job list or leads export: no 'Job Title' or 'email' column found.",
            code="UNKNOWN_CSV",
        )
    result = ImportResult(kind="leads" if "email" in columns else "jobs", rows=len(rows))
    jobs = JobRepository(session)
    user_jobs = UserJobRepository(session, owner_id=user_id)
    contacts = ContactRepository(session, owner_id=user_id)
    blocklist = await DoNotContactRepository(session, owner_id=user_id).blocklist()
    dns_cache: dict[str, bool | None] = {}

    def get(row: dict[str, str], key: str) -> str:
        header = columns.get(key)
        return row.get(header, "") if header else ""

    for number, row in enumerate(rows, start=2):  # row 1 is the header
        title = get(row, "title")
        text = get(row, "description")
        emails = find_emails(get(row, "email")) if result.kind == "leads" else []
        if result.kind == "leads" and not emails:
            result.skipped.append(f"Row {number}: no valid email")
            continue
        if not title and not text:
            result.skipped.append(f"Row {number}: no job title")
            continue
        company = get(row, "company") or UNKNOWN_COMPANY
        location = get(row, "location") or None
        url = get(row, "url") or None
        title = title or (get(row, "keyword") or "Job from LinkedIn post")
        source = JobSource.LINKEDIN_POST if result.kind == "leads" else JobSource.LEGACY_SHEET
        identity = url or f"{title}|{company}|{location or ''}"
        external_id = hashlib.sha256(f"{user_id}|{source.value}|{identity}".encode()).hexdigest()

        job = await jobs.by_external_id(source, external_id)
        if job is None:
            job = await jobs.insert_new(
                {
                    "source": source,
                    "external_id": external_id,
                    "visibility": JobVisibility.PRIVATE,
                    "created_by_user_id": user_id,
                    "title": title[:300],
                    "company": company[:200],
                    "location": location,
                    "is_remote": bool(location and "remote" in location.lower()),
                    "description": text or None,
                    "description_quality": classify_description(text),
                    "apply_url": url,
                    "posted_at": _date(get(row, "posted")),
                    "raw": {
                        "legacy": {
                            k: get(row, k)
                            for k in (
                                "score",
                                "matching",
                                "missing",
                                "status",
                                "sent_at",
                                "keyword",
                            )
                            if get(row, k)
                        }
                    },
                    "dedupe_hash": dedupe_hash(company, title, location),
                }
            )
            assert job is not None
            result.jobs_created += 1
        else:
            result.jobs_existing += 1
        link = await user_jobs.link(job.id)
        if link:  # newly in the list: keep it, imported jobs are not "new" noise
            user_job = await user_jobs.for_job(job.id)
            if user_job is not None:
                user_job.state = UserJobState.SAVED

        if result.kind == "leads":
            await _contacts(
                contacts, job, row, get, emails, blocklist, checker, dns_cache, result, number
            )
    await session.commit()
    return result


async def _contacts(
    contacts: ContactRepository,
    job: Job,
    row: dict[str, str],
    get: Any,
    emails: list[str],
    blocklist: Any,
    checker: DomainChecker,
    dns_cache: dict[str, bool | None],
    result: ImportResult,
    number: int,
) -> None:
    status = get(row, "status").upper()
    sent_at = get(row, "sent_at")
    emailed = status in ("SENT", "EMAILED", "DONE") or bool(sent_at)
    for email in emails:
        if blocklist.blocks(email) or not is_valid_syntax(email):
            result.skipped.append(f"Row {number}: {email} skipped (do-not-contact or invalid)")
            continue
        evidence = excerpt(get(row, "description"), email) or "Imported from the old system"
        if emailed:
            evidence = (
                f"Already emailed by the old system{' on ' + sent_at[:10] if sent_at else ''}. "
                + evidence
            )
            result.already_emailed += 1
        domain = domain_of(email)
        contact = await contacts.insert_new(
            {
                "job_id": job.id,
                "email": email,
                "name": get(row, "name") or None,
                "role_title": get(row, "headline") or None,
                "company": None if job.company == UNKNOWN_COMPANY else job.company,
                "company_domain": None if domain in FREE_MAIL else domain,
                "source": ContactSource.LEGACY_IMPORT,
                "source_url": get(row, "url") or None,
                "source_excerpt": evidence[:600],
            }
        )
        if contact is None:
            result.contacts_existing += 1
            continue
        _set_verification(contact, await verify_address(email, checker, dns_cache))
        result.contacts_created += 1
