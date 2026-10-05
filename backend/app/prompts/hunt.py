"""Phase 16 prompts: skill-gap learning plan, screening-answer bank."""

import json
from typing import Any

from pydantic import BaseModel, Field

from app.integrations.ai import Message

SKILL_PLAN_VERSION = "skill_plan.v1"
ANSWERS_VERSION = "screening_answers.v1"

# Shown in the answer where the resume/profile lacks the fact; the UI highlights it.
FILL_IN = "[fill in]"

_TRUTH = (
    "Never invent facts. Use only employers, job titles, projects, skills, dates and numbers "
    "that appear in the resume or profile. Do not claim skills the candidate lacks."
)

# ---------- skill-gap plan ----------


class PlanDay(BaseModel):
    day: int = Field(description="1-14")
    focus: str = Field(description="The skill this day works on")
    task: str = Field(description="One concrete, doable task for about an hour")


class SkillPlan(BaseModel):
    summary: str = Field(description="2-3 sentences: which gaps matter most and why")
    days: list[PlanDay] = Field(description="Exactly 14 days")
    mini_project: str = Field(
        description="One small portfolio project that practises the top gaps together"
    )
    resources: list[str] = Field(
        description="3-6 generic resource suggestions, e.g. 'the official GraphQL docs "
        "(Learn section)'. No made-up URLs, course names or prices."
    )
    interview_tip: str = Field(description="How to talk honestly about a skill still being learned")


def skill_plan_messages(
    *, gaps: list[dict[str, Any]], strengths: list[str], resume: dict[str, Any]
) -> list[Message]:
    return [
        {
            "role": "system",
            "content": "You are a practical career coach. Write a 2-week learning plan for the "
            "skill gaps listed (most frequent first), building on the candidate's strengths. "
            "One focused hour a day; end with a small project. " + _TRUTH + " English only.",
        },
        {
            "role": "user",
            "content": "Skill gaps (skill, number of target jobs asking for it):\n"
            + json.dumps(gaps, ensure_ascii=False)
            + "\n\nStrengths already shown:\n"
            + json.dumps(strengths, ensure_ascii=False)
            + "\n\nResume (JSON):\n"
            + json.dumps(resume, ensure_ascii=False),
        },
    ]


# ---------- screening answers ----------

STANDARD_QUESTIONS = [
    ("about", "Tell us about yourself."),
    ("why_company", "Why do you want to work at {company}?"),
    ("why_hire", "Why should we hire you for this role?"),
    ("strength", "What is your greatest professional strength?"),
    ("challenge", "Describe a challenge you faced at work and how you handled it."),
    ("why_looking", "Why are you looking for a new role?"),
    ("notice", "What is your notice period?"),
    ("salary", "What are your salary expectations?"),
]


class Answer(BaseModel):
    key: str = Field(description="The question's key, exactly as given")
    answer: str = Field(
        description="First person, 40-120 words (one sentence for notice period and salary)"
    )


class AnswerSet(BaseModel):
    answers: list[Answer]


def answer_messages(
    *,
    job: dict[str, Any],
    resume: dict[str, Any],
    facts: dict[str, str],
    questions: list[tuple[str, str]],
) -> list[Message]:
    asked = "\n".join(f"- {key}: {text}" for key, text in questions)
    known = (
        "Known facts from the candidate's profile: "
        + "; ".join(f"{k}: {v}" for k, v in facts.items())
        + "."
        if facts
        else "The profile gives no notice period or salary expectation."
    )
    return [
        {
            "role": "system",
            "content": "You write answers to job-application screening questions for the "
            "candidate, ready to paste into a form. Tailor them to this job: connect the "
            "candidate's real experience to the job's requirements. "
            + _TRUTH
            + " "
            + known
            + f" If an answer needs a fact that is not known (e.g. notice period, salary, "
            f"reason for leaving), write a short natural answer with {FILL_IN} where the fact "
            "goes — never guess it. Answer every question once, using its key. Plain text, "
            "no markdown. English only.",
        },
        {
            "role": "user",
            "content": "Questions:\n"
            + asked
            + "\n\nJob (JSON):\n"
            + json.dumps(job, ensure_ascii=False)
            + "\n\nResume (JSON):\n"
            + json.dumps(resume, ensure_ascii=False),
        },
    ]
