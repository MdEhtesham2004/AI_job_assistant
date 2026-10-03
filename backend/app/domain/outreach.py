"""Outreach rules (Module 08): idempotency, send schedule, MIME message. No I/O."""

import hashlib
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
) -> tuple[bytes, str]:
    """The RFC 5322 message and its Message-ID (kept to find the mail again in Gmail)."""
    message = EmailMessage(policy=SMTP)
    local, _, domain = from_address.partition("@")
    message["From"] = Address(display_name=from_name or "", username=local, domain=domain)
    message["To"] = to_address
    message["Subject"] = subject
    message["Date"] = formatdate(localtime=False, usegmt=True)
    message_id = message_id or make_msgid(domain=domain or None)
    message["Message-ID"] = message_id
    message[IDEMPOTENCY_HEADER] = idempotency
    message.set_content(body)
    for item in attachments:
        maintype, _, subtype = item.mime_type.partition("/")
        message.add_attachment(
            item.data, maintype=maintype, subtype=subtype or "octet-stream", filename=item.file_name
        )
    return message.as_bytes(), message_id
