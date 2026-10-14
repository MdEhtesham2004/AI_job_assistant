"""Phase 13 prompts: classify a recruiter's reply, write a short follow-up."""

from typing import Literal

from pydantic import BaseModel, Field

from app.integrations.ai import Message

CLASSIFY_VERSION = "reply_classify.v1"
FOLLOW_UP_VERSION = "follow_up.v1"

Category = Literal["interview_invite", "info_request", "rejection", "offer", "auto_reply", "other"]


class ReplyReading(BaseModel):
    category: Category = Field(
        description="interview_invite: asks to schedule a call/interview/test; info_request: "
        "asks for information (notice period, salary, documents); rejection: not moving "
        "forward; offer: a job offer; auto_reply: out-of-office or automatic acknowledgement; "
        "other: anything else written by a person."
    )
    confidence: float = Field(ge=0, le=1, description="How sure you are, 0-1.")
    summary: str = Field(description="One sentence: what the reply says.")
    suggested_action: str = Field(
        description="One short next step for the candidate, e.g. 'Reply with 2-3 time slots'. "
        "Empty for auto replies."
    )


def classify_messages(
    *, job_title: str, company: str, sent_text: str, reply_from: str, reply_text: str
) -> list[Message]:
    return [
        {
            "role": "system",
            "content": "You read replies to a job application email and classify them. Judge "
            "only by what the reply says; quoted earlier messages are context, not the reply. "
            "Be conservative: use a high confidence only when the meaning is clear.",
        },
        {
            "role": "user",
            "content": f"Job: {job_title} at {company or 'unknown company'}\n\n"
            f"Our application email (excerpt):\n{sent_text[:1500]}\n\n"
            f"Reply from {reply_from}:\n{reply_text[:6000]}",
        },
    ]


class FollowUpDraft(BaseModel):
    paragraphs: list[str] = Field(
        description="1-2 short paragraphs, 40-90 words in total. No greeting, no sign-off."
    )


def follow_up_messages(*, job_title: str, company: str, sent_text: str, days: int) -> list[Message]:
    return [
        {
            "role": "system",
            "content": "You write a brief, polite follow-up to a job application email that got "
            "no answer. Mention the role, say you are still very interested, offer to share "
            "anything else they need. Do not repeat the whole application, do not add new "
            "claims about the candidate, no pressure, no placeholders, plain text, no greeting "
            "and no sign-off (added automatically).",
        },
        {
            "role": "user",
            "content": f"Role: {job_title} at {company or 'the company'}. Sent {days} days ago:\n"
            f"{sent_text[:2000]}",
        },
    ]
