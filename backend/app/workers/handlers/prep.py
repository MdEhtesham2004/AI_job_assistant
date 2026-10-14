"""Phase 17 task: write the interview prep pack (+ PDF)."""

import uuid
from typing import Any

from app.core.errors import AppError
from app.services.prep import TASK, generate_prep
from app.workers.runner import TaskContext, handler


class PrepTaskError(AppError):
    status_code = 409
    code = "PREP_TASK_FAILED"


@handler(TASK, "Interview prep pack", link="/jobs")
async def interview_prep(ctx: TaskContext) -> dict[str, Any]:
    if ctx.user_id is None:
        raise PrepTaskError("This task needs an owner.")
    await ctx.progress(10)
    record = await generate_prep(
        ctx.session,
        ai=ctx.services.ai,
        gotenberg=ctx.services.gotenberg,
        storage=ctx.services.storage,
        user_id=ctx.user_id,
        job_id=uuid.UUID(str(ctx.task.payload["job_id"])),
    )
    ctx.notify_on_success = False  # generate_prep sends its own notification
    return {"job_id": str(record.job_id), "questions": len(record.pack["likely_questions"])}
