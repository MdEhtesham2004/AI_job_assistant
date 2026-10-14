"""Phase 15 — AI mock interview.

Lifecycle: planning (AI task) → ready → in_progress (browser ↔ OpenAI Realtime over WebRTC,
transcript lines posted here) → ended (user may fix misheard words) → reporting (AI task)
→ completed. No audio is stored, only the transcript text.

Limits: every interview created this month counts (practice again too, failed plans do not),
the call length comes from Settings › Platform, and the browser token only lets one call
start; the room hangs up at the deadline and late transcript lines are refused.
"""

import re
import uuid
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from html import escape
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings
from app.core.errors import (
    ConflictError,
    LimitExceededError,
    NotFoundError,
    ValidationAppError,
)
from app.integrations.ai import AiClient
from app.integrations.gotenberg import GotenbergClient
from app.integrations.realtime import VoiceClient, voice_client
from app.integrations.storage import Storage, make_key
from app.models.accounts import User
from app.models.enums import (
    InterviewDifficulty,
    InterviewRound,
    InterviewSpeaker,
    InterviewStatus,
    InterviewVerdict,
    NotificationSeverity,
    ParseStatus,
)
from app.models.hunt import InterviewPrep
from app.models.interviews import Interview, InterviewReport, InterviewTurn
from app.models.jobs import Job
from app.models.resumes import ResumeVersion
from app.models.system import AiCall, Task
from app.prompts import interviews as prompts
from app.repositories.analyses import JobAnalysisRepository
from app.repositories.applications import ApplicationRepository
from app.repositories.interviews import (
    InterviewReportRepository,
    InterviewRepository,
    InterviewTurnRepository,
)
from app.repositories.jobs import JobRepository, UserJobRepository
from app.repositories.resumes import ResumeVersionRepository
from app.services.ai import AiService, month_start
from app.services.analysis import active_version, can_score, effective_description
from app.services.notifications import notify
from app.services.resume_files import PDF_MIME
from app.services.tasks import TaskDispatcher, TaskService
from app.services.usage import app_settings

ENTITY = "interview"
MAX_DESCRIPTION_CHARS = 8000
MAX_SESSIONS = 3  # first connect + 2 reconnects
TURN_GRACE = timedelta(seconds=45)  # transcription events arrive after the hang-up
AUTO_END_AFTER = timedelta(minutes=2)  # a tab closed mid-call ends on its own
MAX_TURNS = 120
FILLERS = ("um", "uh", "erm", "hmm", "you know", "i mean", "kind of", "sort of", "basically")


def _now() -> datetime:
    return datetime.now(UTC)


def _norm(text: str) -> str:
    return " ".join(re.sub(r"[^a-z0-9' ]+", " ", text.lower()).split())


def verdict_for(score: int) -> InterviewVerdict:
    if score >= 75:
        return InterviewVerdict.READY
    if score >= 55:
        return InterviewVerdict.ALMOST
    return InterviewVerdict.PRACTICE


def transcript_lines(turns: Sequence[InterviewTurn]) -> list[str]:
    return [
        f"{'INTERVIEWER' if t.speaker is InterviewSpeaker.INTERVIEWER else 'CANDIDATE'}: {t.text}"
        for t in turns
    ]


def communication_metrics(turns: Sequence[InterviewTurn]) -> dict[str, Any]:
    """Measured by code, not by the AI: answer length, filler words, share of talk."""
    answers = [t.text for t in turns if t.speaker is InterviewSpeaker.CANDIDATE and t.text.strip()]
    asked = [t.text for t in turns if t.speaker is InterviewSpeaker.INTERVIEWER]
    words = sum(len(a.split()) for a in answers)
    total = words + sum(len(q.split()) for q in asked)
    joined = " " + " ".join(_norm(a) for a in answers) + " "
    fillers = {f: joined.count(f" {f} ") for f in FILLERS}
    filler_total = sum(fillers.values())
    return {
        "answers": len(answers),
        "candidate_words": words,
        "average_answer_words": round(words / len(answers)) if answers else 0,
        "talk_share": round(words / total, 2) if total else 0,
        "filler_words": filler_total,
        "fillers_per_100_words": round(filler_total * 100 / words, 1) if words else 0,
        "top_fillers": [f for f, n in sorted(fillers.items(), key=lambda x: -x[1]) if n][:3],
    }


def quote_problems(draft: prompts.ReportDraft, turns: Sequence[InterviewTurn]) -> list[str]:
    """Every quote must be the candidate's own words (normalised substring match)."""
    said = (
        " "
        + " ".join(_norm(t.text) for t in turns if t.speaker is InterviewSpeaker.CANDIDATE)
        + " "
    )
    problems = []
    for q in draft.questions:
        if q.quote.strip() and f" {_norm(q.quote)} " not in said:
            problems.append(f"quote for {q.question_id} is not in the candidate's words")
        if not 1 <= q.score <= 5:
            problems.append(f"score for {q.question_id} must be 1-5")
    return problems


# ---------- PDF ----------

_STYLE = """
@page { size: A4; margin: 18mm 16mm; }
body { font-family: Helvetica, Arial, sans-serif; font-size: 10.5pt; color: #1f2937; }
h1 { font-size: 17pt; margin: 0 0 2mm; } h2 { font-size: 12pt; margin: 6mm 0 2mm; }
.muted { color: #6b7280; } .box { border: 1px solid #e5e7eb; border-radius: 6px;
padding: 3mm 4mm; margin: 2mm 0; } .score { font-weight: bold; }
blockquote { margin: 1mm 0; padding-left: 3mm; border-left: 3px solid #d1d5db; color: #374151; }
ul { margin: 1mm 0 1mm 5mm; padding: 0; }
"""

VERDICT_LABEL = {
    InterviewVerdict.READY: "Ready for the screen",
    InterviewVerdict.ALMOST: "Almost there",
    InterviewVerdict.PRACTICE: "Needs practice",
}


def render_report_html(interview: Interview, report: InterviewReport, job: Job) -> str:
    r = report.report
    items = "".join(
        f"<div class='box'><p><b>{escape(q['question'])}</b> "
        f"<span class='score'>{q['score']}/5</span></p>"
        + (f"<blockquote>“{escape(q['quote'])}”</blockquote>" if q.get("quote") else "")
        + f"<p><b>Went well:</b> {escape(q['went_well'])}</p>"
        f"<p><b>Missing:</b> {escape(q['missing'])}</p>"
        f"<p><b>Stronger answer:</b> {escape(q['better_answer'])}</p></div>"
        for q in r.get("questions", [])
    )

    def bullets(key: str) -> str:
        return "<ul>" + "".join(f"<li>{escape(x)}</li>" for x in r.get(key, [])) + "</ul>"

    m = r.get("metrics", {})
    date = (interview.started_at or interview.created_at).strftime("%d %b %Y")
    return (
        f"<html><head><meta charset='utf-8'><style>{_STYLE}</style></head><body>"
        f"<h1>Mock interview report</h1><p class='muted'>{escape(job.title)} · "
        f"{escape(job.company)} · {date} · {interview.round.value} round</p>"
        f"<div class='box'><p class='score'>{VERDICT_LABEL[report.verdict]} — "
        f"{report.overall_score}/100</p><p>{escape(r.get('summary', ''))}</p>"
        "<p class='muted'>Based on a short interview with a few answers: treat the score as a "
        "rough signal and focus on the specific feedback.</p></div>"
        f"<h2>Questions</h2>{items}"
        f"<h2>Strengths</h2>{bullets('strengths')}<h2>To improve</h2>{bullets('improvements')}"
        f"<h2>Communication</h2><p>Clarity {r['communication']['clarity']}/5 · structure "
        f"{r['communication']['structure']}/5 · {m.get('average_answer_words', 0)} words per "
        f"answer · {m.get('filler_words', 0)} filler words</p>"
        f"<p>{escape(r['communication']['notes'])}</p>"
        f"<h2>Practice plan</h2>{bullets('practice_plan')}</body></html>"
    )


# ---------- inputs ----------


def _job_input(job: Job, description: str) -> dict[str, Any]:
    return {
        "title": job.title,
        "company": job.company,
        "location": job.location,
        "description": description[:MAX_DESCRIPTION_CHARS],
    }


async def _resume_for(
    session: AsyncSession, user_id: uuid.UUID, job_id: uuid.UUID
) -> ResumeVersion:
    """The resume tailored for this job if there is one, else the active resume."""
    versions = ResumeVersionRepository(session, owner_id=user_id)
    tailored = await versions.latest_tailored(job_id)
    if tailored is not None and tailored.parse_status is ParseStatus.PARSED and tailored.parsed:
        return tailored
    version = await active_version(session, user_id)
    if version is None or version.parse_status is not ParseStatus.PARSED or not version.parsed:
        raise ConflictError(
            "Upload a resume and wait until it is parsed first.", code="RESUME_REQUIRED"
        )
    return version


resume_for_job = _resume_for  # also used by the screening answers (Phase 16)


async def _missing_skills(
    session: AsyncSession, user_id: uuid.UUID, job_id: uuid.UUID, version: ResumeVersion
) -> list[str]:
    analyses = JobAnalysisRepository(session, owner_id=user_id)
    analysis = await analyses.for_pair(job_id, version.id)
    if analysis is None and version.derived_from_id:
        analysis = await analyses.for_pair(job_id, version.derived_from_id)
    return list(analysis.missing_skills) if analysis else []


missing_skills_for = _missing_skills  # also used by the interview prep pack (Phase 17)


def _resume_input(version: ResumeVersion) -> dict[str, Any]:
    parsed = dict(version.parsed or {})
    for key in ("email", "phone", "links"):  # not needed to interview, keep it private
        parsed.pop(key, None)
    return parsed


# ---------- background work (called by the worker handlers) ----------


async def generate_plan(
    session: AsyncSession,
    *,
    ai: AiClient,
    interview: Interview,
    focus_questions: list[str] | None = None,
) -> Interview:
    """`focus_questions`: rehearse a real interview (Phase 17 prep pack's likely questions)."""
    user_id = interview.user_id
    job = await JobRepository(session).visible(interview.job_id, user_id)
    if job is None:
        raise NotFoundError("The job no longer exists.")
    user_job = await UserJobRepository(session, owner_id=user_id).for_job(job.id)
    version = await _resume_for(session, user_id, job.id)
    repo = InterviewRepository(session, owner_id=user_id)
    retry: list[str] = []
    if interview.retry_of_id:
        previous = await InterviewReportRepository(session, owner_id=user_id).for_interview(
            interview.retry_of_id
        )
        if previous is not None:
            weak = sorted(previous.report.get("questions", []), key=lambda q: q.get("score", 5))
            retry = [q["question"] for q in weak if q.get("score", 5) <= 3][:3] or [
                q["question"] for q in weak[:2]
            ]
    result = await AiService(session, ai).complete_json(
        user_id=user_id,
        task_type="interview_plan",
        prompt_version=prompts.PLAN_VERSION,
        messages=prompts.plan_messages(
            job=_job_input(job, effective_description(job, user_job)),
            resume=_resume_input(version),
            missing_skills=await _missing_skills(session, user_id, job.id, version),
            round_type=interview.round.value,
            difficulty=interview.difficulty.value,
            minutes=interview.minutes,
            avoid_questions=[] if retry or focus_questions else await repo.asked_questions(job.id),
            retry_questions=retry,
            focus_questions=focus_questions or [],
        ),
        output=prompts.InterviewPlan,
    )
    plan = result.data
    if not plan.questions:
        raise ValidationAppError("The AI returned an empty interview plan.")
    plan.questions = plan.questions[:4]
    for index, question in enumerate(plan.questions, start=1):
        question.id = f"q{index}"
    interview.plan = plan.model_dump()
    interview.resume_version_id = version.id
    interview.status = InterviewStatus.READY
    interview.error = None
    return interview


async def generate_report(
    session: AsyncSession,
    *,
    ai: AiClient,
    gotenberg: GotenbergClient,
    storage: Storage,
    interview: Interview,
) -> InterviewReport:
    user_id = interview.user_id
    turns = await InterviewTurnRepository(session, owner_id=user_id).for_interview(interview.id)
    job = await JobRepository(session).visible(interview.job_id, user_id)
    if job is None:
        raise NotFoundError("The job no longer exists.")
    version = (
        await ResumeVersionRepository(session, owner_id=user_id).get(interview.resume_version_id)
        if interview.resume_version_id
        else None
    )
    messages = prompts.report_messages(
        plan=interview.plan or {},
        transcript=transcript_lines(turns),
        resume=_resume_input(version) if version else {},
    )
    service = AiService(session, ai)
    result = await service.complete_json(
        user_id=user_id,
        task_type="interview_report",
        prompt_version=prompts.REPORT_VERSION,
        messages=messages,
        output=prompts.ReportDraft,
    )
    draft = result.data
    problems = quote_problems(draft, turns)
    if problems:  # one retry, then drop what is still not the candidate's words
        retry = await service.complete_json(
            user_id=user_id,
            task_type="interview_report",
            prompt_version=prompts.REPORT_VERSION,
            messages=[
                *messages,
                {"role": "assistant", "content": draft.model_dump_json()},
                prompts.report_retry_message(problems),
            ],
            output=prompts.ReportDraft,
        )
        draft = retry.data
        if quote_problems(draft, turns):
            said = (
                " "
                + " ".join(_norm(t.text) for t in turns if t.speaker is InterviewSpeaker.CANDIDATE)
                + " "
            )
            for q in draft.questions:
                if q.quote and f" {_norm(q.quote)} " not in said:
                    q.quote = ""
    for q in draft.questions:
        q.score = min(5, max(1, q.score))
    score = min(100, max(0, draft.overall_score))
    body = draft.model_dump()
    body["metrics"] = communication_metrics(turns)
    reports = InterviewReportRepository(session, owner_id=user_id)
    report = await reports.for_interview(interview.id)
    if report is None:
        report = InterviewReport(interview_id=interview.id, user_id=user_id)
        session.add(report)
    report.verdict = verdict_for(score)
    report.overall_score = score
    report.report = body
    report.model = result.model
    report.prompt_version = prompts.REPORT_VERSION
    await session.flush()
    pdf = await gotenberg.html_to_pdf(render_report_html(interview, report, job))
    if report.file_key:
        await storage.delete(report.file_key)
    stored = await storage.save(
        make_key(f"users/{user_id}/interviews", f"interview-report-{interview.id.hex[:8]}.pdf"),
        pdf,
        PDF_MIME,
    )
    report.file_key = stored.key
    interview.status = InterviewStatus.COMPLETED
    interview.error = None
    notify(
        session,
        user_id,
        type="interview_report",
        title=f"Interview report ready — {job.title}",
        body=f"{VERDICT_LABEL[report.verdict]} · {score}/100",
        link=f"/interviews/{interview.id}",
        severity=NotificationSeverity.SUCCESS,
    )
    return report


# ---------- the user's actions ----------


@dataclass(frozen=True)
class SessionGrant:
    token: str
    expires_at: datetime
    deadline_at: datetime
    seconds_left: int
    model: str
    wrap_up: str
    reconnect: bool
    provider: str
    connect_url: str


@dataclass(frozen=True)
class TurnIn:
    seq: int
    speaker: InterviewSpeaker
    text: str
    offset_ms: int


class InterviewService:
    def __init__(
        self,
        session: AsyncSession,
        user_id: uuid.UUID,
        *,
        settings: Settings,
        dispatcher: TaskDispatcher,
        realtime: VoiceClient | None = None,
        storage: Storage | None = None,
    ) -> None:
        self.session = session
        self.user_id = user_id
        self.settings = settings
        self.dispatcher = dispatcher
        self.realtime = realtime or voice_client(settings)
        self.storage = storage
        self.interviews = InterviewRepository(session, owner_id=user_id)
        self.turns = InterviewTurnRepository(session, owner_id=user_id)
        self.reports = InterviewReportRepository(session, owner_id=user_id)

    async def _limit_check(self) -> None:
        limit = (await app_settings(self.session)).interviews_per_month
        if limit and await self.interviews.counted_since(month_start()) >= limit:
            raise LimitExceededError(
                f"You used all {limit} mock interviews for this month.",
                code="INTERVIEW_LIMIT_REACHED",
            )

    async def create(
        self,
        job_id: uuid.UUID,
        *,
        round_type: InterviewRound,
        difficulty: InterviewDifficulty,
        retry_of_id: uuid.UUID | None = None,
        from_prep: bool = False,
    ) -> tuple[Interview, Task]:
        """`from_prep`: rehearse the prep pack's likely questions (Phase 17)."""
        job = await JobRepository(self.session).visible(job_id, self.user_id)
        if job is None:
            raise NotFoundError("Job not found.")
        user_job = await UserJobRepository(self.session, owner_id=self.user_id).for_job(job.id)
        if not can_score(job, user_job):
            raise ConflictError(
                "This job has no usable description. Paste it first.", code="DESCRIPTION_MISSING"
            )
        await _resume_for(self.session, self.user_id, job.id)  # fail early without a resume
        if retry_of_id is not None:
            previous = await self.interviews.get(retry_of_id)
            if previous is None or previous.job_id != job.id:
                raise NotFoundError("The interview to retry was not found.")
            if await self.reports.for_interview(previous.id) is None:
                raise ConflictError(
                    "That interview has no report yet.", code="INTERVIEW_NOT_REPORTED"
                )
        focus: list[str] = []
        if from_prep:
            prep = await self.session.scalar(
                select(InterviewPrep).where(
                    InterviewPrep.user_id == self.user_id, InterviewPrep.job_id == job.id
                )
            )
            if prep is None:
                raise ConflictError("Make the interview prep pack first.", code="PREP_REQUIRED")
            focus = [str(q["question"]) for q in prep.pack.get("likely_questions", [])][:3]
        await self._limit_check()
        application = await ApplicationRepository(self.session, owner_id=self.user_id).for_job(
            job.id
        )
        interview = await self.interviews.add(
            Interview(
                job_id=job.id,
                application_id=application.id if application else None,
                retry_of_id=retry_of_id,
                round=round_type,
                difficulty=difficulty,
                minutes=(await app_settings(self.session)).interview_minutes,
                status=InterviewStatus.PLANNING,
            )
        )
        payload: dict[str, Any] = {"interview_id": str(interview.id)}
        if focus:
            payload["focus_questions"] = focus
        task = await TaskService(self.session, self.user_id, self.dispatcher).create(
            "interview_plan", payload, entity_type=ENTITY, entity_id=interview.id
        )
        interview.plan_task_id = task.id
        await self.session.commit()
        return interview, task

    async def get(self, interview_id: uuid.UUID) -> Interview:
        interview = await self.interviews.get(interview_id)
        if interview is None:
            raise NotFoundError("Interview not found.")
        # A call whose tab was closed ends on its own after the deadline.
        if (
            interview.status is InterviewStatus.IN_PROGRESS
            and interview.deadline_at
            and _now() > interview.deadline_at + AUTO_END_AFTER
        ):
            self._end(interview, at=interview.deadline_at)
            await self.session.commit()
        return interview

    async def detail(
        self, interview_id: uuid.UUID
    ) -> tuple[Interview, Sequence[InterviewTurn], InterviewReport | None]:
        interview = await self.get(interview_id)
        return (
            interview,
            await self.turns.for_interview(interview.id),
            await self.reports.for_interview(interview.id),
        )

    async def history(
        self, job_id: uuid.UUID | None = None
    ) -> tuple[Sequence[Interview], dict[uuid.UUID, InterviewReport]]:
        items = await self.interviews.recent(job_id)
        return items, await self.reports.for_interviews([i.id for i in items])

    async def start_session(self, interview_id: uuid.UUID) -> SessionGrant:
        interview = await self.get(interview_id)
        now = _now()
        reconnect = interview.status is InterviewStatus.IN_PROGRESS
        if interview.status is InterviewStatus.READY:
            pass
        elif reconnect:
            if interview.deadline_at and now >= interview.deadline_at:
                raise ConflictError("The interview time is over.", code="INTERVIEW_TIME_OVER")
            if interview.sessions >= MAX_SESSIONS:
                raise ConflictError(
                    "Too many reconnects for this interview. End it to get your report.",
                    code="INTERVIEW_RECONNECT_LIMIT",
                )
        else:
            raise ConflictError("This interview cannot be started now.", code="INTERVIEW_NOT_READY")
        user = await self.session.get(User, self.user_id)
        first_name = user.full_name.split()[0] if user and user.full_name.split() else None
        so_far = transcript_lines(await self.turns.for_interview(interview.id)) if reconnect else []
        instructions = prompts.interviewer_instructions(
            interview.plan or {},
            candidate_name=first_name,
            minutes=interview.minutes,
            so_far=so_far,
        )
        await self.session.commit()  # no transaction held open while OpenAI answers
        token = await self.realtime.create_token(instructions, minutes=interview.minutes)
        if not reconnect:
            interview.status = InterviewStatus.IN_PROGRESS
            interview.started_at = now
            interview.deadline_at = now + timedelta(minutes=interview.minutes)
        interview.sessions += 1
        interview.model = token.model
        await self.session.commit()
        deadline = interview.deadline_at or now
        return SessionGrant(
            token=token.value,
            expires_at=token.expires_at,
            deadline_at=deadline,
            seconds_left=max(0, int((deadline - _now()).total_seconds())),
            model=token.model,
            wrap_up=prompts.WRAP_UP,
            reconnect=reconnect,
            provider=token.provider,
            connect_url=token.connect_url,
        )

    async def add_turns(self, interview_id: uuid.UUID, turns: list[TurnIn]) -> int:
        interview = await self.get(interview_id)
        late = interview.deadline_at is None or _now() > interview.deadline_at + TURN_GRACE
        open_ = interview.status is InterviewStatus.IN_PROGRESS or (
            interview.status is InterviewStatus.ENDED
            and interview.ended_at is not None
            and _now() <= interview.ended_at + TURN_GRACE
        )
        if not open_ or late:
            raise ConflictError(
                "The interview is over; no more transcript can be added.",
                code="INTERVIEW_CLOSED",
            )
        existing = {t.seq: t for t in await self.turns.for_interview(interview.id)}
        saved = 0
        for turn in turns:
            text = " ".join(turn.text.split())[:4000]
            if not text:
                continue
            current = existing.get(turn.seq)
            if current is None:
                if len(existing) >= MAX_TURNS:
                    break
                current = await self.turns.add(
                    InterviewTurn(
                        interview_id=interview.id,
                        seq=turn.seq,
                        speaker=turn.speaker,
                        text=text,
                        offset_ms=max(0, turn.offset_ms),
                    )
                )
                existing[turn.seq] = current
            elif not current.edited:  # a resend (after a lost request) replaces the text
                current.text = text
                current.speaker = turn.speaker
            saved += 1
        await self.session.commit()
        return saved

    def _end(self, interview: Interview, *, at: datetime) -> None:
        started = interview.started_at or at
        limit = interview.minutes * 60
        interview.status = InterviewStatus.ENDED
        interview.ended_at = at
        interview.seconds_used = max(0, min(limit, int((at - started).total_seconds())))
        per_minute = (
            self.settings.gemini_cost_per_minute_usd
            if (interview.model or "").startswith("gemini")
            else self.settings.realtime_cost_per_minute_usd
        )
        cost = Decimal(str(round(interview.seconds_used / 60 * per_minute, 4)))
        interview.estimated_cost_usd = cost
        # Counted with the other AI spend (budget, Analytics); an estimate per minute.
        self.session.add(
            AiCall(
                user_id=self.user_id,
                task_type="interview_realtime",
                model=interview.model or self.settings.realtime_model,
                prompt_version=prompts.INTERVIEWER_VERSION,
                cost_usd=cost,
                latency_ms=interview.seconds_used * 1000,
            )
        )

    async def finish(self, interview_id: uuid.UUID) -> Interview:
        interview = await self.get(interview_id)
        if interview.status is InterviewStatus.IN_PROGRESS:
            at = _now()
            if interview.deadline_at and at > interview.deadline_at:
                at = interview.deadline_at
            self._end(interview, at=at)
            await self.session.commit()
        elif interview.status is not InterviewStatus.ENDED:
            raise ConflictError("This interview is not running.", code="INTERVIEW_NOT_RUNNING")
        return interview

    async def edit_turn(self, interview_id: uuid.UUID, seq: int, text: str) -> InterviewTurn:
        interview = await self.get(interview_id)
        if interview.status is not InterviewStatus.ENDED:
            raise ConflictError(
                "The transcript can only be corrected before the report is made.",
                code="TRANSCRIPT_LOCKED",
            )
        turn = await self.turns.by_seq(interview.id, seq)
        if turn is None:
            raise NotFoundError("Transcript line not found.")
        if turn.speaker is not InterviewSpeaker.CANDIDATE:
            raise ValidationAppError("Only your own answers can be corrected.")
        text = " ".join(text.split())
        if not text:
            raise ValidationAppError("The answer cannot be empty.")
        if not turn.edited:
            turn.original_text = turn.text
        turn.text = text[:4000]
        turn.edited = True
        await self.session.commit()
        return turn

    async def start_report(self, interview_id: uuid.UUID) -> tuple[Interview, Task]:
        interview = await self.get(interview_id)
        if interview.status is InterviewStatus.IN_PROGRESS:
            interview = await self.finish(interview_id)
        if interview.status is not InterviewStatus.ENDED:
            raise ConflictError("A report can only be made after the call.", code="NOT_ENDED")
        turns = await self.turns.for_interview(interview.id)
        if not any(t.speaker is InterviewSpeaker.CANDIDATE and t.text.strip() for t in turns):
            raise ConflictError(
                "Nothing to assess: no answer was recorded in this interview.",
                code="NO_ANSWERS",
            )
        interview.status = InterviewStatus.REPORTING
        task = await TaskService(self.session, self.user_id, self.dispatcher).create(
            "interview_report",
            {"interview_id": str(interview.id)},
            entity_type=ENTITY,
            entity_id=interview.id,
        )
        interview.report_task_id = task.id
        await self.session.commit()
        return interview, task

    async def delete(self, interview_id: uuid.UUID) -> None:
        interview = await self.get(interview_id)
        if interview.status in (InterviewStatus.IN_PROGRESS, InterviewStatus.REPORTING):
            raise ConflictError("End the interview first.", code="INTERVIEW_BUSY")
        report = await self.reports.for_interview(interview.id)
        if report is not None and report.file_key and self.storage is not None:
            await self.storage.delete(report.file_key)
        await self.session.delete(interview)
        await self.session.commit()
