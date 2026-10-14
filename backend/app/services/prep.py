"""Phase 17 — interview prep pack.

Made automatically when an application reaches Interview (the board move queues it at
once; replies that set Interview are picked up by the 5-minute Beat sweep), or on demand.
One AI call per pack, then a PDF. "Practise with Maya" plans a mock interview with the
pack's likely questions.
"""

import uuid
from datetime import UTC, datetime, timedelta
from html import escape
from typing import Any

import structlog
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings
from app.core.errors import ConflictError, NotFoundError
from app.integrations.ai import AiClient
from app.integrations.gotenberg import GotenbergClient
from app.integrations.storage import Storage, make_key
from app.models.applications import Application
from app.models.enums import ApplicationStatus, NotificationSeverity
from app.models.hunt import InterviewPrep
from app.models.jobs import Job
from app.models.system import Task
from app.prompts import prep as prompts
from app.repositories.applications import ApplicationRepository
from app.repositories.jobs import JobRepository, UserJobRepository
from app.repositories.tasks import TaskRepository
from app.services.ai import AiService
from app.services.analysis import can_score, effective_description
from app.services.hunt import unsupported_numbers
from app.services.interviews import missing_skills_for, resume_for_job
from app.services.notifications import notify
from app.services.resume_files import PDF_MIME
from app.services.tasks import TaskDispatcher, TaskService

logger = structlog.get_logger("app.prep")

TASK = "interview_prep"
MAX_DESCRIPTION_CHARS = 8000
SWEEP_WINDOW = timedelta(days=14)  # interviews reached recently, without a pack yet


def _resume_input(parsed: dict[str, Any] | None) -> dict[str, Any]:
    data = dict(parsed or {})
    for key in ("email", "phone", "links"):
        data.pop(key, None)
    return data


async def prep_for(
    session: AsyncSession, user_id: uuid.UUID, job_id: uuid.UUID
) -> InterviewPrep | None:
    result: InterviewPrep | None = await session.scalar(
        select(InterviewPrep).where(
            InterviewPrep.user_id == user_id, InterviewPrep.job_id == job_id
        )
    )
    return result


async def running_prep(session: AsyncSession, user_id: uuid.UUID, job_id: uuid.UUID) -> Task | None:
    for task in await TaskRepository(session, owner_id=user_id).active_for("job", job_id):
        if task.type == TASK:
            return task
    return None


async def queue_prep(
    session: AsyncSession,
    user_id: uuid.UUID,
    job_id: uuid.UUID,
    dispatcher: TaskDispatcher,
    *,
    automatic: bool = False,
) -> Task | None:
    """Start making the pack. `automatic`: only when there is none yet (no duplicates)."""
    job = await JobRepository(session).visible(job_id, user_id)
    if job is None:
        raise NotFoundError("Job not found.")
    running = await running_prep(session, user_id, job.id)
    if running is not None:
        return running
    if automatic and await prep_for(session, user_id, job.id) is not None:
        return None
    user_job = await UserJobRepository(session, owner_id=user_id).for_job(job.id)
    if not can_score(job, user_job):
        if automatic:
            return None
        raise ConflictError(
            "This job has no usable description. Paste it first.", code="DESCRIPTION_MISSING"
        )
    await resume_for_job(session, user_id, job.id)  # needs a parsed resume
    return await TaskService(session, user_id, dispatcher).create(
        TASK, {"job_id": str(job.id), "automatic": automatic}, entity_type="job", entity_id=job.id
    )


def render_prep_html(job: Job, pack: dict[str, Any]) -> str:
    def items(values: list[str]) -> str:
        return "<ul>" + "".join(f"<li>{escape(v)}</li>" for v in values) + "</ul>"

    fit = "".join(
        f"<tr><td>{escape(f['requirement'])}</td><td>{escape(f['evidence'])}</td></tr>"
        for f in pack.get("your_fit", [])
    )
    questions = "".join(
        f"<div class='box'><b>{escape(q['question'])}</b><p class='muted'>{escape(q['why'])}</p>"
        f"<p>{escape(q['how_to_answer'])}</p></div>"
        for q in pack.get("likely_questions", [])
    )
    stories = "".join(
        f"<div class='box'><b>{escape(s['title'])}</b>"
        f"<p><b>S</b> {escape(s['situation'])}<br><b>T</b> {escape(s['task'])}<br>"
        f"<b>A</b> {escape(s['action'])}<br><b>R</b> {escape(s['result'])}</p></div>"
        for s in pack.get("star_stories", [])
    )
    gaps = "".join(
        f"<p><b>{escape(g['gap'])}:</b> {escape(g['honest_answer'])}</p>"
        for g in pack.get("gaps", [])
    )
    style = (
        "@page{size:A4;margin:16mm}body{font-family:Helvetica,Arial,sans-serif;font-size:10pt;"
        "color:#1f2937}h1{font-size:16pt;margin:0}h2{font-size:12pt;margin:5mm 0 2mm}"
        ".muted{color:#6b7280}.box{border:1px solid #e5e7eb;border-radius:6px;padding:2mm 3mm;"
        "margin:1.5mm 0}table{width:100%;border-collapse:collapse}td{border-top:1px solid "
        "#e5e7eb;padding:1.5mm;vertical-align:top}ul{margin:1mm 0 1mm 5mm;padding:0}"
    )
    return (
        f"<html><head><meta charset='utf-8'><style>{style}</style></head><body>"
        f"<h1>Interview prep — {escape(job.title)}</h1><p class='muted'>{escape(job.company)}</p>"
        f"<p>{escape(pack.get('role_summary', ''))}</p>"
        f"<h2>What they value</h2>{items(pack.get('what_they_value', []))}"
        f"<h2>Your fit</h2><table>{fit}</table>"
        f"<h2>Likely questions</h2>{questions}<h2>Your STAR stories</h2>{stories}"
        + (f"<h2>Gaps to expect</h2>{gaps}" if gaps else "")
        + f"<h2>Questions to ask them</h2>{items(pack.get('questions_to_ask', []))}"
        f"<h2>Day before</h2>{items(pack.get('checklist', []))}</body></html>"
    )


async def generate_prep(
    session: AsyncSession,
    *,
    ai: AiClient,
    gotenberg: GotenbergClient,
    storage: Storage,
    user_id: uuid.UUID,
    job_id: uuid.UUID,
) -> InterviewPrep:
    job = await JobRepository(session).visible(job_id, user_id)
    if job is None:
        raise NotFoundError("Job not found.")
    user_job = await UserJobRepository(session, owner_id=user_id).for_job(job.id)
    version = await resume_for_job(session, user_id, job.id)
    result = await AiService(session, ai).complete_json(
        user_id=user_id,
        task_type=TASK,
        prompt_version=prompts.PREP_VERSION,
        messages=prompts.prep_messages(
            job={
                "title": job.title,
                "company": job.company,
                "location": job.location,
                "description": effective_description(job, user_job)[:MAX_DESCRIPTION_CHARS],
            },
            resume=_resume_input(version.parsed),
            missing_skills=await missing_skills_for(session, user_id, job.id, version),
        ),
        output=prompts.PrepPack,
    )
    pack = result.data.model_dump()
    pack["star_stories"] = pack["star_stories"][:3]
    # Numbers the resume does not contain: shown as "check these" (never silently trusted).
    source = (version.text_content or "") + " " + str(version.parsed or "")
    told = " ".join(
        [s["result"] + " " + s["action"] for s in pack["star_stories"]]
        + [q["how_to_answer"] for q in pack["likely_questions"]]
    )
    pack["check"] = unsupported_numbers(told, source)

    record = await prep_for(session, user_id, job.id)
    if record is None:
        record = InterviewPrep(user_id=user_id, job_id=job.id)
        session.add(record)
    application = await ApplicationRepository(session, owner_id=user_id).for_job(job.id)
    record.application_id = application.id if application else None
    record.pack = pack
    record.model = result.model
    record.prompt_version = prompts.PREP_VERSION
    pdf = await gotenberg.html_to_pdf(render_prep_html(job, pack))
    if record.file_key:
        await storage.delete(record.file_key)
    stored = await storage.save(
        make_key(f"users/{user_id}/interviews", f"interview-prep-{job.id.hex[:8]}.pdf"),
        pdf,
        PDF_MIME,
    )
    record.file_key = stored.key
    notify(
        session,
        user_id,
        type="interview_prep_ready",
        title=f"Interview prep ready — {job.title}",
        body=f"{job.company}: likely questions, your STAR stories and questions to ask.",
        link=f"/jobs/{job.id}/prep",
        severity=NotificationSeverity.SUCCESS,
    )
    await session.commit()
    await session.refresh(record)
    return record


async def dispatch_preps(
    session: AsyncSession, settings: Settings, dispatcher: TaskDispatcher, now: datetime
) -> int:
    """Beat (every 5 min): packs for applications that reached Interview without one
    (e.g. set by an email reply). Board moves queue theirs immediately."""
    rows = await session.execute(
        select(Application.user_id, Application.job_id)
        .outerjoin(
            InterviewPrep,
            (InterviewPrep.user_id == Application.user_id)
            & (InterviewPrep.job_id == Application.job_id),
        )
        .where(
            Application.status == ApplicationStatus.INTERVIEW,
            Application.last_status_at >= now - SWEEP_WINDOW,
            InterviewPrep.id.is_(None),
        )
        .limit(50)
    )
    started = 0
    for user_id, job_id in rows.all():
        if await running_prep(session, user_id, job_id) is not None:
            continue  # already being made (not a new start)
        try:
            if await queue_prep(session, user_id, job_id, dispatcher, automatic=True):
                started += 1
        except Exception:
            logger.exception("prep.dispatch_failed", user_id=str(user_id), job_id=str(job_id))
            await session.rollback()
    return started


def now_utc() -> datetime:
    return datetime.now(UTC)
