"""Phase 16 — easier job hunt.

1. **Daily digest:** once per local day, at the user's hour, the best new matches: new jobs
   in the user's list since the last digest are scored (reused when a score exists, at most
   `digest_score_cap` AI calls per day), those at or above the user's minimum are ranked,
   the top few go into an in-app notification and — when Gmail is connected — an email the
   user sends to themselves.
2. **Skill gaps:** missing skills counted across the user's scored jobs (no AI); one AI call
   turns the top gaps into a 2-week learning plan.
3. **Screening answers:** per job, ready-to-paste answers to common form questions, grounded
   in the resume; notice period and salary come from the profile or stay "[fill in]".
"""

import re
import uuid
from collections import Counter, defaultdict
from collections.abc import Sequence
from dataclasses import dataclass, field
from datetime import UTC, date, datetime, timedelta
from html import escape
from typing import Any
from zoneinfo import ZoneInfo

import structlog
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings
from app.core.errors import AppError, ConflictError, LimitExceededError, NotFoundError
from app.domain.outreach import build_message
from app.integrations.ai import AiClient
from app.integrations.gmail import GmailAuthError
from app.models.accounts import Profile, User, UserSettings
from app.models.analysis import JobAnalysis
from app.models.enums import ApprovalStatus, NotificationSeverity, ParseStatus, UserJobState
from app.models.hunt import Digest, ScreeningAnswers, SkillPlanRecord
from app.models.jobs import Job, UserJob
from app.models.resumes import ResumeVersion
from app.models.system import Task
from app.prompts import hunt as prompts
from app.repositories.analyses import JobAnalysisRepository
from app.repositories.jobs import JobRepository, UserJobRepository
from app.repositories.profiles import ProfileRepository, UserSettingsRepository
from app.repositories.tasks import TaskRepository
from app.services.ai import AiService
from app.services.analysis import active_version, analyze_job, can_score, effective_description
from app.services.gmail_account import GmailAccountService, GmailNotConnectedError
from app.services.interviews import resume_for_job
from app.services.notifications import notify
from app.services.tasks import TaskDispatcher, TaskService

logger = structlog.get_logger("app.hunt")

DIGEST_ENTITY = "digest"
LOOKBACK = timedelta(days=3)  # first digest (or after a pause): new jobs of the last 3 days
SKIP_STATES = (UserJobState.ARCHIVED, UserJobState.SKIPPED)
MAX_CUSTOM_QUESTIONS = 3
MAX_DESCRIPTION_CHARS = 8000


def _zone(name: str | None) -> ZoneInfo:
    try:
        return ZoneInfo(name or "UTC")
    except (KeyError, ValueError):
        return ZoneInfo("UTC")


def _resume_input(version: ResumeVersion) -> dict[str, Any]:
    parsed = dict(version.parsed or {})
    for key in ("email", "phone", "links"):
        parsed.pop(key, None)
    return parsed


# =====================================================================================
# 1. Daily digest
# =====================================================================================


@dataclass
class DigestOutcome:
    digest: Digest | None
    reason: str | None = None  # why nothing was sent


def digest_email(digest: Digest, *, app_url: str, name: str | None) -> tuple[str, str, str]:
    """(subject, plain text, HTML) for the digest email."""
    jobs = digest.jobs
    plural = "s" if len(jobs) != 1 else ""
    subject = f"{len(jobs)} new job match{'es' if len(jobs) != 1 else ''} for you today"
    hello = f"Hi {name}," if name else "Hi,"
    lines = [
        f"{i}. {j['title']} — {j['company']} ({j['score']}/100) {app_url}/jobs/{j['job_id']}"
        for i, j in enumerate(jobs, start=1)
    ]
    text = (
        f"{hello}\n\nYour best new match{plural} today:\n\n"
        + "\n".join(lines)
        + f"\n\nAll jobs: {app_url}/jobs\nTurn this email off in Settings › Daily digest.\n"
    )
    rows = "".join(
        f"<tr><td style='padding:6px 0'><a href='{escape(app_url)}/jobs/{j['job_id']}' "
        f"style='color:#2563eb;font-weight:600;text-decoration:none'>{escape(j['title'])}</a>"
        f"<br><span style='color:#6b7280'>{escape(j['company'])}"
        f"{' · ' + escape(j['location']) if j.get('location') else ''}</span></td>"
        f"<td style='padding:6px 0 6px 16px;text-align:right;font-weight:700'>"
        f"{j['score']}</td></tr>"
        for j in jobs
    )
    html = (
        "<div style='font-family:Arial,sans-serif;font-size:14px;color:#111827;max-width:560px'>"
        f"<p>{escape(hello)}</p><p>Your best new match{plural} today:</p>"
        f"<table style='width:100%;border-collapse:collapse'>{rows}</table>"
        f"<p><a href='{escape(app_url)}/jobs'>See all jobs</a></p>"
        "<p style='color:#6b7280;font-size:12px'>Turn this email off in Settings › Daily "
        "digest.</p></div>"
    )
    return subject, text, html


async def _new_jobs(
    session: AsyncSession, user_id: uuid.UUID, since: datetime
) -> list[tuple[Job, UserJob]]:
    rows = await session.execute(
        select(Job, UserJob)
        .join(UserJob, UserJob.job_id == Job.id)
        .where(
            UserJob.user_id == user_id,
            UserJob.created_at >= since,
            UserJob.state.not_in(SKIP_STATES),
        )
        .order_by(UserJob.created_at.desc())
        .limit(200)
    )
    return [(job, user_job) for job, user_job in rows.all()]


async def build_digest(
    session: AsyncSession,
    *,
    ai: AiClient,
    settings: Settings,
    user_id: uuid.UUID,
    now: datetime | None = None,
    force: bool = False,
) -> DigestOutcome:
    """Make (or, with `force`, remake) today's digest for one user."""
    now = now or datetime.now(UTC)
    user_settings = await UserSettingsRepository(session, owner_id=user_id).get_or_create()
    profile = await ProfileRepository(session, owner_id=user_id).get(user_id)
    today = now.astimezone(_zone(profile.timezone if profile else None)).date()

    existing = await session.scalar(
        select(Digest).where(Digest.user_id == user_id, Digest.digest_date == today)
    )
    if existing is not None and not force:
        return DigestOutcome(existing, "Today's digest was already made.")
    previous = await session.scalar(
        select(Digest)
        .where(Digest.user_id == user_id, Digest.digest_date < today)
        .order_by(Digest.digest_date.desc())
        .limit(1)
    )
    since = max(previous.created_at, now - LOOKBACK) if previous else now - LOOKBACK

    version = await active_version(session, user_id)
    if version is None or version.parse_status is not ParseStatus.PARSED:
        return DigestOutcome(None, "Upload a resume first: matches need a score.")

    candidates = await _new_jobs(session, user_id, since)
    analyses = JobAnalysisRepository(session, owner_id=user_id)
    scored = 0
    picked: list[tuple[JobAnalysis, Job]] = []
    budget_reached = False
    for job, user_job in candidates:
        analysis = await analyses.for_pair(job.id, version.id)
        if analysis is None and not budget_reached and scored < settings.digest_score_cap:
            if not can_score(job, user_job):
                continue
            try:
                analysis = await analyze_job(session, ai, user_id, job, user_job, version)
                scored += 1
            except LimitExceededError:
                budget_reached = True  # AI budget used up: rank what is already scored
                continue
            except AppError as exc:
                logger.warning("digest.score_failed", job_id=str(job.id), error=exc.message)
                continue
        if analysis is not None and analysis.match_score >= user_settings.digest_min_score:
            picked.append((analysis, job))
    picked.sort(key=lambda pair: pair[0].match_score, reverse=True)
    top = picked[: settings.digest_max_jobs]

    digest = existing or Digest(user_id=user_id, digest_date=today)
    digest.jobs = [
        {
            "job_id": str(job.id),
            "title": job.title,
            "company": job.company,
            "location": job.location,
            "score": analysis.match_score,
            "decision": analysis.decision.value,
        }
        for analysis, job in top
    ]
    digest.new_jobs = len(candidates)
    digest.scored = (existing.scored if existing else 0) + scored
    if existing is None:
        session.add(digest)
    await session.flush()

    if top:
        best = top[0][0].match_score
        notify(
            session,
            user_id,
            type="digest_daily",
            title=f"{len(top)} new match{'es' if len(top) != 1 else ''} for you today "
            f"(best {best}/100)",
            body=", ".join(f"{j.title} — {j.company}" for _, j in top[:3]),
            link="/",
            severity=NotificationSeverity.SUCCESS,
        )
        if user_settings.digest_email:
            await _email_digest(session, settings, user_id, digest)
    await session.commit()
    return DigestOutcome(digest, None if top else "No new jobs at or above your minimum score.")


async def _email_digest(
    session: AsyncSession, settings: Settings, user_id: uuid.UUID, digest: Digest
) -> None:
    """Send the digest from the user's own Gmail to themselves (best effort)."""
    gmail_service = GmailAccountService(session, user_id, settings)
    status = await gmail_service.status()
    if not status.connected or not status.can_send:
        digest.email_error = "Gmail is not connected."
        return
    try:
        gmail, account = await gmail_service.api()
        user = await session.get(User, user_id)
        first = user.full_name.split()[0] if user and user.full_name.split() else None
        subject, text, html = digest_email(
            digest, app_url=settings.frontend_url.rstrip("/"), name=first
        )
        mime, _ = build_message(
            from_address=account.account_email,
            from_name=None,
            to_address=account.account_email,
            subject=subject,
            body=text,
            html=html,
            attachments=[],
            idempotency=f"digest-{user_id}-{digest.digest_date.isoformat()}",
        )
        await gmail.send(mime)
        digest.emailed = True
        digest.email_error = None
    except GmailNotConnectedError:
        digest.email_error = "Gmail is not connected."
    except GmailAuthError:
        await gmail_service.mark_revoked()
        digest.email_error = "Gmail access was revoked."
    except AppError as exc:
        digest.email_error = exc.message[:300]
        logger.warning("digest.email_failed", user_id=str(user_id), error=exc.message)


async def dispatch_digests(
    session: AsyncSession, settings: Settings, dispatcher: TaskDispatcher, now: datetime
) -> int:
    """Beat (every 15 min): start today's digest for users whose local hour has come."""
    rows = await session.execute(
        select(UserSettings.user_id, UserSettings.digest_hour, Profile.timezone)
        .join(User, User.id == UserSettings.user_id)
        .outerjoin(Profile, Profile.user_id == UserSettings.user_id)
        .where(
            UserSettings.digest_enabled.is_(True),
            User.is_active.is_(True),
            User.approval_status == ApprovalStatus.APPROVED,
        )
    )
    started = 0
    for user_id, hour, timezone in rows.all():
        local = now.astimezone(_zone(timezone))
        if local.hour < hour:
            continue
        done = await session.scalar(
            select(Digest.id).where(Digest.user_id == user_id, Digest.digest_date == local.date())
        )
        if done is not None:
            continue
        tasks = TaskRepository(session, owner_id=user_id)
        if await tasks.active_for(DIGEST_ENTITY, user_id):
            continue  # still running from the last tick
        try:
            await TaskService(session, user_id, dispatcher).create(
                "daily_digest",
                {"date": local.date().isoformat()},
                entity_type=DIGEST_ENTITY,
                entity_id=user_id,
            )
            started += 1
        except Exception:
            logger.exception("digest.dispatch_failed", user_id=str(user_id))
            await session.rollback()
    return started


async def start_digest_now(
    session: AsyncSession, user_id: uuid.UUID, dispatcher: TaskDispatcher
) -> Task:
    running = await TaskRepository(session, owner_id=user_id).active_for(DIGEST_ENTITY, user_id)
    if running:
        return running[0]
    return await TaskService(session, user_id, dispatcher).create(
        "daily_digest", {"force": True}, entity_type=DIGEST_ENTITY, entity_id=user_id
    )


async def latest_digest(session: AsyncSession, user_id: uuid.UUID) -> Digest | None:
    result: Digest | None = await session.scalar(
        select(Digest).where(Digest.user_id == user_id).order_by(Digest.digest_date.desc()).limit(1)
    )
    return result


# =====================================================================================
# 2. Skill gaps
# =====================================================================================


@dataclass
class SkillGap:
    skill: str
    jobs: int
    examples: list[str] = field(default_factory=list)


@dataclass
class SkillGaps:
    jobs_analyzed: int
    gaps: list[SkillGap]
    strengths: list[SkillGap]


def _skill_key(skill: str) -> str:
    return " ".join(re.sub(r"[^a-z0-9+#. ]+", " ", skill.lower()).split())


def aggregate_skills(
    rows: Sequence[tuple[list[str], list[str], str]], limit: int = 12
) -> tuple[list[SkillGap], list[SkillGap]]:
    """rows: (missing_skills, matched_skills, job label) per scored job → gaps, strengths."""

    def count(index: int) -> list[SkillGap]:
        jobs: dict[str, int] = Counter()
        names: dict[str, Counter[str]] = defaultdict(Counter)
        examples: dict[str, list[str]] = defaultdict(list)
        for row in rows:
            seen: set[str] = set()
            for skill in row[index]:
                key = _skill_key(skill)
                if not key or key in seen:
                    continue
                seen.add(key)
                jobs[key] += 1
                names[key][skill.strip()] += 1
                if len(examples[key]) < 3:
                    examples[key].append(row[2])
        ranked = sorted(jobs.items(), key=lambda item: (-item[1], item[0]))[:limit]
        return [SkillGap(names[key].most_common(1)[0][0], n, examples[key]) for key, n in ranked]

    return count(0), count(1)


async def skill_gaps(session: AsyncSession, user_id: uuid.UUID) -> SkillGaps:
    """Free: counts over the scores of the active resume (or the one it was tailored from)."""
    version = await active_version(session, user_id)
    if version is None:
        return SkillGaps(0, [], [])
    versions = [version.id] + ([version.derived_from_id] if version.derived_from_id else [])
    rows = await session.execute(
        select(JobAnalysis.missing_skills, JobAnalysis.matched_skills, Job.title, Job.company)
        .join(Job, Job.id == JobAnalysis.job_id)
        .outerjoin(UserJob, (UserJob.job_id == Job.id) & (UserJob.user_id == user_id))
        .where(
            JobAnalysis.user_id == user_id,
            JobAnalysis.resume_version_id.in_(versions),
            (UserJob.state.is_(None)) | (UserJob.state.not_in(SKIP_STATES)),
        )
        .order_by(JobAnalysis.updated_at.desc())
        .limit(300)
    )
    data = [
        (list(missing or []), list(matched or []), f"{title} — {company}")
        for missing, matched, title, company in rows.all()
    ]
    gaps, strengths = aggregate_skills(data)
    return SkillGaps(len(data), gaps, strengths[:8])


async def generate_skill_plan(
    session: AsyncSession, *, ai: AiClient, user_id: uuid.UUID
) -> SkillPlanRecord:
    found = await skill_gaps(session, user_id)
    if not found.gaps:
        raise ConflictError("No skill gaps yet: score a few jobs first.", code="NO_SKILL_GAPS")
    version = await active_version(session, user_id)
    assert version is not None
    gaps = [{"skill": g.skill, "jobs": g.jobs} for g in found.gaps[:6]]
    result = await AiService(session, ai).complete_json(
        user_id=user_id,
        task_type="skill_plan",
        prompt_version=prompts.SKILL_PLAN_VERSION,
        messages=prompts.skill_plan_messages(
            gaps=gaps, strengths=[s.skill for s in found.strengths], resume=_resume_input(version)
        ),
        output=prompts.SkillPlan,
    )
    plan = result.data
    plan.days = sorted(plan.days, key=lambda d: d.day)[:14]
    record = SkillPlanRecord(
        user_id=user_id,
        gaps=gaps,
        plan=plan.model_dump(),
        model=result.model,
        prompt_version=prompts.SKILL_PLAN_VERSION,
    )
    session.add(record)
    notify(
        session,
        user_id,
        type="skill_plan_ready",
        title="Your 2-week learning plan is ready",
        body="Focus: " + ", ".join(str(g["skill"]) for g in gaps[:3]),
        link="/skills",
        severity=NotificationSeverity.SUCCESS,
    )
    await session.commit()
    return record


async def latest_skill_plan(session: AsyncSession, user_id: uuid.UUID) -> SkillPlanRecord | None:
    result: SkillPlanRecord | None = await session.scalar(
        select(SkillPlanRecord)
        .where(SkillPlanRecord.user_id == user_id)
        .order_by(SkillPlanRecord.created_at.desc())
        .limit(1)
    )
    return result


# =====================================================================================
# 3. Screening answers
# =====================================================================================

_NUMBER = re.compile(r"\d[\d,.]*%?")


def unsupported_numbers(answer: str, source: str) -> list[str]:
    """Numbers in an answer that appear nowhere in the resume / profile facts."""
    known = {n.rstrip(".,%").replace(",", "") for n in _NUMBER.findall(source)}
    found = []
    for raw in _NUMBER.findall(answer):
        number = raw.rstrip(".,%").replace(",", "")
        if number and number not in known and number not in found:
            found.append(number)
    return found


async def generate_answers(
    session: AsyncSession,
    *,
    ai: AiClient,
    user_id: uuid.UUID,
    job_id: uuid.UUID,
    custom_questions: list[str],
) -> ScreeningAnswers:
    job = await JobRepository(session).visible(job_id, user_id)
    if job is None:
        raise NotFoundError("Job not found.")
    user_job = await UserJobRepository(session, owner_id=user_id).for_job(job.id)
    version = await resume_for_job(session, user_id, job.id)
    profile = await ProfileRepository(session, owner_id=user_id).get(user_id)
    facts = {
        k: v
        for k, v in {
            "notice period": profile.notice_period if profile else None,
            "expected salary": profile.expected_salary if profile else None,
        }.items()
        if v
    }
    questions = [
        (key, text.format(company=job.company)) for key, text in prompts.STANDARD_QUESTIONS
    ]
    questions += [
        (f"custom_{i}", q.strip())
        for i, q in enumerate(custom_questions[:MAX_CUSTOM_QUESTIONS], start=1)
        if q.strip()
    ]
    result = await AiService(session, ai).complete_json(
        user_id=user_id,
        task_type="screening_answers",
        prompt_version=prompts.ANSWERS_VERSION,
        messages=prompts.answer_messages(
            job={
                "title": job.title,
                "company": job.company,
                "location": job.location,
                "description": effective_description(job, user_job)[:MAX_DESCRIPTION_CHARS],
            },
            resume=_resume_input(version),
            facts=facts,
            questions=questions,
        ),
        output=prompts.AnswerSet,
    )
    by_key = {a.key: a.answer.strip() for a in result.data.answers}
    source = (
        (version.text_content or "")
        + " "
        + str(version.parsed or "")
        + " "
        + " ".join(facts.values())
    )

    record = await session.scalar(
        select(ScreeningAnswers).where(
            ScreeningAnswers.user_id == user_id, ScreeningAnswers.job_id == job.id
        )
    )
    kept = {a["key"]: a for a in (record.answers if record else []) if a.get("edited")}
    answers = []
    for key, question in questions:
        if key in kept and kept[key]["question"] == question:
            answers.append(kept[key])  # the user's own edit is never overwritten
            continue
        text = by_key.get(key) or prompts.FILL_IN
        # Notice period and salary are never guessed: without a profile fact → fill in.
        fact = {"notice": "notice period", "salary": "expected salary"}.get(key)
        if fact and fact not in facts and _NUMBER.search(text):
            text = (
                f"My notice period is {prompts.FILL_IN}."
                if key == "notice"
                else f"My expectation is {prompts.FILL_IN}, and I am open to discussing it."
            )
        answers.append(
            {
                "key": key,
                "question": question,
                "answer": text,
                "edited": False,
                "custom": key.startswith("custom_"),
                "check": unsupported_numbers(text, source),
            }
        )
    if record is None:
        record = ScreeningAnswers(user_id=user_id, job_id=job.id)
        session.add(record)
    record.answers = answers
    record.model = result.model
    record.prompt_version = prompts.ANSWERS_VERSION
    await session.commit()
    return record


async def answers_for(
    session: AsyncSession, user_id: uuid.UUID, job_id: uuid.UUID
) -> ScreeningAnswers | None:
    result: ScreeningAnswers | None = await session.scalar(
        select(ScreeningAnswers).where(
            ScreeningAnswers.user_id == user_id, ScreeningAnswers.job_id == job_id
        )
    )
    return result


async def edit_answer(
    session: AsyncSession, user_id: uuid.UUID, job_id: uuid.UUID, key: str, text: str
) -> ScreeningAnswers:
    record = await answers_for(session, user_id, job_id)
    if record is None:
        raise NotFoundError("No answers for this job yet.")
    answers = [dict(a) for a in record.answers]
    for answer in answers:
        if answer["key"] == key:
            answer["answer"] = " ".join(text.split()) if "\n" not in text else text.strip()
            answer["edited"] = True
            answer["check"] = []
            break
    else:
        raise NotFoundError("Question not found.")
    record.answers = answers  # new list so the JSONB change is saved
    await session.commit()
    await session.refresh(record)  # updated_at was set by the database
    return record


async def start_answers(
    session: AsyncSession,
    user_id: uuid.UUID,
    job_id: uuid.UUID,
    custom_questions: list[str],
    dispatcher: TaskDispatcher,
) -> Task:
    job = await JobRepository(session).visible(job_id, user_id)
    if job is None:
        raise NotFoundError("Job not found.")
    user_job = await UserJobRepository(session, owner_id=user_id).for_job(job.id)
    if not can_score(job, user_job):
        raise ConflictError(
            "This job has no usable description. Paste it first.", code="DESCRIPTION_MISSING"
        )
    await resume_for_job(session, user_id, job.id)  # fail early without a resume
    for task in await TaskRepository(session, owner_id=user_id).active_for("job", job.id):
        if task.type == "screening_answers":
            return task
    return await TaskService(session, user_id, dispatcher).create(
        "screening_answers",
        {"job_id": str(job.id), "custom_questions": custom_questions[:MAX_CUSTOM_QUESTIONS]},
        entity_type="job",
        entity_id=job.id,
    )


def today_for(timezone: str | None, now: datetime | None = None) -> date:
    return (now or datetime.now(UTC)).astimezone(_zone(timezone)).date()
