"""Phase 10 prompts: tailored resume (structured) and cover letter (paragraphs)."""

import json
from typing import Any

from pydantic import BaseModel, Field

from app.integrations.ai import Message

TAILOR_VERSION = "resume_tailor.v1"
# v2 (live test 2026-10-02): v1 wrote "I led …", "CI workflows", "agile teams", "backend
# APIs" — none of it in the resume. v2 forbids leadership/tool/practice claims explicitly.
COVER_VERSION = "cover_letter.v2"

_TRUTH = (
    "Never invent facts. Use only employers, job titles, institutions, degrees, dates, "
    "skills, projects, certifications and numbers that appear in the resume."
)


def tailor_messages(
    resume: dict[str, Any], job: dict[str, Any], emphasize: list[str], do_not_claim: list[str]
) -> list[Message]:
    hints = ""
    if emphasize:
        hints += f" Emphasize these skills the candidate really has: {', '.join(emphasize)}."
    if do_not_claim:
        hints += (
            " The candidate does NOT have these skills — do not add or imply them: "
            + ", ".join(do_not_claim)
            + "."
        )
    return [
        {
            "role": "system",
            "content": "You tailor a resume to one job while staying strictly truthful. "
            "Allowed: rewrite the summary for this role, reorder skills (most relevant "
            "first), reorder and reword bullet highlights to put relevant work first, drop "
            "irrelevant bullets, keep numbers exactly. Not allowed: adding employers, titles, "
            "institutions, degrees, certifications, projects, skills, outcomes or claims that "
            "the resume does not state; changing dates or job titles. Keep every experience "
            "and education entry. " + _TRUTH + hints,
        },
        {
            "role": "user",
            "content": "Resume (JSON):\n"
            + json.dumps(resume, ensure_ascii=False)
            + "\n\nJob (JSON):\n"
            + json.dumps(job, ensure_ascii=False),
        },
    ]


class CoverLetterDraft(BaseModel):
    paragraphs: list[str] = Field(
        description="3-4 body paragraphs, 200-300 words in total. No greeting, no sign-off."
    )


def cover_messages(
    resume: dict[str, Any], job: dict[str, Any], do_not_claim: list[str]
) -> list[Message]:
    avoid = (
        " The candidate does NOT have: " + ", ".join(do_not_claim) + " — do not claim them."
        if do_not_claim
        else ""
    )
    return [
        {
            "role": "system",
            "content": "You write concise, specific cover letters in first person. Name the "
            "company and the exact job title. Connect 2-3 real achievements from the resume to "
            "the job's needs, using the resume's own verbs (if it says 'built', do not write "
            "'led'). Do not claim tools, practices or responsibilities the resume does not "
            "state (for example CI/CD, version control, agile, mentoring, backend APIs, "
            "leading a team) — you may say the candidate is keen to learn something the job "
            "asks for. No generic filler, no clichés, no placeholders such as [Name], no "
            "greeting and no sign-off (they are added automatically). " + _TRUTH + avoid,
        },
        {
            "role": "user",
            "content": "Resume (JSON):\n"
            + json.dumps(resume, ensure_ascii=False)
            + "\n\nJob (JSON):\n"
            + json.dumps(job, ensure_ascii=False),
        },
    ]


def retry_message(problems: list[str]) -> Message:
    return {
        "role": "user",
        "content": "Your answer has problems: "
        + "; ".join(problems)
        + ". Fix them and answer again, using only facts from the resume.",
    }
