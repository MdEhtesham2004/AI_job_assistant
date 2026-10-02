"""Match score and decision (Feature doc Module 04). The AI gives component scores; the
weighted total and the decision are computed here, so they are deterministic and auditable."""

import re
from collections.abc import Iterable

from app.models.enums import AnalysisDecision

COMPONENTS = ("skills", "experience", "technology", "education", "location")
DEFAULT_WEIGHTS = {"skills": 40, "experience": 25, "technology": 20, "education": 10, "location": 5}

_NON_WORD = re.compile(r"[^0-9a-z+#]+")


def clamp(value: int | float) -> int:
    return max(0, min(100, round(value)))


def weighted_score(components: dict[str, int], weights: dict[str, int]) -> int:
    """Σ score × weight / Σ weight, rounded. Missing weights fall back to the defaults."""
    used = {key: int(weights.get(key, DEFAULT_WEIGHTS[key])) for key in COMPONENTS}
    total = sum(used.values()) or 100
    return clamp(sum(clamp(components.get(key, 0)) * used[key] for key in COMPONENTS) / total)


def decide(score: int, use_master_at: int, tailor_at: int) -> AnalysisDecision:
    if score >= use_master_at:
        return AnalysisDecision.USE_MASTER
    if score >= tailor_at:
        return AnalysisDecision.TAILOR
    return AnalysisDecision.SKIP


def _norm(value: str) -> str:
    return " ".join(_NON_WORD.sub(" ", value.lower()).split())


def grounded(items: Iterable[str], source_text: str, limit: int) -> list[str]:
    """Keep items that really appear in `source_text` (deduplicated, at most `limit`).

    Used so "matched skills" are skills the resume really has and "missing skills" are
    skills the job really asks for — the AI cannot invent either list.
    """
    known = f" {_norm(source_text)} "
    kept: list[str] = []
    seen: set[str] = set()
    for item in items:
        text = " ".join(item.split())
        key = _norm(text)
        if key and key not in seen and f" {key} " in known:
            seen.add(key)
            kept.append(text)
    return kept[:limit]
