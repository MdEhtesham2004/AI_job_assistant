"""Phase 13/20 task: one apply-pipeline run for one user → approval queue (Outbox)."""

from typing import Any

from app.core.errors import AppError
from app.services.automation import Tools, run_pipeline
from app.workers.runner import TaskContext, handler


class AutomationTaskError(AppError):
    status_code = 409
    code = "AUTOMATION_FAILED"


@handler("automation_run", "Apply pipeline", link="/outbox")
async def automation_run(ctx: TaskContext) -> dict[str, Any]:
    if ctx.user_id is None:
        raise AutomationTaskError("Automation runs need an owner.")
    services = ctx.services
    await ctx.progress(5)
    result = await run_pipeline(
        ctx.session,
        Tools(
            settings=services.settings,
            ai=services.ai,
            gotenberg=services.gotenberg,
            storage=services.storage,
        ),
        ctx.user_id,
        ctx.progress,
    )
    ctx.notify_on_success = False  # run_pipeline sends the summary notification
    return result.as_dict()
