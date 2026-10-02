"""Fakes for external services (Phase 6)."""

import json
from pathlib import Path
from typing import Any

import httpx
from fakeredis.aioredis import FakeRedis

from app.core.config import Settings
from app.core.errors import ExternalServiceError
from app.integrations.ai import AiClient
from app.integrations.storage import LocalStorage
from app.workers.runner import Services

FAKE_PDF = b"%PDF-1.7\n% fake test pdf\n%%EOF"


class FakeGotenberg:
    def __init__(self, *, fail: bool = False) -> None:
        self.fail = fail
        self.rendered: list[str] = []

    async def html_to_pdf(self, html: str) -> bytes:
        if self.fail:
            raise ExternalServiceError("The PDF service is unreachable.")
        self.rendered.append(html)
        return FAKE_PDF

    async def check(self) -> None:
        if self.fail:
            raise RuntimeError("down")


def fake_services(settings: Settings, tmp_path: Path, **overrides: Any) -> Services:
    redis = FakeRedis(decode_responses=True)
    services = Services(
        settings=settings,
        storage=LocalStorage(tmp_path / "storage"),
        gotenberg=FakeGotenberg(),  # type: ignore[arg-type]
        ai=AiClient(settings, redis),
        redis=redis,
    )
    for key, value in overrides.items():
        setattr(services, key, value)
    return services


def chat_response(
    content: Any, *, prompt_tokens: int = 12, completion_tokens: int = 8, cost: float = 0.000123
) -> httpx.Response:
    """An OpenAI-compatible chat-completions response (OpenRouter adds usage.cost)."""
    text = content if isinstance(content, str) else json.dumps(content)
    return httpx.Response(
        200,
        json={
            "id": "gen-test",
            "model": "test/model",
            "choices": [{"index": 0, "message": {"role": "assistant", "content": text}}],
            "usage": {
                "prompt_tokens": prompt_tokens,
                "completion_tokens": completion_tokens,
                "cost": cost,
            },
        },
    )
