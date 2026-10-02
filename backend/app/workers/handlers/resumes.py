"""Phase 7 resume tasks: parse, ATS analysis, improved resume PDF, LinkedIn summary."""

import uuid
from pathlib import PurePath
from typing import Any

from app.core.errors import AppError, ExternalServiceError
from app.integrations.storage import make_key
from app.models.enums import ParseStatus, ResumeKind
from app.models.resumes import ResumeAtsReport, ResumeVersion
from app.prompts import resumes as prompts
from app.prompts.resumes import AtsAnalysis, LinkedInSummary, ParsedResume
from app.repositories.resumes import (
    ResumeAtsReportRepository,
    ResumeRepository,
    ResumeVersionRepository,
)
from app.services.ai import AiService
from app.services.resume_files import PDF_MIME
from app.services.resume_improve import render_html, resume_text, ungrounded_facts
from app.workers.runner import TaskContext, handler

MAX_ITEMS = 5
HEADLINE_MAX = 220


class ResumeTaskError(AppError):
    status_code = 409
    code = "RESUME_TASK_FAILED"


def _owner(ctx: TaskContext) -> uuid.UUID:
    if ctx.user_id is None:
        raise ResumeTaskError("Resume tasks need an owner.")
    return ctx.user_id


async def _version(ctx: TaskContext) -> ResumeVersion:
    version_id = uuid.UUID(str(ctx.task.payload.get("version_id")))
    version = await ResumeVersionRepository(ctx.session, owner_id=_owner(ctx)).get(version_id)
    if version is None:
        raise ResumeTaskError("The resume version no longer exists.")
    return version


async def _report(ctx: TaskContext, version: ResumeVersion) -> ResumeAtsReport:
    reports = ResumeAtsReportRepository(ctx.session, owner_id=_owner(ctx))
    report = await reports.latest_for(version.id)
    if report is None:
        raise ResumeTaskError("Run the ATS analysis first.")
    return report


def _parsed(version: ResumeVersion) -> ParsedResume:
    if version.parse_status is not ParseStatus.PARSED or version.parsed is None:
        raise ResumeTaskError("The resume is not parsed yet.")
    return ParsedResume.model_validate(version.parsed)


def _ai(ctx: TaskContext) -> AiService:
    return AiService(ctx.session, ctx.services.ai)


def _text(ctx: TaskContext, version: ResumeVersion) -> str:
    return (version.text_content or "")[: ctx.services.settings.resume_ai_max_chars]


def _score(value: int) -> int:
    return max(0, min(100, int(value)))


def _clean(items: list[str]) -> list[str]:
    seen: list[str] = []
    for item in items:
        item = item.strip()
        if item and item.lower() not in (s.lower() for s in seen):
            seen.append(item)
    return seen[:MAX_ITEMS]


@handler("resume_parse", "Resume parsing", link="/resumes")
async def resume_parse(ctx: TaskContext) -> dict[str, Any]:
    version = await _version(ctx)
    await ctx.progress(10)
    try:
        result = await _ai(ctx).complete_json(
            user_id=ctx.user_id,
            task_type="resume_parse",
            prompt_version=prompts.PARSE_VERSION,
            messages=prompts.parse_messages(_text(ctx, version)),
            output=ParsedResume,
        )
    except AppError as exc:
        retrying = (
            isinstance(exc, ExternalServiceError)
            and ctx.task.attempts <= ctx.services.settings.task_max_retries
        )
        if not retrying:  # last attempt: show the failure on the version itself
            version.parse_status = ParseStatus.FAILED
            version.parse_error = exc.message
            await ctx.session.commit()
        raise
    version.parsed = result.data.model_dump()
    version.parse_status = ParseStatus.PARSED
    version.parse_error = None
    return {
        "version_id": str(version.id),
        "skills": len(result.data.skills),
        "experience": len(result.data.experience),
    }


@handler("resume_ats", "ATS analysis", link="/resumes")
async def resume_ats(ctx: TaskContext) -> dict[str, Any]:
    version = await _version(ctx)
    await ctx.progress(10)
    result = await _ai(ctx).complete_json(
        user_id=ctx.user_id,
        task_type="resume_ats",
        prompt_version=prompts.ATS_VERSION,
        messages=prompts.ats_messages(_text(ctx, version)),
        output=AtsAnalysis,
    )
    data = result.data
    report = await ResumeAtsReportRepository(ctx.session, owner_id=_owner(ctx)).add(
        ResumeAtsReport(
            resume_version_id=version.id,
            ats_score=_score(data.ats_score),
            section_scores={k: _score(v) for k, v in data.section_scores.model_dump().items()},
            strengths=_clean(data.strengths),
            missing_skills=_clean(data.missing_skills),
            top_roles=_clean(data.top_roles),
            suggestions=_clean(data.suggestions),
            model=result.model,
            prompt_version=prompts.ATS_VERSION,
        )
    )
    return {
        "version_id": str(version.id),
        "report_id": str(report.id),
        "ats_score": report.ats_score,
    }


@handler("resume_improve", "Improved resume", link="/resumes")
async def resume_improve(ctx: TaskContext) -> dict[str, Any]:
    source = await _version(ctx)
    original = _parsed(source)
    report = await _report(ctx, source)
    report_input = {
        "ats_score": report.ats_score,
        "missing_skills": report.missing_skills,
        "suggestions": report.suggestions,
    }
    messages = prompts.improve_messages(original.model_dump(), report_input)
    source_text = source.text_content or ""

    improved: ParsedResume | None = None
    problems: list[str] = []
    for attempt in range(2):  # one retry when the AI adds facts
        await ctx.progress(10 + attempt * 30)
        result = await _ai(ctx).complete_json(
            user_id=ctx.user_id,
            task_type="resume_improve",
            prompt_version=prompts.IMPROVE_VERSION,
            messages=messages,
            output=ParsedResume,
        )
        candidate = result.data.model_copy(
            update={  # identity and contact details are never rewritten
                "name": original.name,
                "headline": original.headline,
                "email": original.email,
                "phone": original.phone,
                "location": original.location,
                "links": original.links,
            }
        )
        problems = ungrounded_facts(candidate, original, source_text)
        if not problems:
            improved = candidate
            break
        messages = [
            *messages,
            {"role": "assistant", "content": result.data.model_dump_json()},
            prompts.improve_retry_message(problems),
        ]
    if improved is None:
        raise ResumeTaskError(
            "The AI kept adding facts that are not in your resume ("
            + ", ".join(problems[:5])
            + "). Nothing was saved — please try again."
        )

    await ctx.progress(70)
    html = render_html(improved)
    pdf = await ctx.services.gotenberg.html_to_pdf(html)
    file_name = f"{PurePath(source.file_name).stem}-improved.pdf"
    stored = await ctx.services.storage.save(
        make_key(f"users/{ctx.user_id}/resumes", file_name), pdf, PDF_MIME
    )
    await ctx.progress(90)

    await ResumeRepository(ctx.session, owner_id=_owner(ctx)).get_for_update()
    versions = ResumeVersionRepository(ctx.session, owner_id=_owner(ctx))
    version = await versions.add(
        ResumeVersion(
            resume_id=source.resume_id,
            version_no=await versions.next_version_no(source.resume_id),
            kind=ResumeKind.IMPROVED,
            derived_from_id=source.id,
            file_key=stored.key,
            file_name=file_name,
            mime_type=PDF_MIME,
            file_size=stored.size,
            text_content=resume_text(improved),
            parsed=improved.model_dump(),
            parse_status=ParseStatus.PARSED,
            content_html=html,
        )
    )
    return {
        "version_id": str(version.id),
        "version_no": version.version_no,
        "file": {
            "key": stored.key,
            "name": file_name,
            "size": stored.size,
            "content_type": PDF_MIME,
        },
    }


@handler("resume_linkedin", "LinkedIn summary", link="/resumes")
async def resume_linkedin(ctx: TaskContext) -> dict[str, Any]:
    version = await _version(ctx)
    parsed = _parsed(version)
    report = await _report(ctx, version)
    await ctx.progress(10)
    result = await _ai(ctx).complete_json(
        user_id=ctx.user_id,
        task_type="resume_linkedin",
        prompt_version=prompts.LINKEDIN_VERSION,
        messages=prompts.linkedin_messages(parsed.model_dump()),
        output=LinkedInSummary,
    )
    summary = {
        "headline": result.data.headline.strip()[:HEADLINE_MAX],
        "about": result.data.about.strip(),
    }
    report.linkedin_summary = summary
    return {"version_id": str(version.id), **summary}
