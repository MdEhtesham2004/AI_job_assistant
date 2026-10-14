"""Phase 16 tasks: daily digest, skill-gap learning plan, screening answers."""

import uuid
from typing import Any

from app.core.errors import AppError
from app.services.hunt import build_digest, generate_answers, generate_skill_plan
from app.workers.runner import TaskContext, handler


class HuntTaskError(AppError):
    status_code = 409
    code = "HUNT_TASK_FAILED"


def _owner(ctx: TaskContext) -> uuid.UUID:
    if ctx.user_id is None:
        raise HuntTaskError("This task needs an owner.")
    return ctx.user_id


@handler("daily_digest", "Daily job digest", link="/")
async def daily_digest(ctx: TaskContext) -> dict[str, Any]:
    owner = _owner(ctx)
    await ctx.progress(5)
    outcome = await build_digest(
        ctx.session,
        ai=ctx.services.ai,
        settings=ctx.services.settings,
        user_id=owner,
        force=bool(ctx.task.payload.get("force")),
    )
    ctx.notify_on_success = False  # the digest sends its own notification (when it has jobs)
    digest = outcome.digest
    return {
        "jobs": len(digest.jobs) if digest else 0,
        "new_jobs": digest.new_jobs if digest else 0,
        "scored": digest.scored if digest else 0,
        "emailed": bool(digest and digest.emailed),
        "note": outcome.reason,
    }


@handler("skill_plan", "Skill-gap learning plan", link="/skills")
async def skill_plan(ctx: TaskContext) -> dict[str, Any]:
    owner = _owner(ctx)
    await ctx.progress(10)
    record = await generate_skill_plan(ctx.session, ai=ctx.services.ai, user_id=owner)
    ctx.notify_on_success = False
    return {"plan_id": str(record.id), "skills": [g["skill"] for g in record.gaps]}


@handler("screening_answers", "Screening answers", link="/jobs")
async def screening_answers(ctx: TaskContext) -> dict[str, Any]:
    owner = _owner(ctx)
    await ctx.progress(10)
    record = await generate_answers(
        ctx.session,
        ai=ctx.services.ai,
        user_id=owner,
        job_id=uuid.UUID(str(ctx.task.payload["job_id"])),
        custom_questions=list(ctx.task.payload.get("custom_questions") or []),
    )
    return {"job_id": str(record.job_id), "answers": len(record.answers)}
