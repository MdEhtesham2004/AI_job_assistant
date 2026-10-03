"""Phase 12 prompts: read a LinkedIn hiring post, draft an application email."""

import json
from typing import Any

from pydantic import BaseModel, Field

from app.integrations.ai import Message

POST_VERSION = "linkedin_post.v1"
EMAIL_VERSION = "application_email.v1"


class PostDetails(BaseModel):
    is_hiring: bool = Field(
        description="True only if the author is hiring for a role (not a job seeker, "
        "not a course or an advert)."
    )
    job_title: str = Field(description="The role being hired for, as written. Empty if not stated.")
    company: str = Field(description="The hiring company. Empty if not stated — never guess.")
    location: str = Field(description="City/country or 'Remote'. Empty if not stated.")
    contact_name: str = Field(
        description="Name of the person to write to, if the post names one. Empty otherwise."
    )


def post_messages(text: str, author_name: str | None, author_headline: str | None) -> list[Message]:
    return [
        {
            "role": "system",
            "content": "You read LinkedIn posts and extract job details. Use only what the "
            "post says; use an empty string when something is not stated. Never guess a "
            "company from the author's headline unless the post says they hire for it.",
        },
        {
            "role": "user",
            "content": f"Author: {author_name or '-'} ({author_headline or '-'})\n\nPost:\n{text}",
        },
    ]


class EmailDraft(BaseModel):
    subject: str = Field(description="Short subject: 'Application for <role> – <candidate name>'.")
    paragraphs: list[str] = Field(
        description="2-3 short body paragraphs, 100-170 words in total. No greeting, no "
        "sign-off, no signature."
    )


def email_messages(
    resume: dict[str, Any],
    job: dict[str, Any],
    *,
    found_via: str,
    attachments: list[str],
    do_not_claim: list[str],
) -> list[Message]:
    avoid = (
        " The candidate does NOT have: " + ", ".join(do_not_claim) + " — do not claim them."
        if do_not_claim
        else ""
    )
    return [
        {
            "role": "system",
            "content": "You write short, specific job application emails in first person, "
            "plain text. Paragraph 1: the exact role, the company (if known) and where the "
            f"candidate found it ({found_via}). Paragraph 2: two or three concrete matches "
            "between the resume and the job, using the resume's own words. Last paragraph: "
            f"say that {' and '.join(attachments)} {'is' if len(attachments) == 1 else 'are'} "
            "attached and ask for a conversation. Never invent facts: only employers, titles, "
            "skills, projects and numbers from the resume. No markdown, no placeholders such "
            "as [Name], no greeting and no sign-off (they are added automatically)." + avoid,
        },
        {
            "role": "user",
            "content": "Resume (JSON):\n"
            + json.dumps(resume, ensure_ascii=False)
            + "\n\nJob (JSON):\n"
            + json.dumps(job, ensure_ascii=False),
        },
    ]
