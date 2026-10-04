"""Automation (Phase 13): everything up to the user's approval — only when the user asks.

Two modes (admin decision 2026-10-03):
- **saved** (always available, no Apify): jobs already in the user's list that have an
  approved contact and no application → match score (reused when it exists) → (≥ minimum)
  tailored resume when the analysis says so + cover letter → email application → AI draft.
- **fetch** (calls Apify — locked until an admin enables it in Settings › Platform):
  LinkedIn hiring posts for the user's keywords → private jobs + pending contacts, then the
  same steps for those new jobs and the saved ones.
There is no schedule: a run starts only from "Automate" in the Outbox. Capped per run;
nothing is ever sent by itself.
"""

import uuid
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any, Literal

import structlog
from sqlalchemy import exists, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings
from app.core.errors import AppError, ConflictError, LimitExceededError, PermissionDeniedError
from app.integrations.ai import AiClient
from app.integrations.apify import PostSource
from app.integrations.gotenberg import GotenbergClient
from app.integrations.mail_dns import DomainChecker
from app.integrations.storage import Storage
from app.models.accounts import UserSettings
from app.models.applications import Application
from app.models.enums import (
    AnalysisDecision,
    ApplicationChannel,
    ContactApproval,
    ContactVerification,
    NotificationSeverity,
    ParseStatus,
    UserJobState,
)
from app.models.jobs import Job, UserJob
from app.models.outreach import Contact
from app.models.resumes import ResumeVersion
from app.models.system import AppSettings, Task
from app.repositories.analyses import JobAnalysisRepository
from app.repositories.applications import ApplicationRepository
from app.repositories.jobs import JobRepository, UserJobRepository
from app.repositories.outreach import ContactFilters, ContactRepository, DoNotContactRepository
from app.repositories.profiles import UserSettingsRepository
from app.repositories.tasks import TaskRepository
from app.services.analysis import active_version, analyze_job, can_score
from app.services.applications import ApplicationService
from app.services.contacts import discover_linkedin
from app.services.documents import generate_cover_letter, generate_tailored
from app.services.gmail_account import GmailAccountService
from app.services.notifications import notify
from app.services.outreach import generate_draft
from app.services.tasks import TaskDispatcher, TaskService

logger = structlog.get_logger("app.automation")

Mode = Literal["saved", "fetch"]
MAX_KEYWORDS = 5
HIDDEN_STATES = (UserJobState.SKIPPED, UserJobState.ARCHIVED)


@dataclass
class RunResult:
    mode: str = "saved"
    keywords: list[str] = field(default_factory=list)
    posts: int = 0
    new_contacts: int = 0
    empty_keywords: list[str] = field(default_factory=list)  # searches that found nothing
    candidates: int = 0
    scored: int = 0
    reused_scores: int = 0
    below_minimum: int = 0
    prepared: int = 0
    skipped: list[str] = field(default_factory=list)
    stopped: str | None = None

    def as_dict(self) -> dict[str, Any]:
        return self.__dict__.copy()


@dataclass(frozen=True)
class Tools:
    settings: Settings
    ai: AiClient
    gotenberg: GotenbergClient
    storage: Storage
    posts: PostSource
    domains: DomainChecker


# ---------- platform switch (admin only) ----------


async def app_settings(session: AsyncSession) -> AppSettings:
    row = await session.get(AppSettings, 1)
    if row is None:  # created by migration 0013; tests truncate tables
        row = AppSettings(id=1)
        session.add(row)
        await session.flush()
    return row


async def fetch_allowed(session: AsyncSession) -> bool:
    return (await app_settings(session)).automation_fetch_enabled


# ---------- candidates ----------


async def _contact_for(
    session: AsyncSession, user_id: uuid.UUID, job_id: uuid.UUID, *, approved_only: bool
) -> Contact | None:
    rows, _ = await ContactRepository(session, owner_id=user_id).page(
        ContactFilters(job_id=job_id), limit=20, offset=0
    )
    blocklist = await DoNotContactRepository(session, owner_id=user_id).blocklist()
    usable = [
        c
        for c, _ in rows
        if c.verification is not ContactVerification.INVALID
        and not blocklist.blocks(c.email)
        and (
            c.approval is ContactApproval.APPROVED
            if approved_only
            else c.approval is not ContactApproval.REJECTED
        )
    ]
    usable.sort(key=lambda c: c.approval is not ContactApproval.APPROVED)  # approved first
    return usable[0] if usable else None


async def saved_job_ids(session: AsyncSession, user_id: uuid.UUID) -> list[uuid.UUID]:
    """Jobs in the user's list (not skipped/archived) with an approved, usable contact and
    no application yet — newest first."""
    has_application = exists().where(Application.user_id == user_id, Application.job_id == Job.id)
    rows = await session.scalars(
        select(Job.id)
        .join(UserJob, (UserJob.job_id == Job.id) & (UserJob.user_id == user_id))
        .join(Contact, (Contact.job_id == Job.id) & (Contact.user_id == user_id))
        .where(
            UserJob.state.not_in(HIDDEN_STATES),
            Contact.approval == ContactApproval.APPROVED,
            Contact.verification != ContactVerification.INVALID,
            ~has_application,
        )
        .group_by(Job.id, Job.created_at)
        .order_by(Job.created_at.desc())
    )
    blocklist = await DoNotContactRepository(session, owner_id=user_id).blocklist()
    ready: list[uuid.UUID] = []
    for job_id in rows.all():
        contact = await _contact_for(session, user_id, job_id, approved_only=True)
        if contact is not None and not blocklist.blocks(contact.email):
            ready.append(job_id)
    return ready


# ---------- readiness ----------


async def not_ready_reason(
    session: AsyncSession, settings: Settings, user_id: uuid.UUID
) -> str | None:
    version = await active_version(session, user_id)
    if version is None or version.parse_status is not ParseStatus.PARSED:
        return "Upload a resume and wait until it is parsed."
    try:
        await GmailAccountService(session, user_id, settings).connected()
    except AppError as exc:
        return exc.message
    return None


def fetch_problem(user_settings: UserSettings) -> str | None:
    if not user_settings.automation_keywords:
        return "Add at least one keyword in Settings › Automation."
    if not user_settings.linkedin_source_enabled:
        return "Turn on 'LinkedIn hiring posts' in Settings."
    return None


# ---------- the run ----------


async def run_pipeline(
    session: AsyncSession,
    tools: Tools,
    user_id: uuid.UUID,
    progress: Callable[[int], Awaitable[None]],
    mode: Mode = "saved",
) -> RunResult:
    result = RunResult(mode=mode)
    user_settings = await UserSettingsRepository(session, owner_id=user_id).get_or_create()
    reason = await not_ready_reason(session, tools.settings, user_id)
    if reason:
        result.stopped = reason
        return result
    version = await active_version(session, user_id)
    assert version is not None

    # 1. fetch mode: LinkedIn hiring posts → private jobs + pending contacts.
    fetched: list[uuid.UUID] = []
    if mode == "fetch":
        if not await fetch_allowed(session):
            result.stopped = "Fetching new jobs is turned off by the admin."
            return result
        if problem := fetch_problem(user_settings):
            result.stopped = problem
            return result
        result.keywords = list(user_settings.automation_keywords)[:MAX_KEYWORDS]
        for index, keyword in enumerate(result.keywords):
            try:
                found = await discover_linkedin(
                    session,
                    ai=tools.ai,
                    source=tools.posts,
                    checker=tools.domains,
                    user_id=user_id,
                    keyword=keyword,
                    # Settings › Platform "Most posts per fetch", like a manual fetch.
                    max_posts=(await app_settings(session)).apify_max_posts_per_fetch,
                    posted_limit=user_settings.automation_posted_limit,  # type: ignore[arg-type]
                    progress=_noop,
                )
            except LimitExceededError as exc:
                result.stopped = exc.message
                break
            result.posts += found.posts
            result.new_contacts += found.new_contacts
            if found.posts == 0:
                result.empty_keywords.append(keyword)
            fetched += [uuid.UUID(j) for j in found.job_ids if uuid.UUID(j) not in fetched]
            if found.stopped:
                result.stopped = found.stopped
                break
            await progress(10 + int(30 * (index + 1) / len(result.keywords)))

    # 2. Candidates: new jobs from this fetch (pending contacts allowed — the approval
    #    queue shows their evidence), then saved jobs with an approved contact.
    applications = ApplicationRepository(session, owner_id=user_id)
    jobs: list[tuple[Job, Contact]] = []
    seen: set[uuid.UUID] = set()
    for job_id, approved_only in [(j, False) for j in fetched] + [
        (j, True) for j in await saved_job_ids(session, user_id)
    ]:
        if job_id in seen:
            continue
        seen.add(job_id)
        job = await JobRepository(session).visible(job_id, user_id)
        if job is None or await applications.for_job(job.id):
            continue
        contact = await _contact_for(session, user_id, job.id, approved_only=approved_only)
        if contact is not None:
            jobs.append((job, contact))
    result.candidates = len(jobs)

    # 3. Score → documents → application → draft, at most `automation_max_jobs`.
    for index, (job, contact) in enumerate(jobs):
        if result.prepared >= user_settings.automation_max_jobs or result.stopped:
            break
        try:
            await _prepare(session, tools, user_settings, user_id, job, contact, version, result)
        except LimitExceededError as exc:
            await session.rollback()
            result.stopped = exc.message
        except AppError as exc:
            await session.rollback()
            result.skipped.append(f"{job.title}: {exc.message}")
        await progress(40 + int(55 * (index + 1) / max(1, len(jobs))))

    user_settings.automation_last_run_at = datetime.now(UTC)
    notify(
        session,
        user_id,
        type="automation_run",
        title=f"Automation: {result.prepared} application(s) ready for your approval",
        body=_summary(result),
        link="/outbox",
        severity=NotificationSeverity.SUCCESS if result.prepared else NotificationSeverity.INFO,
    )
    await session.commit()
    logger.info("automation.run", user_id=str(user_id), mode=mode, prepared=result.prepared)
    return result


def _summary(result: RunResult) -> str:
    parts = []
    if result.mode == "fetch":
        parts.append(f"{result.posts} posts read")
    parts += [
        f"{result.candidates} jobs with a contact",
        f"{result.scored} scored",
        f"{result.below_minimum} below your minimum",
    ]
    text = ", ".join(parts) + "."
    if result.empty_keywords:
        text += " No posts for: " + ", ".join(result.empty_keywords) + "."
    if result.stopped:
        text += f" Stopped: {result.stopped}"
    return text


async def _noop(_percent: int) -> None:
    return None


async def _prepare(
    session: AsyncSession,
    tools: Tools,
    user_settings: UserSettings,
    user_id: uuid.UUID,
    job: Job,
    contact: Contact,
    version: ResumeVersion,
    result: RunResult,
) -> None:
    user_job = await UserJobRepository(session, owner_id=user_id).for_job(job.id)
    if not can_score(job, user_job):
        result.skipped.append(f"{job.title}: the description is too short to score")
        return
    # Reuse a score made earlier for this resume version (no AI call).
    analysis = await JobAnalysisRepository(session, owner_id=user_id).for_pair(job.id, version.id)
    if analysis is None:
        analysis = await analyze_job(session, tools.ai, user_id, job, user_job, version)
        result.scored += 1
    else:
        result.reused_scores += 1
    if analysis.match_score < user_settings.automation_min_score:
        result.below_minimum += 1
        return
    tailored = None
    if user_settings.automation_tailor and analysis.decision is AnalysisDecision.TAILOR:
        try:
            tailored = await generate_tailored(
                session,
                ai=tools.ai,
                gotenberg=tools.gotenberg,
                storage=tools.storage,
                user_id=user_id,
                job=job,
                user_job=user_job,
                source=version,
            )
        except LimitExceededError:
            raise
        except AppError as exc:  # keep going with the master resume
            result.skipped.append(f"{job.title}: tailored resume skipped ({exc.message})")
    letter = None
    if user_settings.automation_cover_letter:
        try:
            letter = await generate_cover_letter(
                session,
                ai=tools.ai,
                gotenberg=tools.gotenberg,
                storage=tools.storage,
                user_id=user_id,
                job=job,
                user_job=user_job,
                version=tailored or version,
                contact_name=contact.name,
            )
        except LimitExceededError:
            raise
        except AppError as exc:
            result.skipped.append(f"{job.title}: cover letter skipped ({exc.message})")
    await session.commit()
    application = await ApplicationService(session, user_id).create(
        job.id,
        channel=ApplicationChannel.EMAIL,
        resume_version_id=tailored.id if tailored else version.id,
        cover_letter_id=letter.id if letter else None,
        next_action="Review the email in the approval queue",
        contact_id=contact.id,
    )
    await generate_draft(
        session,
        ai=tools.ai,
        settings=tools.settings,
        user_id=user_id,
        application_id=application.id,
    )
    result.prepared += 1


# ---------- starting a run ----------

AUTOMATION_ENTITY = "automation"


async def start_run(
    session: AsyncSession,
    settings: Settings,
    user_id: uuid.UUID,
    dispatcher: TaskDispatcher,
    mode: Mode,
) -> Task:
    """One run per user at a time; checks what the run needs before queueing it."""
    if reason := await not_ready_reason(session, settings, user_id):
        raise ConflictError(reason, code="AUTOMATION_NOT_READY")
    if mode == "fetch":
        if not await fetch_allowed(session):
            raise PermissionDeniedError(
                "Fetching new jobs is locked. An admin can turn it on in Settings › Platform.",
                code="FETCH_LOCKED",
            )
        user_settings = await UserSettingsRepository(session, owner_id=user_id).get_or_create()
        if problem := fetch_problem(user_settings):
            raise ConflictError(problem, code="FETCH_NOT_READY")
    elif not await saved_job_ids(session, user_id):
        raise ConflictError(
            "No saved job is ready: approve a contact for a job first, or fetch new jobs.",
            code="NOTHING_TO_AUTOMATE",
        )
    active = await TaskRepository(session, owner_id=user_id).active_for(AUTOMATION_ENTITY, user_id)
    for task in active:
        if task.type == "automation_run":
            return task
    return await TaskService(session, user_id, dispatcher).create(
        "automation_run", {"mode": mode}, entity_type=AUTOMATION_ENTITY, entity_id=user_id
    )


async def last_run(session: AsyncSession, user_id: uuid.UUID) -> Task | None:
    result: Task | None = await session.scalar(
        select(Task)
        .where(Task.user_id == user_id, Task.type == "automation_run")
        .order_by(Task.created_at.desc())
        .limit(1)
    )
    return result
