"""Phase 9 prompt: how well a resume fits one job (component scores only)."""

import json
from typing import Any, Literal

from pydantic import BaseModel, Field

from app.integrations.ai import Message

MATCH_VERSION = "job_match.v2"

# v2 (live test, 2026-10-02): v1 had no scale, so scores were very low (a 4-year React Native
# developer got 40 for a React Native role) and "missing skills" listed soft skills.
_RUBRIC = (
    "Score each component on this scale: 90-100 meets or exceeds nearly everything asked; "
    "70-89 meets most requirements with small gaps; 50-69 meets some, with clear gaps; "
    "below 50 major requirements are missing. Judge against what the job requires, giving "
    "credit for equivalent or closely related experience (e.g. React Native counts toward "
    "React). Education: 100 when the job states no requirement. Location: 100 if remote or "
    "the same city; 60-80 for the same country with relocation; lower otherwise."
)


class JobMatch(BaseModel):
    skills_match: int = Field(description="0-100: required/preferred skills the candidate has.")
    experience_match: int = Field(description="0-100: years and kind of experience vs. asked.")
    technology_match: int = Field(description="0-100: tech stack / domain overlap.")
    education_match: int = Field(description="0-100: degree requirements met (100 if none).")
    location_match: int = Field(
        description="0-100: 100 if remote or same city, lower if relocation is needed."
    )
    matched_skills: list[str] = Field(description="Skills from the job that the resume has.")
    missing_skills: list[str] = Field(description="Skills the job asks for that are missing.")
    seniority_fit: Literal["below", "good", "above"]
    recommendations: list[str] = Field(
        description="At most 5 concrete tips to improve the application for this job."
    )
    red_flags: list[str] = Field(
        description="At most 5 serious mismatches (e.g. required visa, 10+ years required)."
    )


def match_messages(resume: dict[str, Any], job: dict[str, Any]) -> list[Message]:
    return [
        {
            "role": "system",
            "content": "You are a fair, experienced technical recruiter. Compare the candidate's "
            "resume with the job and score each component from 0 to 100. "
            + _RUBRIC
            + " Do not reward keywords the resume does not support. matched_skills and "
            "missing_skills are concrete technical skills, tools or languages only (no soft "
            "skills like communication, problem-solving or version control): matched = asked "
            "by the job and present in the resume; missing = asked by the job and absent from "
            "the resume. Do not compute an overall score.",
        },
        {
            "role": "user",
            "content": "Candidate resume (JSON):\n"
            + json.dumps(resume, ensure_ascii=False)
            + "\n\nJob (JSON):\n"
            + json.dumps(job, ensure_ascii=False),
        },
    ]
