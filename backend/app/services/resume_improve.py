"""Improved resume: grounding check (no invented facts) and the deterministic HTML template.

The AI only writes structured content. Layout is ours, so every improved resume is
ATS-friendly (one column, real text, standard headings) and rendered the same way.
"""

import re
from html import escape

from app.prompts.resumes import ParsedResume

_NON_WORD = re.compile(r"[^0-9a-z+#]+")
_NUMBER = re.compile(r"\d+(?:\.\d+)?")
_THOUSANDS = re.compile(r"(?<=\d),(?=\d{3})")


def _norm(value: str) -> str:
    return " ".join(_NON_WORD.sub(" ", value.lower()).split())


def _numbers(text: str) -> set[str]:
    return set(_NUMBER.findall(_THOUSANDS.sub("", text)))


def ungrounded_facts(improved: ParsedResume, original: ParsedResume, source_text: str) -> list[str]:
    """Facts in `improved` that appear nowhere in the original resume. Empty = truthful."""
    known = " " + _norm(source_text) + " " + _norm(original.model_dump_json()) + " "
    known_numbers = _numbers(source_text + " " + original.model_dump_json())

    def missing(value: str | None) -> bool:
        text = _norm(value or "")
        return bool(text) and f" {text} " not in known

    problems: list[str] = []
    for job in improved.experience:
        if missing(job.company):
            problems.append(f"employer '{job.company}'")
        if missing(job.title):
            problems.append(f"job title '{job.title}'")
    for school in improved.education:
        if missing(school.institution):
            problems.append(f"institution '{school.institution}'")
        if missing(school.degree):
            problems.append(f"degree '{school.degree}'")
    for skill in improved.skills:
        if missing(skill):
            problems.append(f"skill '{skill}'")
    for certification in improved.certifications:
        if missing(certification):
            problems.append(f"certification '{certification}'")

    prose = [improved.summary or "", improved.headline or ""]
    prose += [line for job in improved.experience for line in job.highlights]
    prose += [project.description for project in improved.projects]
    for number in sorted({n for line in prose for n in _numbers(line)}):
        if number not in known_numbers:
            problems.append(f"number '{number}'")
    return problems


def resume_text(resume: ParsedResume) -> str:
    """Plain text of a structured resume (stored as the version's text_content)."""
    lines = [resume.name or "", resume.headline or ""]
    lines.append(" | ".join(v for v in [resume.email, resume.phone, resume.location] if v))
    lines += resume.links
    if resume.summary:
        lines += ["", "SUMMARY", resume.summary]
    if resume.skills:
        lines += ["", "SKILLS", ", ".join(resume.skills)]
    if resume.experience:
        lines += ["", "EXPERIENCE"]
        for job in resume.experience:
            lines.append(f"{job.title}, {job.company} ({_dates(job.start, job.end)})")
            lines += [f"- {item}" for item in job.highlights]
    if resume.projects:
        lines += ["", "PROJECTS"]
        for project in resume.projects:
            lines.append(f"{project.name}: {project.description}")
    if resume.education:
        lines += ["", "EDUCATION"]
        for school in resume.education:
            lines.append(
                f"{school.degree}, {school.institution} ({_dates(school.start, school.end)})"
            )
    if resume.certifications:
        lines += ["", "CERTIFICATIONS", *resume.certifications]
    return "\n".join(lines).strip()


def _dates(start: str | None, end: str | None) -> str:
    return " – ".join(v for v in [start, end] if v)


_STYLE = """
  @page { size: A4; margin: 16mm 16mm; }
  body { font-family: Arial, Helvetica, sans-serif; font-size: 10.5pt; color: #111827;
         line-height: 1.4; margin: 0; }
  h1 { font-size: 20pt; margin: 0; }
  .headline { font-size: 11.5pt; color: #374151; margin: 2px 0 4px; }
  .contact { color: #4b5563; font-size: 9.5pt; }
  h2 { font-size: 11pt; text-transform: uppercase; letter-spacing: .06em; color: #1f3a8a;
       border-bottom: 1px solid #c7d2fe; padding-bottom: 2px; margin: 14px 0 6px; }
  .row { display: flex; justify-content: space-between; gap: 12px; }
  .row strong { font-size: 10.5pt; }
  .muted { color: #4b5563; }
  .entry { margin-bottom: 8px; page-break-inside: avoid; }
  ul { margin: 3px 0 0 16px; padding: 0; }
  li { margin: 1px 0; }
  p { margin: 0; }
"""


def render_html(resume: ParsedResume) -> str:
    e = escape
    parts: list[str] = [
        '<!doctype html><html><head><meta charset="utf-8">',
        f"<title>{e(resume.name or 'Resume')}</title><style>{_STYLE}</style></head><body>",
        f"<h1>{e(resume.name or '')}</h1>",
    ]
    if resume.headline:
        parts.append(f'<p class="headline">{e(resume.headline)}</p>')
    contact = [v for v in [resume.email, resume.phone, resume.location, *resume.links] if v]
    if contact:
        parts.append(f'<p class="contact">{" · ".join(e(v) for v in contact)}</p>')
    if resume.summary:
        parts.append(f"<h2>Summary</h2><p>{e(resume.summary)}</p>")
    if resume.skills:
        parts.append(f"<h2>Skills</h2><p>{e(', '.join(resume.skills))}</p>")
    if resume.experience:
        parts.append("<h2>Experience</h2>")
        for job in resume.experience:
            where = ", ".join(e(v) for v in [job.company, job.location] if v)
            parts.append(
                '<div class="entry"><div class="row">'
                f"<span><strong>{e(job.title)}</strong> — {where}</span>"
                f'<span class="muted">{e(_dates(job.start, job.end))}</span></div>'
            )
            if job.highlights:
                items = "".join(f"<li>{e(item)}</li>" for item in job.highlights)
                parts.append(f"<ul>{items}</ul>")
            parts.append("</div>")
    if resume.projects:
        parts.append("<h2>Projects</h2>")
        for project in resume.projects:
            tech = f' <span class="muted">({e(", ".join(project.technologies))})</span>'
            parts.append(
                f'<div class="entry"><p><strong>{e(project.name)}</strong>'
                f"{tech if project.technologies else ''}</p><p>{e(project.description)}</p></div>"
            )
    if resume.education:
        parts.append("<h2>Education</h2>")
        for school in resume.education:
            details = f'<p class="muted">{e(school.details)}</p>' if school.details else ""
            parts.append(
                '<div class="entry"><div class="row">'
                f"<span><strong>{e(school.degree)}</strong> — {e(school.institution)}</span>"
                f'<span class="muted">{e(_dates(school.start, school.end))}</span></div>'
                f"{details}</div>"
            )
    if resume.certifications:
        items = "".join(f"<li>{e(c)}</li>" for c in resume.certifications)
        parts.append(f"<h2>Certifications</h2><ul>{items}</ul>")
    parts.append("</body></html>")
    return "".join(parts)
