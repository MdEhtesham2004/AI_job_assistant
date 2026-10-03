"""Contact rules (Module 07): find emails in text, keep the evidence, check addresses."""

import re
from dataclasses import dataclass

from email_validator import EmailNotValidError, validate_email

_EMAIL = re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9-]+(?:\.[A-Za-z0-9-]+)*\.[A-Za-z]{2,}")
# "logo@2x.png" and similar are not addresses.
_NOT_EMAIL = re.compile(r"\.(png|jpe?g|gif|webp|svg|pdf)$", re.IGNORECASE)
_NO_REPLY = re.compile(r"^(no-?reply|do-?not-?reply|mailer-daemon|postmaster)@", re.IGNORECASE)
EXCERPT_CHARS = 160
FREE_MAIL = frozenset(
    {"gmail.com", "googlemail.com", "outlook.com", "hotmail.com", "yahoo.com", "yahoo.in",
     "icloud.com", "live.com", "rediffmail.com", "proton.me", "protonmail.com"}
)  # fmt: skip


# Misspelt free-mail domains (seen live: "hr…@gamil.com" in a hiring post). They may even
# have mail servers (typo-squatting), so they are "risky", never silently valid.
TYPO_DOMAINS = frozenset(
    {"gamil.com", "gmial.com", "gmai.com", "gmail.co", "gmail.con", "gmal.com", "gnail.com",
     "gmaill.com", "yahooo.com", "yaho.com", "outlok.com", "hotmial.com", "hotmai.com"}
)  # fmt: skip


def normalize(email: str) -> str:
    return email.strip().strip(".").lower()


def domain_of(email: str) -> str:
    return email.rsplit("@", 1)[-1].lower()


def is_valid_syntax(email: str) -> bool:
    try:
        validate_email(email, check_deliverability=False)
    except EmailNotValidError:
        return False
    return True


def find_emails(text: str) -> list[str]:
    """Addresses in the text, in order, without duplicates or no-reply addresses."""
    found: list[str] = []
    for match in _EMAIL.findall(text or ""):
        email = normalize(match)
        if _NOT_EMAIL.search(email) or _NO_REPLY.match(email) or email in found:
            continue
        if is_valid_syntax(email):
            found.append(email)
    return found


def excerpt(text: str, email: str, width: int = EXCERPT_CHARS) -> str:
    """The words around the address: shown as evidence of where it was published."""
    flat = " ".join((text or "").split())
    at = flat.lower().find(email.lower())
    if at < 0:
        return flat[:width]
    start = max(0, at - width // 2)
    end = min(len(flat), at + len(email) + width // 2)
    return ("…" if start else "") + flat[start:end].strip() + ("…" if end < len(flat) else "")


@dataclass(frozen=True)
class Blocklist:
    """The user's do-not-contact entries."""

    emails: frozenset[str]
    domains: frozenset[str]

    def blocks(self, email: str) -> bool:
        email = normalize(email)
        return email in self.emails or domain_of(email) in self.domains
