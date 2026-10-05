"""Phase 15 — AI mock interview (6-minute voice screen with a report)."""

import uuid
from collections.abc import Sequence
from typing import Annotated

from fastapi import APIRouter, Query, Request, status

from app.api.deps import ApprovedUser, DbSession
from app.models.interviews import Interview, InterviewReport
from app.models.jobs import Job
from app.schemas.interviews import (
    InterviewCreate,
    InterviewCreated,
    InterviewDetail,
    InterviewJob,
    InterviewSummary,
    PlanQuestionRead,
    ReportRead,
    SessionRead,
    TurnEdit,
    TurnRead,
    TurnsWrite,
)
from app.services.interviews import InterviewService, TurnIn
from app.services.resume_files import PDF_MIME
from app.services.tasks import download_url

router = APIRouter(tags=["interviews"])


def service(request: Request, db: DbSession, user: ApprovedUser) -> InterviewService:
    state = request.app.state
    return InterviewService(
        db,
        user.id,
        settings=state.settings,
        dispatcher=state.dispatcher,
        realtime=getattr(state, "realtime", None),
        storage=state.storage,
    )


async def _jobs(db: DbSession, interviews: Sequence[Interview]) -> dict[uuid.UUID, Job]:
    jobs: dict[uuid.UUID, Job] = {}
    for job_id in {i.job_id for i in interviews}:
        job = await db.get(Job, job_id)
        if job is not None:
            jobs[job_id] = job
    return jobs


def _summary(interview: Interview, job: Job | None, report: InterviewReport | None) -> dict:
    return {
        "id": interview.id,
        "status": interview.status,
        "round": interview.round,
        "difficulty": interview.difficulty,
        "minutes": interview.minutes,
        "job": InterviewJob(
            id=interview.job_id,
            title=job.title if job else "Deleted job",
            company=job.company if job else "",
        ),
        "application_id": interview.application_id,
        "retry_of_id": interview.retry_of_id,
        "verdict": report.verdict if report else None,
        "overall_score": report.overall_score if report else None,
        "started_at": interview.started_at,
        "seconds_used": interview.seconds_used,
        "created_at": interview.created_at,
    }


@router.post(
    "/jobs/{job_id}/interviews",
    response_model=InterviewCreated,
    status_code=status.HTTP_202_ACCEPTED,
    summary="Plan a mock interview for a job (counts against the monthly limit)",
)
async def create_interview(
    job_id: uuid.UUID, body: InterviewCreate, request: Request, db: DbSession, user: ApprovedUser
) -> InterviewCreated:
    interview, task = await service(request, db, user).create(
        job_id,
        round_type=body.round,
        difficulty=body.difficulty,
        retry_of_id=body.retry_of_id,
        from_prep=body.from_prep,
    )
    return InterviewCreated(interview_id=interview.id, task_id=task.id)


@router.get("/interviews", response_model=list[InterviewSummary], summary="Your mock interviews")
async def list_interviews(
    request: Request,
    db: DbSession,
    user: ApprovedUser,
    job_id: Annotated[uuid.UUID | None, Query()] = None,
) -> list[InterviewSummary]:
    items, reports = await service(request, db, user).history(job_id)
    jobs = await _jobs(db, items)
    return [InterviewSummary(**_summary(i, jobs.get(i.job_id), reports.get(i.id))) for i in items]


@router.get("/interviews/{interview_id}", response_model=InterviewDetail, summary="One interview")
async def get_interview(
    interview_id: uuid.UUID, request: Request, db: DbSession, user: ApprovedUser
) -> InterviewDetail:
    svc = service(request, db, user)
    interview, turns, report = await svc.detail(interview_id)
    job = await db.get(Job, interview.job_id)
    plan = interview.plan or {}
    show_questions = report is not None or interview.status.value in ("ended", "reporting")
    return InterviewDetail(
        **_summary(interview, job, report),
        error=interview.error,
        deadline_at=interview.deadline_at,
        ended_at=interview.ended_at,
        plan_task_id=interview.plan_task_id,
        report_task_id=interview.report_task_id,
        thin_description=bool(plan.get("thin_description")),
        questions=[
            PlanQuestionRead(id=q["id"], kind=q["kind"], topic=q["topic"], question=q["question"])
            for q in plan.get("questions", [])
        ]
        if show_questions
        else [],
        turns=[TurnRead.model_validate(t) for t in turns],
        report=ReportRead(
            verdict=report.verdict,
            overall_score=report.overall_score,
            report=report.report,
            pdf_url=download_url(
                svc.settings,
                user.id,
                key=report.file_key,
                filename=f"Interview report - {job.company if job else 'job'}.pdf",
                content_type=PDF_MIME,
            )
            if report.file_key
            else None,
        )
        if report
        else None,
        estimated_cost_usd=interview.estimated_cost_usd,
    )


@router.post(
    "/interviews/{interview_id}/session",
    response_model=SessionRead,
    summary="Start (or reconnect) the voice call: a short-lived OpenAI Realtime token",
)
async def start_session(
    interview_id: uuid.UUID, request: Request, db: DbSession, user: ApprovedUser
) -> SessionRead:
    svc = service(request, db, user)
    grant = await svc.start_session(interview_id)
    return SessionRead(
        client_secret=grant.token,
        expires_at=grant.expires_at,
        deadline_at=grant.deadline_at,
        seconds_left=grant.seconds_left,
        model=grant.model,
        connect_url=grant.connect_url,
        provider=grant.provider,
        wrap_up=grant.wrap_up,
        reconnect=grant.reconnect,
    )


@router.post(
    "/interviews/{interview_id}/turns",
    summary="Save transcript lines from the call (idempotent per sequence number)",
)
async def add_turns(
    interview_id: uuid.UUID, body: TurnsWrite, request: Request, db: DbSession, user: ApprovedUser
) -> dict[str, int]:
    saved = await service(request, db, user).add_turns(
        interview_id,
        [TurnIn(t.seq, t.speaker, t.text, t.offset_ms) for t in body.turns],
    )
    return {"saved": saved}


@router.patch(
    "/interviews/{interview_id}/turns/{seq}",
    response_model=TurnRead,
    summary="Correct a misheard answer before the report",
)
async def edit_turn(
    interview_id: uuid.UUID,
    seq: int,
    body: TurnEdit,
    request: Request,
    db: DbSession,
    user: ApprovedUser,
) -> TurnRead:
    turn = await service(request, db, user).edit_turn(interview_id, seq, body.text)
    return TurnRead.model_validate(turn)


@router.post(
    "/interviews/{interview_id}/finish",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="End the call (idempotent)",
)
async def finish(
    interview_id: uuid.UUID, request: Request, db: DbSession, user: ApprovedUser
) -> None:
    await service(request, db, user).finish(interview_id)


@router.post(
    "/interviews/{interview_id}/report",
    response_model=InterviewCreated,
    status_code=status.HTTP_202_ACCEPTED,
    summary="Write the report from the transcript",
)
async def make_report(
    interview_id: uuid.UUID, request: Request, db: DbSession, user: ApprovedUser
) -> InterviewCreated:
    interview, task = await service(request, db, user).start_report(interview_id)
    return InterviewCreated(interview_id=interview.id, task_id=task.id)


@router.delete(
    "/interviews/{interview_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Delete an interview, its transcript and report",
)
async def delete_interview(
    interview_id: uuid.UUID, request: Request, db: DbSession, user: ApprovedUser
) -> None:
    await service(request, db, user).delete(interview_id)
