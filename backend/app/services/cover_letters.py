"""Cover letter rules (Module 06): compose, check, render. Pure functions — no I/O."""

import math
import re
from datetime import date
from html import escape

_WORD = re.compile(r"[0-9a-z+#]+")
_NUMBER = re.compile(r"\d+(?:\.\d+)?")
_THOUSANDS = re.compile(r"(?<=\d),(?=\d{3})")
_PLACEHOLDER = re.compile(
    r"\[[^\]]{1,40}\]|\{[^}]{1,40}\}|<[^>]{1,40}>|\b(?:your name|company name|job title|xyz)\b",
    re.IGNORECASE,
)
_LEARNING = re.compile(r"\b(learn|learning|keen to|eager to|pick up|grow into)\b", re.IGNORECASE)
_COMPANY_SUFFIXES = {"pvt", "private", "ltd", "limited", "inc", "llc", "llp", "corp", "co", "the"}
_STOP = {"and", "or", "of", "the", "a", "an", "in", "for", "with", "to", "at"}
MIN_WORDS, MAX_WORDS = 120, 450


def _words(text: str) -> list[str]:
    return _WORD.findall(text.lower())


def _numbers(text: str) -> set[str]:
    return set(_NUMBER.findall(_THOUSANDS.sub("", text)))


def compose(paragraphs: list[str], *, contact_name: str | None, candidate_name: str | None) -> str:
    greeting = (
        f"Dear {contact_name.strip()},"
        if contact_name and contact_name.strip()
        else ("Dear Hiring Team,")
    )
    body = [" ".join(p.split()) for p in paragraphs if p.strip()]
    closing = "Sincerely,\n" + (candidate_name or "")
    return "\n\n".join([greeting, *body, closing.strip()])


def body_of(content: str) -> str:
    """The letter without greeting and sign-off (for word counts and checks)."""
    parts = [p.strip() for p in content.split("\n\n") if p.strip()]
    if parts and parts[0].lower().startswith("dear "):
        parts = parts[1:]
    if parts and parts[-1].lower().startswith(("sincerely", "regards", "best", "kind regards")):
        parts = parts[:-1]
    return "\n\n".join(parts)


def _mentions(text: str, phrase: str) -> bool:
    """Does `text` claim `phrase`? Exact phrase ("React.js" ~ "react js"), or — for
    multi-word skills — at least 2/3 of its words in one sentence ("responsive designs"
    ~ "Responsive Web Design"; "React Native" is *not* "React.js")."""
    target = _words(phrase)
    if not target:
        return False
    if f" {' '.join(target)} " in " " + " ".join(_words(text)) + " ":
        return True
    if len(target) < 3:
        return False
    needed = math.ceil(len(target) * 2 / 3)
    for sentence in re.split(r"(?<=[.!?])\s+", text):
        words = _words(sentence)
        if sum(any(w.startswith(t) for w in words) for t in target) >= needed:
            return True
    return False


def problems(
    content: str,
    *,
    resume_text: str,
    job_text: str,
    company: str,
    title: str,
    lacking: list[str] | None = None,
) -> list[str]:
    """Reasons the letter is not acceptable. Empty = OK.

    `lacking`: skills the job asks for that the resume does not have (from the match
    analysis). The letter must not claim them — naming the role title does not count.
    """
    found: list[str] = []
    body = body_of(content)
    without_title = re.sub(re.escape(title), " ", body, flags=re.IGNORECASE) if title else body
    # "I am keen to learn GraphQL" is honest; only claims count.
    claims = " ".join(
        sentence
        for sentence in re.split(r"(?<=[.!?])\s+", without_title)
        if not _LEARNING.search(sentence)
    )
    claimed = [skill for skill in lacking or [] if _mentions(claims, skill)]
    if claimed:
        found.append("claims skills that are not in the resume: " + ", ".join(claimed))
    if match := _PLACEHOLDER.search(content):
        found.append(f"placeholder '{match.group(0)}'")
    # Numbers may come from the resume, the job text, or the company/role name ("Web3", "L2").
    known = _numbers(" ".join([resume_text, job_text, company, title]))
    invented = sorted(n for n in _numbers(body) if n not in known)
    if invented:
        found.append("numbers not in the resume or job: " + ", ".join(invented))
    words = set(_words(body))
    company_words = [w for w in _words(company) if w not in _COMPANY_SUFFIXES]
    if company_words and not all(w in words for w in company_words):
        found.append(f"the company '{company}' is not named")
    title_words = [w for w in _words(title) if w not in _STOP]
    # Most of the title's words must appear (all of a two-word title like "Mobile Lead").
    if title_words and sum(w in words for w in title_words) < math.ceil(len(title_words) * 0.6):
        found.append(f"the role '{title}' is not named")
    count = len(_words(body))
    if count < MIN_WORDS or count > MAX_WORDS:
        found.append(f"{count} words (aim for 200-300)")
    return found


_STYLE = """
  @page { size: A4; margin: 22mm 22mm; }
  body { font-family: Arial, Helvetica, sans-serif; font-size: 11pt; color: #111827;
         line-height: 1.55; margin: 0; }
  .from { margin-bottom: 18px; }
  .from strong { font-size: 14pt; }
  .muted { color: #4b5563; font-size: 10pt; }
  p { margin: 0 0 12px; }
"""


def render_html(
    content: str, *, name: str | None, contact_line: str, today: date | None = None
) -> str:
    today = today or date.today()
    paragraphs = "".join(
        f"<p>{escape(p.strip()).replace(chr(10), '<br>')}</p>"
        for p in content.split("\n\n")
        if p.strip()
    )
    return (
        '<!doctype html><html><head><meta charset="utf-8">'
        f"<title>Cover letter</title><style>{_STYLE}</style></head><body>"
        f'<div class="from"><strong>{escape(name or "")}</strong>'
        f'<div class="muted">{escape(contact_line)}</div></div>'
        f'<p class="muted">{today:%d %B %Y}</p>'
        f"{paragraphs}</body></html>"
    )
