"""Contacts (Module 07): LinkedIn hiring posts + manual entry, verification, approval.

A LinkedIn post that publishes an email becomes a private job (description = the post)
plus a contact with the post as evidence. Nothing is emailed until the user approves the
contact *and* the email (Phase 12 rule, inherited from the legacy Module 8).
"""

import csv
import hashlib
import io
import uuid
from collections.abc import Awaitable, Callable, Sequence
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any

import structlog
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import ConflictError, LimitExceededError, NotFoundError, ValidationAppError
from app.domain.contacts import (
    FREE_MAIL,
    TYPO_DOMAINS,
    domain_of,
    excerpt,
    find_emails,
    is_valid_syntax,
    normalize,
)
from app.domain.jobs import classify_description, dedupe_hash
from app.integrations.ai import AiClient
from app.integrations.apify import LinkedInPost, PostedLimit, PostSource, hiring_query
from app.integrations.mail_dns import DomainChecker
from app.models.enums import (
    ContactApproval,
    ContactSource,
    ContactVerification,
    DncSource,
    JobSource,
    JobVisibility,
)
from app.models.jobs import Job
from app.models.outreach import Contact, DoNotContact
from app.models.system import Task
from app.prompts import outreach as prompts
from app.prompts.outreach import PostDetails
from app.repositories.analyses import JobAnalysisRepository
from app.repositories.applications import ApplicationRepository
from app.repositories.jobs import JobRepository, UserJobRepository
from app.repositories.outreach import ContactFilters, ContactRepository, DoNotContactRepository
from app.repositories.profiles import UserSettingsRepository
from app.services.ai import AiService
from app.services.analysis import active_version
from app.services.job_export import BOM, safe_cell
from app.services.tasks import TaskDispatcher, TaskService
from app.services.usage import app_settings

logger = structlog.get_logger("app.contacts")

# A LinkedIn post that does not name the company. Checks skip it ("name the company").
UNKNOWN_COMPANY = "Company not stated"


def known_company(company: str | None) -> str:
    return "" if not company or company == UNKNOWN_COMPANY else company


EXPORT_LIMIT = 5000
DESCRIPTION_MAX = 32_000
EXPORT_COLUMNS = [
    ("Email", "email"),
    ("Name", "name"),
    ("Contact role", "contact_role"),
    ("Company", "company"),
    ("Job title", "job_title"),
    ("Location", "location"),
    ("Remote", "remote"),
    ("Date posted", "posted_at"),
    ("Match score", "match_score"),
    ("Approval", "approval"),
    ("Verification", "verification"),
    ("Do not contact", "do_not_contact"),
    ("Application", "application"),
    ("Applied", "applied_at"),
    ("Source", "source"),
    ("Post / source link", "source_url"),
    ("Evidence", "evidence"),
    ("Job link", "job_link"),
    ("Found", "found_at"),
    ("Description", "description"),
]


# ---------- verification ----------


async def verify_address(
    email: str, checker: DomainChecker, cache: dict[str, bool | None] | None = None
) -> ContactVerification:
    """Syntax + MX. `unverified` when DNS could not answer."""
    if not is_valid_syntax(email):
        return ContactVerification.INVALID
    domain = domain_of(email)
    if domain in FREE_MAIL:
        return ContactVerification.VALID
    if domain in TYPO_DOMAINS:
        return ContactVerification.RISKY
    if cache is not None and domain in cache:
        accepts = cache[domain]
    else:
        accepts = await checker.accepts_mail(domain)
        if cache is not None:
            cache[domain] = accepts
    if accepts is None:
        return ContactVerification.UNVERIFIED
    return ContactVerification.VALID if accepts else ContactVerification.INVALID


def _set_verification(contact: Contact, verification: ContactVerification) -> None:
    contact.verification = verification
    contact.verified_at = (
        datetime.now(UTC) if verification is not ContactVerification.UNVERIFIED else None
    )
    if verification is ContactVerification.INVALID and contact.approval is ContactApproval.APPROVED:
        contact.approval = ContactApproval.PENDING  # DB check: approved ⇒ not invalid
        contact.approved_at = None


# ---------- LinkedIn discovery (worker) ----------


@dataclass
class DiscoveryResult:
    posts: int = 0
    without_email: int = 0
    not_hiring: int = 0
    jobs: int = 0
    new_contacts: int = 0
    known_contacts: int = 0
    known_posts: int = 0  # seen before: no AI call made for them
    blocked: int = 0
    job_ids: list[str] = field(default_factory=list)
    stopped: str | None = None

    def as_dict(self) -> dict[str, Any]:
        return self.__dict__.copy()


TITLE_CHARS = 100


def _short(value: str) -> str:
    """Posts that list many roles produce very long "titles" (seen live) — keep them readable."""
    text = " ".join(value.split())
    return text if len(text) <= TITLE_CHARS else text[: TITLE_CHARS - 1].rsplit(" ", 1)[0] + "…"


def _post_external_id(user_id: uuid.UUID, post: LinkedInPost) -> str:
    return hashlib.sha256(f"{user_id}|{post.post_id}".encode()).hexdigest()


async def _post_job(
    session: AsyncSession,
    user_id: uuid.UUID,
    post: LinkedInPost,
    details: PostDetails,
    keyword: str,
) -> Job:
    """The post as a private job of this user (stored once per user and post)."""
    jobs = JobRepository(session)
    external_id = _post_external_id(user_id, post)
    job = await jobs.by_external_id(JobSource.LINKEDIN_POST, external_id)
    if job is None:
        title = _short(details.job_title) or keyword
        company = _short(details.company) or UNKNOWN_COMPANY
        location = details.location.strip() or None
        job = await jobs.insert_new(
            {
                "source": JobSource.LINKEDIN_POST,
                "external_id": external_id,
                "visibility": JobVisibility.PRIVATE,
                "created_by_user_id": user_id,
                "title": title,
                "company": company,
                "location": location,
                "is_remote": bool(location and "remote" in location.lower()),
                "description": post.text,
                "description_quality": classify_description(post.text),
                "apply_url": post.url,
                "posted_at": post.posted_at,
                "raw": {
                    "author_name": post.author_name,
                    "author_headline": post.author_headline,
                    "author_url": post.author_url,
                },
                "dedupe_hash": dedupe_hash(company, title, location),
            }
        )
        assert job is not None
    await UserJobRepository(session, owner_id=user_id).link(job.id)
    return job


async def discover_linkedin(
    session: AsyncSession,
    *,
    ai: AiClient,
    source: PostSource,
    checker: DomainChecker,
    user_id: uuid.UUID,
    keyword: str,
    max_posts: int,
    posted_limit: PostedLimit,
    progress: Callable[[int], Awaitable[None]],
) -> DiscoveryResult:
    result = DiscoveryResult()
    posts = await source.search(
        hiring_query(keyword), max_posts=max_posts, posted_limit=posted_limit
    )
    result.posts = len(posts)
    await progress(30)
    contacts = ContactRepository(session, owner_id=user_id)
    blocklist = await DoNotContactRepository(session, owner_id=user_id).blocklist()
    dns_cache: dict[str, bool | None] = {}
    with_email = [(post, find_emails(post.text)) for post in posts]
    result.without_email = sum(1 for _, emails in with_email if not emails)
    candidates = [(post, emails) for post, emails in with_email if emails]
    jobs = JobRepository(session)
    for index, (post, emails) in enumerate(candidates):
        # Seen before (same user, same post): its job and contacts exist — no AI call.
        known = await jobs.by_external_id(JobSource.LINKEDIN_POST, _post_external_id(user_id, post))
        if known is not None:
            result.known_posts += 1
            result.known_contacts += len(emails)
            result.job_ids.append(str(known.id))
            continue
        try:
            details = (
                await AiService(session, ai).complete_json(
                    user_id=user_id,
                    task_type="linkedin_post",
                    prompt_version=prompts.POST_VERSION,
                    messages=prompts.post_messages(
                        post.text, post.author_name, post.author_headline
                    ),
                    output=PostDetails,
                )
            ).data
        except LimitExceededError as exc:
            result.stopped = exc.message  # AI budget reached: keep what is done
            break
        if not details.is_hiring:
            result.not_hiring += 1
            continue
        job = await _post_job(session, user_id, post, details, keyword)
        added_here = 0
        for email in emails:
            if blocklist.blocks(email):
                result.blocked += 1
                continue
            domain = domain_of(email)
            contact = await contacts.insert_new(
                {
                    "job_id": job.id,
                    "email": email,
                    "name": details.contact_name.strip() or post.author_name,
                    "role_title": post.author_headline,
                    "company": details.company.strip() or None,
                    "company_domain": None if domain in FREE_MAIL else domain,
                    "source": ContactSource.LINKEDIN_POST,
                    "source_url": post.url,
                    "source_excerpt": excerpt(post.text, email),
                }
            )
            if contact is None:
                result.known_contacts += 1
                continue
            _set_verification(contact, await verify_address(email, checker, dns_cache))
            added_here += 1
        result.new_contacts += added_here
        result.jobs += 1
        result.job_ids.append(str(job.id))
        await session.commit()
        await progress(30 + int(65 * (index + 1) / max(1, len(candidates))))
    await session.commit()
    logger.info(
        "contacts.discovered",
        keyword=keyword,
        **{k: v for k, v in result.as_dict().items() if k != "job_ids"},
    )
    return result


# ---------- API side ----------


@dataclass(frozen=True)
class ContactView:
    contact: Contact
    job: Job | None
    blocked: bool = False


class ContactService:
    def __init__(
        self,
        session: AsyncSession,
        user_id: uuid.UUID,
        *,
        checker: DomainChecker,
        dispatcher: TaskDispatcher | None = None,
    ) -> None:
        self.session = session
        self.user_id = user_id
        self.checker = checker
        self.contacts = ContactRepository(session, owner_id=user_id)
        self.dnc = DoNotContactRepository(session, owner_id=user_id)
        self.dispatcher = dispatcher

    async def _get(self, contact_id: uuid.UUID) -> Contact:
        contact = await self.contacts.get(contact_id)
        if contact is None:
            raise NotFoundError("Contact not found.")
        return contact

    async def view(self, contact: Contact) -> ContactView:
        job = (
            await JobRepository(self.session).visible(contact.job_id, self.user_id)
            if contact.job_id
            else None
        )
        return ContactView(contact, job, await self.dnc.blocks(contact.email))

    async def list(
        self, filters: ContactFilters, *, page: int, page_size: int
    ) -> tuple[list[ContactView], int]:
        rows, total = await self.contacts.page(
            filters, limit=page_size, offset=(page - 1) * page_size
        )
        blocklist = await self.dnc.blocklist()
        return [ContactView(c, j, blocklist.blocks(c.email)) for c, j in rows], total

    async def counts(self) -> dict[str, int]:
        return await self.contacts.approval_counts()

    async def create(
        self,
        *,
        email: str,
        name: str | None,
        role_title: str | None,
        company: str | None,
        job_id: uuid.UUID | None,
        source_url: str | None = None,
    ) -> Contact:
        """Added by the user: approved straight away (they vouch for it) unless it is invalid."""
        address = normalize(email)
        if not is_valid_syntax(address):
            raise ValidationAppError("That is not a valid email address.", code="BAD_EMAIL")
        if await self.dnc.blocks(address):
            raise ConflictError(
                "That address is on your do-not-contact list.", code="DO_NOT_CONTACT"
            )
        if await self.contacts.by_email(address):
            raise ConflictError("You already have this contact.", code="CONTACT_EXISTS")
        job = None
        if job_id:
            job = await JobRepository(self.session).visible(job_id, self.user_id)
            if job is None:
                raise NotFoundError("Job not found.")
        verification = await verify_address(address, self.checker)
        if verification is ContactVerification.INVALID:
            raise ValidationAppError(
                f"The domain {domain_of(address)} does not accept email.",
                code="EMAIL_UNDELIVERABLE",
            )
        domain = domain_of(address)
        now = datetime.now(UTC)
        contact = await self.contacts.add(
            Contact(
                job_id=job.id if job else None,
                email=address,
                name=(name or "").strip() or None,
                role_title=(role_title or "").strip() or None,
                company=(company or "").strip() or (job.company if job else None),
                company_domain=None if domain in FREE_MAIL else domain,
                source=ContactSource.USER,
                source_url=(source_url or "").strip() or None,
                source_excerpt="Added by you",
                verification=verification,
                verified_at=now if verification is not ContactVerification.UNVERIFIED else None,
                approval=ContactApproval.APPROVED,
                approved_at=now,
            )
        )
        await self.session.commit()
        return contact

    async def update(self, contact_id: uuid.UUID, changes: dict[str, Any]) -> Contact:
        contact = await self._get(contact_id)
        for key in ("name", "role_title", "company"):
            if key in changes:
                setattr(contact, key, (changes[key] or "").strip() or None)
        if changes.get("approval") is not None:
            approval = ContactApproval(changes["approval"])
            if approval is ContactApproval.APPROVED:
                if contact.verification is ContactVerification.INVALID:
                    raise ConflictError(
                        "This address cannot receive email, so it cannot be approved.",
                        code="CONTACT_INVALID",
                    )
                if await self.dnc.blocks(contact.email):
                    raise ConflictError(
                        "This address is on your do-not-contact list.", code="DO_NOT_CONTACT"
                    )
            contact.approval = approval
            contact.approved_at = (
                datetime.now(UTC) if approval is ContactApproval.APPROVED else None
            )
        await self.session.commit()
        await self.session.refresh(contact)
        return contact

    async def reverify(self, contact_id: uuid.UUID) -> Contact:
        contact = await self._get(contact_id)
        _set_verification(contact, await verify_address(contact.email, self.checker))
        await self.session.commit()
        await self.session.refresh(contact)
        return contact

    async def delete(self, contact_id: uuid.UUID) -> None:
        contact = await self._get(contact_id)
        await self.session.delete(contact)
        await self.session.commit()

    async def export_csv(self, filters: ContactFilters) -> str:
        """Contacts with their job (Excel-safe CSV: BOM, formulas neutralised)."""
        rows, _ = await self.contacts.page(filters, limit=EXPORT_LIMIT, offset=0)
        blocklist = await self.dnc.blocklist()
        job_ids = [job.id for _, job in rows if job is not None]
        applications = await ApplicationRepository(self.session, owner_id=self.user_id).by_job_ids(
            job_ids
        )
        version = await active_version(self.session, self.user_id)
        scores = await JobAnalysisRepository(self.session, owner_id=self.user_id).best_for_jobs(
            job_ids, version.id if version else None
        )
        out = io.StringIO()
        writer = csv.writer(out, lineterminator="\r\n")
        writer.writerow([label for label, _ in EXPORT_COLUMNS])
        for contact, job in rows:
            application = applications.get(job.id) if job else None
            score = scores.get(job.id) if job else None
            values = {
                "email": contact.email,
                "name": contact.name,
                "contact_role": contact.role_title,
                "company": contact.company or (known_company(job.company) if job else None),
                "job_title": job.title if job else None,
                "location": job.location if job else None,
                "remote": job.is_remote if job else None,
                "posted_at": job.posted_at if job else None,
                "match_score": score.match_score if score else None,
                "approval": contact.approval.value,
                "verification": contact.verification.value,
                "do_not_contact": blocklist.blocks(contact.email),
                "application": application.status.value if application else None,
                "applied_at": application.applied_at if application else None,
                "source": contact.source.value,
                "source_url": contact.source_url,
                "evidence": contact.source_excerpt,
                "job_link": job.apply_url if job else None,
                "found_at": contact.created_at,
                # Excel keeps at most 32,767 characters per cell.
                "description": (job.description or "")[:DESCRIPTION_MAX] if job else None,
            }
            writer.writerow([safe_cell(values[key]) for _, key in EXPORT_COLUMNS])
        return BOM + out.getvalue()

    async def approved_for_job(self, job_id: uuid.UUID) -> Sequence[Contact]:
        rows, _ = await self.contacts.page(ContactFilters(job_id=job_id), limit=50, offset=0)
        return [c for c, _ in rows]

    # ---------- discovery ----------

    async def start_discovery(
        self, keyword: str, *, max_posts: int, posted_limit: PostedLimit
    ) -> Task:
        assert self.dispatcher is not None
        keyword = " ".join(keyword.split())
        if len(keyword) < 2:
            raise ValidationAppError("Enter a role or skill to search for.")
        user_settings = await UserSettingsRepository(
            self.session, owner_id=self.user_id
        ).get_or_create()
        if not user_settings.linkedin_source_enabled:
            raise ConflictError(
                "Turn on 'LinkedIn hiring posts' in Settings first.", code="LINKEDIN_DISABLED"
            )
        # Cost control (Phase 14): Apify bills per post; the admin caps posts per fetch.
        cap = (await app_settings(self.session)).apify_max_posts_per_fetch
        if max_posts > cap:
            raise ValidationAppError(
                f"A LinkedIn fetch can read at most {cap} posts.",
                code="TOO_MANY_POSTS",
                details={"max_posts": cap},
            )
        return await TaskService(self.session, self.user_id, self.dispatcher).create(
            "contact_discover",
            {"keyword": keyword, "max_posts": max_posts, "posted_limit": posted_limit},
        )

    # ---------- do-not-contact ----------

    async def blocked_list(self) -> Sequence[DoNotContact]:
        return await self.dnc.all()

    async def block(
        self, *, email: str | None, domain: str | None, reason: str | None
    ) -> DoNotContact:
        email = normalize(email) if email else None
        domain = (domain or "").strip().lstrip("@").lower() or None
        if bool(email) == bool(domain):
            raise ValidationAppError("Give either an email address or a domain.")
        if email and not is_valid_syntax(email):
            raise ValidationAppError("That is not a valid email address.", code="BAD_EMAIL")
        if domain and ("." not in domain or " " in domain):
            raise ValidationAppError("That is not a valid domain.", code="BAD_DOMAIN")
        existing = await self.dnc.find(email=email, domain=domain)
        if existing is not None:
            return existing
        entry = await self.dnc.add(
            DoNotContact(
                email=email,
                domain=domain,
                reason=(reason or "").strip() or None,
                source=DncSource.USER,
            )
        )
        # Contacts it covers stop being approved.
        rows, _ = await self.contacts.page(ContactFilters(), limit=10_000, offset=0)
        for contact, _ in rows:
            if (email and contact.email == email) or (
                domain and domain_of(contact.email) == domain
            ):
                contact.approval = ContactApproval.REJECTED
                contact.approved_at = None
        await self.session.commit()
        return entry

    async def unblock(self, entry_id: uuid.UUID) -> None:
        entry = await self.dnc.get(entry_id)
        if entry is None:
            raise NotFoundError("Entry not found.")
        await self.session.delete(entry)
        await self.session.commit()
