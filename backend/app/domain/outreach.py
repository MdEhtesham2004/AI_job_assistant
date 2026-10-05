"""Outreach rules (Module 08): idempotency, send schedule, MIME message. No I/O."""

import hashlib
import re
import uuid
from collections.abc import Iterable
from dataclasses import dataclass
from datetime import datetime, timedelta
from email.headerregistry import Address
from email.message import EmailMessage
from email.policy import SMTP
from email.utils import formatdate, make_msgid
from zoneinfo import ZoneInfo

from app.models.enums import EmailType

IDEMPOTENCY_HEADER = "X-App-Idempotency-Key"


def idempotency_key(user_id: uuid.UUID, application_id: uuid.UUID, email_type: EmailType) -> str:
    """sha256(user_id | application_id | email_type) — Phase 0 §5.7."""
    return hashlib.sha256(f"{user_id}|{application_id}|{email_type.value}".encode()).hexdigest()


class SendingDisabledError(ValueError):
    """The daily cap is 0."""


@dataclass(frozen=True)
class SendRules:
    daily_cap: int
    interval_seconds: int
    window_start_hour: int  # when sending resumes the next day (local time)
    tz: ZoneInfo


def next_slot(
    now: datetime, taken: Iterable[datetime], rules: SendRules, jitter_seconds: int = 0
) -> datetime:
    """The earliest send time that respects the minimum gap and the daily cap.

    `taken`: send times already used or reserved (sent, queued, sending) — at most
    `daily_cap` of them may fall on one local calendar day.
    """
    if rules.daily_cap <= 0:
        raise SendingDisabledError("Sending is turned off (daily cap is 0).")
    slots = sorted(taken)
    gap = timedelta(seconds=rules.interval_seconds + max(0, jitter_seconds))
    candidate = max([now, *(slot + gap for slot in slots)]) if slots else now
    for _ in range(366):
        day = candidate.astimezone(rules.tz).date()
        used = sum(1 for slot in slots if slot.astimezone(rules.tz).date() == day)
        if used < rules.daily_cap:
            return candidate
        next_day = datetime.combine(
            day + timedelta(days=1), datetime.min.time(), tzinfo=rules.tz
        ).replace(hour=rules.window_start_hour)
        candidate = next_day + timedelta(seconds=max(0, jitter_seconds))
    raise SendingDisabledError("No send slot available.")  # pragma: no cover


@dataclass(frozen=True)
class Attachment:
    file_name: str
    mime_type: str
    data: bytes


def build_message(
    *,
    from_address: str,
    from_name: str | None,
    to_address: str,
    subject: str,
    body: str,
    attachments: list[Attachment],
    idempotency: str,
    message_id: str | None = None,
    in_reply_to: str | None = None,
    html: str | None = None,
) -> tuple[bytes, str]:
    """The RFC 5322 message and the Message-ID we set (Gmail may replace it).

    `in_reply_to`: the Message-ID Gmail gave the original — follow-ups join its thread.
    `html`: optional HTML version of `body` (multipart/alternative; e.g. the daily digest).
    """
    message = EmailMessage(policy=SMTP)
    local, _, domain = from_address.partition("@")
    message["From"] = Address(display_name=from_name or "", username=local, domain=domain)
    message["To"] = to_address
    message["Subject"] = subject
    message["Date"] = formatdate(localtime=False, usegmt=True)
    message_id = message_id or make_msgid(domain=domain or None)
    message["Message-ID"] = message_id
    message[IDEMPOTENCY_HEADER] = idempotency
    if in_reply_to:
        message["In-Reply-To"] = in_reply_to
        message["References"] = in_reply_to
    message.set_content(body)
    if html:
        message.add_alternative(html, subtype="html")
    for item in attachments:
        maintype, _, subtype = item.mime_type.partition("/")
        message.add_attachment(
            item.data, maintype=maintype, subtype=subtype or "octet-stream", filename=item.file_name
        )
    return message.as_bytes(), message_id


# ---------- replies (Phase 13) ----------

_BOUNCE_SENDERS = re.compile(r"^(mailer-daemon|postmaster|mail-daemon)@", re.IGNORECASE)
_BOUNCE_SUBJECT = re.compile(
    r"delivery status notification|undeliverable|undelivered mail|mail delivery (failed|subsystem)|"
    r"delivery (has )?failed|returned mail|failure notice",
    re.IGNORECASE,
)
_NO_CONTACT = re.compile(
    r"\b(do not|don't|dont|please stop|stop) (contact|email|mail|message|write to)(ing)? me\b|"
    r"\bunsubscribe\b|\bremove me from\b",
    re.IGNORECASE,
)
CONFIDENCE_AUTO = 0.80  # at or above: change the status; below: ask the user


def is_bounce(from_address: str, subject: str) -> bool:
    return bool(_BOUNCE_SENDERS.match(from_address) or _BOUNCE_SUBJECT.search(subject))


def asks_not_to_be_contacted(text: str) -> bool:
    return bool(_NO_CONTACT.search(text))


def reply_subject(subject: str) -> str:
    return subject if subject.lower().startswith("re:") else f"Re: {subject}"
