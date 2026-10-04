"""Phase 12 tasks: find LinkedIn hiring posts, draft an application email, send it."""

import uuid
from typing import Any

from app.core.errors import AppError
from app.models.enums import NotificationSeverity
from app.services.contacts import discover_linkedin
from app.services.notifications import notify
from app.services.outreach import EmailSender, generate_draft
from app.services.usage import Meter, MeteredPostSource
from app.workers.runner import TaskContext, handler


class OutreachTaskError(AppError):
    status_code = 409
    code = "OUTREACH_TASK_FAILED"


def _owner(ctx: TaskContext) -> uuid.UUID:
    if ctx.user_id is None:
        raise OutreachTaskError("Outreach tasks need an owner.")
    return ctx.user_id


@handler("contact_discover", "LinkedIn hiring posts", link="/contacts")
async def contact_discover(ctx: TaskContext) -> dict[str, Any]:
    owner = _owner(ctx)
    payload = ctx.task.payload
    await ctx.progress(5)
    result = await discover_linkedin(
        ctx.session,
        ai=ctx.services.ai,
        # Shared cache + per-user quota + usage log (Phase 14 cost control).
        source=MeteredPostSource(
            Meter(ctx.session, ctx.services.settings, ctx.services.redis, owner),
            ctx.services.posts,
        ),
        checker=ctx.services.domains,
        user_id=owner,
        keyword=str(payload["keyword"]),
        max_posts=int(payload.get("max_posts", ctx.services.settings.apify_max_posts)),
        posted_limit=payload.get("posted_limit", "week"),
        progress=ctx.progress,
    )
    ctx.notify_on_success = False
    notify(
        ctx.session,
        owner,
        type="contacts_found",
        title=f"LinkedIn: {result.new_contacts} new contact(s) for “{payload['keyword']}”",
        body=f"{result.posts} posts read, {result.jobs} hiring posts with an email. "
        "Review and approve the contacts before any email goes out.",
        link="/contacts?approval=pending",
        severity=NotificationSeverity.SUCCESS,
    )
    return result.as_dict()


@handler("email_draft", "Application email", link="/outbox")
async def email_draft(ctx: TaskContext) -> dict[str, Any]:
    owner = _owner(ctx)
    await ctx.progress(10)
    email = await generate_draft(
        ctx.session,
        ai=ctx.services.ai,
        settings=ctx.services.settings,
        user_id=owner,
        application_id=uuid.UUID(str(ctx.task.payload["application_id"])),
    )
    ctx.notify_on_success = False  # generate_draft sends its own notification
    return {"email_id": str(email.id), "application_id": str(email.application_id)}


@handler("email_send", "Send email", link="/outbox")
async def email_send(ctx: TaskContext) -> dict[str, Any]:
    owner = _owner(ctx)
    ctx.notify_on_success = False  # sent / failed notifications come from the sender
    outcome = await EmailSender(
        ctx.session, owner, ctx.services.settings, ctx.services.storage
    ).send(uuid.UUID(str(ctx.task.payload["email_id"])))
    return outcome.as_dict()
