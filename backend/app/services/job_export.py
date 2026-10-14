"""CSV export of a user's jobs (admin change request, Phase 8).

Excel-friendly: UTF-8 with BOM (₹ and Indian scripts open correctly), CRLF line ends.
Safe: cells starting with = + - @ (or tab/CR) are prefixed with ' so a job posting cannot
inject spreadsheet formulas (CSV injection).
Match-score columns are part of the format now and filled once Phase 9 scores jobs.
"""

import csv
import io
from collections.abc import Iterable
from datetime import datetime
from typing import Any

BOM = "﻿"
_FORMULA_START = ("=", "+", "-", "@", "\t", "\r")

COLUMNS = [
    ("title", "Title"),
    ("company", "Company"),
    ("location", "Location"),
    ("remote", "Remote"),
    ("employment_type", "Employment type"),
    ("posted_at", "Posted"),
    ("state", "State"),
    ("description_quality", "Description"),
    ("apply_url", "Apply link"),
    ("found_at", "Found"),
    ("notes", "Notes"),
    ("match_score", "Match score"),
    ("matching_skills", "Matching skills"),
    ("missing_skills", "Missing skills"),
    ("scored_at", "Scored"),
]
DESCRIPTION_COLUMN = ("description", "Job description")


def safe_cell(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, bool):
        return "Yes" if value else "No"
    if isinstance(value, datetime):
        return value.strftime("%Y-%m-%d %H:%M")
    if isinstance(value, list | tuple):
        value = ", ".join(str(item) for item in value)
    text = str(value)
    return f"'{text}" if text.startswith(_FORMULA_START) else text


def to_csv(rows: Iterable[dict[str, Any]], *, include_description: bool = False) -> str:
    columns = [*COLUMNS, DESCRIPTION_COLUMN] if include_description else COLUMNS
    out = io.StringIO()
    writer = csv.writer(out, lineterminator="\r\n")
    writer.writerow([label for _, label in columns])
    for row in rows:
        writer.writerow([safe_cell(row.get(key)) for key, _ in columns])
    return BOM + out.getvalue()
