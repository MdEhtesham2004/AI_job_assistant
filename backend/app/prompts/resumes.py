"""Phase 7 prompts and their structured outputs: parse, ATS analysis, improve, LinkedIn."""

import json
from typing import Any

from pydantic import BaseModel, Field

from app.integrations.ai import Message

# ---------- outputs ----------


class Experience(BaseModel):
    title: str
    company: str
    location: str | None
    start: str | None = Field(description="As written, e.g. 'Jan 2022'.")
    end: str | None = Field(description="As written, or 'Present'.")
    highlights: list[str]


class Education(BaseModel):
    degree: str
    institution: str
    start: str | None
    end: str | None
    details: str | None = Field(description="Grade, major or honours, if stated.")


class Project(BaseModel):
    name: str
    description: str
    technologies: list[str]


class ParsedResume(BaseModel):
    name: str | None
    email: str | None
    phone: str | None
    location: str | None
    links: list[str]
    headline: str | None = Field(description="Current title or one-line headline, if stated.")
    summary: str | None
    skills: list[str]
    experience: list[Experience]
    education: list[Education]
    projects: list[Project]
    certifications: list[str]


class SectionScores(BaseModel):
    structure: int
    content: int
    keywords: int
    formatting: int


class AtsAnalysis(BaseModel):
    ats_score: int = Field(description="0-100.")
    section_scores: SectionScores = Field(description="Each 0-100.")
    strengths: list[str] = Field(description="At most 5.")
    missing_skills: list[str] = Field(description="At most 5, relevant to the top roles.")
    top_roles: list[str] = Field(description="At most 5 job titles this resume fits best.")
    suggestions: list[str] = Field(description="At most 5 concrete, actionable improvements.")


class LinkedInSummary(BaseModel):
    headline: str = Field(description="At most 220 characters.")
    about: str = Field(description="3-5 short paragraphs, first person.")


# ---------- prompts ----------

PARSE_VERSION = "resume_parse.v1"
ATS_VERSION = "resume_ats.v1"
IMPROVE_VERSION = "resume_improve.v2"
LINKEDIN_VERSION = "linkedin_summary.v1"

_TRUTH_RULE = (
    "Never invent facts. Use only employers, job titles, institutions, degrees, dates, "
    "skills and numbers that appear in the resume."
)


def parse_messages(text: str) -> list[Message]:
    return [
        {
            "role": "system",
            "content": "You extract structured data from resumes. Copy values as written; "
            "use null or an empty list when something is missing. " + _TRUTH_RULE,
        },
        {"role": "user", "content": f"Resume text:\n\n{text}"},
    ]


def ats_messages(text: str) -> list[Message]:
    return [
        {
            "role": "system",
            "content": "You are an ATS (applicant tracking system) and recruiting expert. "
            "Rate the resume for general ATS quality — not for one specific job. "
            "structure: clear standard sections and order. content: impact, metrics, "
            "action verbs. keywords: relevant hard skills for the candidate's field. "
            "formatting: parseable layout, consistent dates, no tables/graphics issues. "
            "ats_score is the overall score. Be honest and specific; each list at most 5 items.",
        },
        {"role": "user", "content": f"Resume text:\n\n{text}"},
    ]


def improve_messages(parsed: dict[str, Any], report: dict[str, Any]) -> list[Message]:
    return [
        {
            "role": "system",
            "content": "You rewrite resumes to score better with ATS while staying truthful. "
            "Improve wording only: summary, bullet highlights (strong action verbs, keep any "
            "numbers exactly), skill ordering. Keep every experience, education entry and "
            "project. Rephrase what is stated — never add outcomes, impact, responsibilities, "
            "seniority or claims that the original does not state (no 'drove revenue growth', "
            "'led the team', 'proactive monitoring' unless written there). Do not add "
            "employers, titles, institutions, degrees, certifications or skills that are not "
            "in the original. Do not change dates or job titles. " + _TRUTH_RULE,
        },
        {
            "role": "user",
            "content": "Original resume (JSON):\n"
            + json.dumps(parsed, ensure_ascii=False)
            + "\n\nATS report to address:\n"
            + json.dumps(report, ensure_ascii=False),
        },
    ]


def improve_retry_message(problems: list[str]) -> Message:
    return {
        "role": "user",
        "content": "Your rewrite added facts that are not in the original resume: "
        + "; ".join(problems)
        + ". Remove them and answer again, using only facts from the original.",
    }


def linkedin_messages(parsed: dict[str, Any]) -> list[Message]:
    return [
        {
            "role": "system",
            "content": "You write LinkedIn profiles. Write a headline (max 220 characters, "
            "role + key skills + value) and an About section in first person, warm and "
            "professional, no hashtags or emojis. " + _TRUTH_RULE,
        },
        {"role": "user", "content": "Resume (JSON):\n" + json.dumps(parsed, ensure_ascii=False)},
    ]
