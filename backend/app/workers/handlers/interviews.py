"""Phase 15 tasks: write the mock-interview plan, write the report (+ PDF)."""

import uuid
from typing import Any

from app.core.errors import AppError, ExternalServiceError
from app.models.enums import InterviewStatus
from app.models.interviews import Interview
from app.repositories.interviews import InterviewRepository
from app.services.interviews import generate_plan, generate_report
from app.workers.runner import TaskContext, handler


class InterviewTaskError(AppError):
    status_code = 409
    code = "INTERVIEW_TASK_FAILED"


async def _interview(ctx: TaskContext) -> Interview:
    if ctx.user_id is None:
        raise InterviewTaskError("Interview tasks need an owner.")
    interview = await InterviewRepository(ctx.session, owner_id=ctx.user_id).get(
        uuid.UUID(str(ctx.task.payload["interview_id"]))
    )
    if interview is None:
        raise InterviewTaskError("The interview no longer exists.")
    return interview


async def _fail(
    ctx: TaskContext, interview: Interview, exc: Exception, back_to: InterviewStatus
) -> None:
    """Final failure: show it on the interview. Retries keep the status unchanged."""
    retrying = (
        isinstance(exc, ExternalServiceError)
        and ctx.task.attempts <= ctx.services.settings.task_max_retries
    )
    if not retrying:
        await ctx.session.rollback()
        interview = await ctx.session.merge(interview)
        interview.status = back_to
        interview.error = exc.message if isinstance(exc, AppError) else "Something went wrong."
        await ctx.session.commit()


@handler("interview_plan", "Mock interview plan", link="/interviews")
async def interview_plan(ctx: TaskContext) -> dict[str, Any]:
    interview = await _interview(ctx)
    await ctx.progress(10)
    try:
        await generate_plan(
            ctx.session,
            ai=ctx.services.ai,
            interview=interview,
            focus_questions=list(ctx.task.payload.get("focus_questions") or []),
        )
    except Exception as exc:
        await _fail(ctx, interview, exc, InterviewStatus.FAILED)
        raise
    ctx.notify_on_success = False  # the room is waiting for it; no notification needed
    return {
        "interview_id": str(interview.id),
        "questions": len((interview.plan or {}).get("questions", [])),
    }


@handler("interview_report", "Mock interview report", link="/interviews")
async def interview_report(ctx: TaskContext) -> dict[str, Any]:
    interview = await _interview(ctx)
    await ctx.progress(10)
    try:
        report = await generate_report(
            ctx.session,
            ai=ctx.services.ai,
            gotenberg=ctx.services.gotenberg,
            storage=ctx.services.storage,
            interview=interview,
        )
    except Exception as exc:
        # The transcript is kept: the user can simply try the report again.
        await _fail(ctx, interview, exc, InterviewStatus.ENDED)
        raise
    ctx.notify_on_success = False  # generate_report sends its own notification
    return {"interview_id": str(interview.id), "overall_score": report.overall_score}
