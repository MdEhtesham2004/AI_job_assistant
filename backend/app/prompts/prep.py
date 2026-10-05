"""Phase 17 prompt: the interview prep pack for one job."""

import json
from typing import Any

from pydantic import BaseModel, Field

from app.integrations.ai import Message

PREP_VERSION = "interview_prep.v1"


class FitItem(BaseModel):
    requirement: str = Field(description="A key requirement from the job")
    evidence: str = Field(
        description="Where the resume shows it (employer, project, number) — or 'Not shown "
        "in your resume' when it is a gap"
    )


class LikelyQuestion(BaseModel):
    question: str
    why: str = Field(description="Why this employer is likely to ask it, one sentence")
    how_to_answer: str = Field(
        description="2-3 sentences of advice using the candidate's real experience"
    )


class StarStory(BaseModel):
    title: str = Field(description="Short name, e.g. 'Cutting the crash rate at Acme'")
    situation: str
    task: str
    action: str
    result: str = Field(description="Only results stated in the resume; no invented numbers")
    use_for: list[str] = Field(description="Which likely questions this story answers")


class GapAnswer(BaseModel):
    gap: str
    honest_answer: str = Field(
        description="How to answer honestly: what is related, what is being learned"
    )


class PrepPack(BaseModel):
    role_summary: str = Field(description="3-4 sentences: what the role is really about")
    what_they_value: list[str] = Field(description="3-5 things the employer cares about most")
    your_fit: list[FitItem] = Field(description="4-6 key requirements")
    likely_questions: list[LikelyQuestion] = Field(description="6-8 questions, most likely first")
    star_stories: list[StarStory] = Field(description="Exactly 3, built from the resume")
    gaps: list[GapAnswer] = Field(description="0-4 gaps the interviewer may probe")
    questions_to_ask: list[str] = Field(description="4-5 thoughtful questions for them")
    checklist: list[str] = Field(description="4-6 short day-before items")


def prep_messages(
    *, job: dict[str, Any], resume: dict[str, Any], missing_skills: list[str]
) -> list[Message]:
    gaps = (
        " The match analysis found these missing skills: " + ", ".join(missing_skills[:8]) + "."
        if missing_skills
        else ""
    )
    return [
        {
            "role": "system",
            "content": "You are an experienced interview coach preparing a candidate for a real "
            "interview for this job. Be specific to this job and this candidate. Never invent "
            "facts: use only employers, projects, skills, dates and numbers from the resume. "
            "STAR stories must come from real resume experience; if a result has no number in "
            "the resume, describe it without one. Name gaps honestly." + gaps + " Plain text, "
            "no markdown. English only.",
        },
        {
            "role": "user",
            "content": "Job (JSON):\n"
            + json.dumps(job, ensure_ascii=False)
            + "\n\nResume (JSON):\n"
            + json.dumps(resume, ensure_ascii=False),
        },
    ]
