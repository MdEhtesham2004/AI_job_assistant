"""Phase 6 diagnostics: prove that workers, PDF rendering, storage and the AI client work."""

from datetime import UTC, datetime
from html import escape
from typing import Any

from pydantic import BaseModel, Field

from app.integrations.storage import make_key
from app.models.accounts import User
from app.services.ai import AiService
from app.workers.runner import RetryableTaskError, TaskContext, handler

TEST_PDF_TEMPLATE = """<!doctype html>
<html><head><meta charset="utf-8"><title>Test PDF</title>
<style>
  body {{ font-family: Arial, sans-serif; margin: 40px; color: #1f2937; }}
  h1 {{ color: #3b4fd8; margin-bottom: 4px; }}
  .muted {{ color: #6b7280; }}
  td {{ padding: 4px 16px 4px 0; }}
</style></head>
<body>
  <h1>AI Job Assistant</h1>
  <p class="muted">Background-worker test document</p>
  <table>
    <tr><td>Generated for</td><td><strong>{name}</strong></td></tr>
    <tr><td>Generated at</td><td>{time} UTC</td></tr>
    <tr><td>Task</td><td>{task_id}</td></tr>
  </table>
  <p>If you can read this, the task queue, the worker, Gotenberg and file storage work.</p>
</body></html>"""


@handler("test_pdf", "Test PDF")
async def test_pdf(ctx: TaskContext) -> dict[str, Any]:
    user = await ctx.session.get(User, ctx.user_id) if ctx.user_id else None
    html = TEST_PDF_TEMPLATE.format(
        name=escape(user.full_name if user else "system"),
        time=datetime.now(UTC).strftime("%Y-%m-%d %H:%M:%S"),
        task_id=ctx.task.id,
    )
    await ctx.progress(20)
    pdf = await ctx.services.gotenberg.html_to_pdf(html)
    await ctx.progress(70)
    stored = await ctx.services.storage.save(
        make_key(f"users/{ctx.user_id}/tasks", "test.pdf"), pdf, "application/pdf"
    )
    await ctx.progress(90)
    return {
        "file": {
            "key": stored.key,
            "name": "test.pdf",
            "size": stored.size,
            "content_type": stored.content_type,
        }
    }


@handler("test_failure", "Failure test")
async def test_failure(ctx: TaskContext) -> dict[str, Any]:
    raise RetryableTaskError("This test task always fails (to show retries).")


class AiPing(BaseModel):
    ok: bool
    message: str = Field(description="One short sentence confirming you can answer in JSON.")


@handler("ai_test", "AI connection test", link="/admin/system")
async def ai_test(ctx: TaskContext) -> dict[str, Any]:
    result = await AiService(ctx.session, ctx.services.ai).complete_json(
        user_id=ctx.user_id,
        task_type="ai_test",
        prompt_version="ai_test.v1",
        messages=[
            {"role": "system", "content": "You are a health check. Answer in JSON."},
            {"role": "user", "content": "Confirm that you are working."},
        ],
        output=AiPing,
    )
    return {
        "model": result.model,
        "answer": result.data.model_dump(),
        "input_tokens": result.input_tokens,
        "output_tokens": result.output_tokens,
        "cost_usd": str(result.cost_usd),
        "latency_ms": result.latency_ms,
        "cached": result.cached,
    }
