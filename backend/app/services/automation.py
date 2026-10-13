"""Apply pipeline (Phase 13, simplified in Phase 20): everything up to the user's approval.

Jobs in the user's list with an approved contact and no application → match score (reused
when it exists) → (≥ minimum) tailored resume when the analysis says so + cover letter →
email application → AI draft. Finding recruiters is Automations › Scheduled searches' job
(the old "fetch new jobs" mode was removed, admin decision 2026-10-13). Runs on "Prepare
applications", or daily at the user's hour when switched on. Capped per run; nothing is
ever sent without approval in the Outbox.
"""

import uuid
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

import structlog
from sqlalchemy import exists, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings
from app.core.errors import AppError, ConflictError, LimitExceededError
from app.integrations.ai import AiClient
from app.integrations.gotenberg import GotenbergClient
from app.integrations.storage import Storage
from app.models.accounts import Profile, User, UserSettings
from app.models.applications import Application
from app.models.enums import (
    AnalysisDecision,
    ApplicationChannel,
    ApprovalStatus,
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
from app.services.documents import generate_cover_letter, generate_tailored
from app.services.gmail_account import GmailAccountService
from app.services.notifications import notify
from app.services.outreach import generate_draft
from app.services.tasks import TaskDispatcher, TaskService

logger = structlog.get_logger("app.automation")

HIDDEN_STATES = (UserJobState.SKIPPED, UserJobState.ARCHIVED)


@dataclass
class RunResult:
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


# ---------- platform settings (admin only) ----------


async def app_settings(session: AsyncSession) -> AppSettings:
    row = await session.get(AppSettings, 1)
    if row is None:  # created by migration 0013; tests truncate tables
        row = AppSettings(id=1)
        session.add(row)
        await session.flush()
    return row


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
    """Jobs the pipeline can prepare — newest first (see job_readiness)."""
    return (await job_readiness(session, user_id))[0]


async def job_readiness(
    session: AsyncSession, user_id: uuid.UUID
) -> tuple[list[uuid.UUID], list[uuid.UUID]]:
    """(ready, below_minimum): jobs in the user's list (not skipped/archived) with an approved,
    usable contact and no application yet. Jobs already scored below the user's minimum for
    the active resume go to `below_minimum` — running again would only skip them (found
    live: the button said 2 while every run prepared 0)."""
    user_settings = await UserSettingsRepository(session, owner_id=user_id).get_or_create()
    version = await active_version(session, user_id)
    analyses = JobAnalysisRepository(session, owner_id=user_id)
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
    below: list[uuid.UUID] = []
    for job_id in rows.all():
        contact = await _contact_for(session, user_id, job_id, approved_only=True)
        if contact is None or blocklist.blocks(contact.email):
            continue
        analysis = await analyses.for_pair(job_id, version.id) if version else None
        if analysis is not None and analysis.match_score < user_settings.automation_min_score:
            below.append(job_id)
        else:
            ready.append(job_id)
    return ready, below


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


# ---------- the run ----------


async def run_pipeline(
    session: AsyncSession,
    tools: Tools,
    user_id: uuid.UUID,
    progress: Callable[[int], Awaitable[None]],
) -> RunResult:
    result = RunResult()
    user_settings = await UserSettingsRepository(session, owner_id=user_id).get_or_create()
    reason = await not_ready_reason(session, tools.settings, user_id)
    if reason:
        result.stopped = reason
        return result
    version = await active_version(session, user_id)
    assert version is not None

    # 1. Candidates: saved jobs with an approved contact and no application yet.
    applications = ApplicationRepository(session, owner_id=user_id)
    jobs: list[tuple[Job, Contact]] = []
    for job_id in await saved_job_ids(session, user_id):
        job = await JobRepository(session).visible(job_id, user_id)
        if job is None or await applications.for_job(job.id):
            continue
        contact = await _contact_for(session, user_id, job.id, approved_only=True)
        if contact is not None:
            jobs.append((job, contact))
    result.candidates = len(jobs)

    # 2. Score → documents → application → draft, at most `automation_max_jobs`.
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
        await progress(10 + int(85 * (index + 1) / max(1, len(jobs))))

    user_settings.automation_last_run_at = datetime.now(UTC)
    notify(
        session,
        user_id,
        type="automation_run",
        title=f"Apply pipeline: {result.prepared} application(s) ready for your approval",
        body=_summary(result),
        link="/outbox",
        severity=NotificationSeverity.SUCCESS if result.prepared else NotificationSeverity.INFO,
    )
    await session.commit()
    logger.info("automation.run", user_id=str(user_id), prepared=result.prepared)
    return result


def _summary(result: RunResult) -> str:
    text = (
        f"{result.candidates} jobs with a contact, {result.scored} scored, "
        f"{result.below_minimum} below your minimum."
    )
    if result.stopped:
        text += f" Stopped: {result.stopped}"
    return text


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
) -> Task:
    """One run per user at a time; checks what the run needs before queueing it."""
    if reason := await not_ready_reason(session, settings, user_id):
        raise ConflictError(reason, code="AUTOMATION_NOT_READY")
    if not await saved_job_ids(session, user_id):
        raise ConflictError(
            "No job is ready: approve a recruiter contact for a job first.",
            code="NOTHING_TO_AUTOMATE",
        )
    active = await TaskRepository(session, owner_id=user_id).active_for(AUTOMATION_ENTITY, user_id)
    for task in active:
        if task.type == "automation_run":
            return task
    return await TaskService(session, user_id, dispatcher).create(
        "automation_run", {}, entity_type=AUTOMATION_ENTITY, entity_id=user_id
    )


async def dispatch_automations(
    session: AsyncSession, settings: Settings, dispatcher: TaskDispatcher, now: datetime
) -> int:
    """Beat (every 15 min): the daily apply pipeline once the user's local hour has come.
    Skipped quietly when nothing is ready (no notification noise)."""
    rows = await session.execute(
        select(
            UserSettings.user_id,
            UserSettings.automation_hour,
            UserSettings.automation_last_run_at,
            Profile.timezone,
        )
        .join(User, User.id == UserSettings.user_id)
        .outerjoin(Profile, Profile.user_id == UserSettings.user_id)
        .where(
            UserSettings.automation_enabled.is_(True),
            User.is_active.is_(True),
            User.approval_status == ApprovalStatus.APPROVED,
        )
    )
    started = 0
    for user_id, hour, last_run_at, timezone in rows.all():
        zone = _zone(timezone)
        local = now.astimezone(zone)
        if local.hour < hour or (
            last_run_at and last_run_at.astimezone(zone).date() >= local.date()
        ):
            continue
        try:
            await start_run(session, settings, user_id, dispatcher)
            started += 1
        except AppError:
            continue  # not ready / nothing to prepare: try again on the next tick
        except Exception:
            logger.exception("automation.dispatch_failed", user_id=str(user_id))
            await session.rollback()
    return started


def _zone(name: str | None) -> ZoneInfo:
    try:
        return ZoneInfo(name or "UTC")
    except ZoneInfoNotFoundError:
        return ZoneInfo("UTC")


async def last_run(session: AsyncSession, user_id: uuid.UUID) -> Task | None:
    result: Task | None = await session.scalar(
        select(Task)
        .where(Task.user_id == user_id, Task.type == "automation_run")
        .order_by(Task.created_at.desc())
        .limit(1)
    )
    return result
