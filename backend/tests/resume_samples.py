"""Real (tiny) PDF and DOCX resumes built in memory for tests."""

import io

RESUME_LINES = [
    "Asha Verma",
    "React Native Developer | asha@example.com | +91 98765 43210 | Pune",
    "SUMMARY",
    "Mobile developer with 4 years of experience building React Native apps.",
    "SKILLS",
    "React Native, TypeScript, Redux, Firebase, Jest",
    "EXPERIENCE",
    "Senior Mobile Developer, Acme Apps (Jan 2022 - Present)",
    "- Built a payments app used by 50000 customers",
    "- Cut crash rate by 30% with better error handling",
    "Mobile Developer, Blue Labs (Jun 2020 - Dec 2021)",
    "- Shipped 6 apps to the Play Store and App Store",
    "EDUCATION",
    "B.Tech Computer Science, Pune University (2016 - 2020)",
]


def make_pdf(lines: list[str] | None = None) -> bytes:
    """A valid one-page PDF with real, extractable text."""
    lines = lines or RESUME_LINES
    ops = ["BT", "/F1 11 Tf", "14 TL", "50 800 Td"]
    for line in lines:
        safe = line.replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")
        ops.append(f"({safe}) Tj T*")
    ops.append("ET")
    stream = "\n".join(ops).encode("latin-1")
    objects = [
        b"<< /Type /Catalog /Pages 2 0 R >>",
        b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
        b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 595 842] "
        b"/Resources << /Font << /F1 4 0 R >> >> /Contents 5 0 R >>",
        b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>",
        b"<< /Length " + str(len(stream)).encode() + b" >>\nstream\n" + stream + b"\nendstream",
    ]
    out = io.BytesIO()
    out.write(b"%PDF-1.4\n")
    offsets = []
    for number, body in enumerate(objects, start=1):
        offsets.append(out.tell())
        out.write(f"{number} 0 obj\n".encode() + body + b"\nendobj\n")
    xref = out.tell()
    out.write(f"xref\n0 {len(objects) + 1}\n0000000000 65535 f \n".encode())
    for offset in offsets:
        out.write(f"{offset:010d} 00000 n \n".encode())
    out.write(
        f"trailer\n<< /Size {len(objects) + 1} /Root 1 0 R >>\nstartxref\n{xref}\n%%EOF".encode()
    )
    return out.getvalue()


def make_docx(lines: list[str] | None = None) -> bytes:
    from docx import Document

    document = Document()
    for line in lines or RESUME_LINES:
        document.add_paragraph(line)
    out = io.BytesIO()
    document.save(out)
    return out.getvalue()


# What a good AI parse of RESUME_LINES looks like.
PARSED = {
    "name": "Asha Verma",
    "email": "asha@example.com",
    "phone": "+91 98765 43210",
    "location": "Pune",
    "links": [],
    "headline": "React Native Developer",
    "summary": "Mobile developer with 4 years of experience building React Native apps.",
    "skills": ["React Native", "TypeScript", "Redux", "Firebase", "Jest"],
    "experience": [
        {
            "title": "Senior Mobile Developer",
            "company": "Acme Apps",
            "location": None,
            "start": "Jan 2022",
            "end": "Present",
            "highlights": [
                "Built a payments app used by 50000 customers",
                "Cut crash rate by 30% with better error handling",
            ],
        },
        {
            "title": "Mobile Developer",
            "company": "Blue Labs",
            "location": None,
            "start": "Jun 2020",
            "end": "Dec 2021",
            "highlights": ["Shipped 6 apps to the Play Store and App Store"],
        },
    ],
    "education": [
        {
            "degree": "B.Tech Computer Science",
            "institution": "Pune University",
            "start": "2016",
            "end": "2020",
            "details": None,
        }
    ],
    "projects": [],
    "certifications": [],
}

ATS = {
    "ats_score": 72,
    "section_scores": {"structure": 80, "content": 70, "keywords": 65, "formatting": 75},
    "strengths": ["Clear experience section", "Quantified results"],
    "missing_skills": ["CI/CD", "GraphQL"],
    "top_roles": ["React Native Developer", "Mobile Engineer"],
    "suggestions": ["Add a projects section", "Group skills by type"],
}
