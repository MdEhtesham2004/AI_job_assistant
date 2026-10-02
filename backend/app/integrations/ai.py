"""LLM client for any OpenAI-compatible chat-completions API (OpenRouter by default).

Returns validated structured output (Pydantic), retries once when the model returns
invalid JSON, caches identical requests in Redis, and reports tokens, cost and latency.
It never touches the database — `services/ai.py` records usage and enforces budgets.
"""

import hashlib
import json
from dataclasses import dataclass
from decimal import Decimal
from time import perf_counter
from typing import Any

import httpx
from pydantic import BaseModel, ValidationError
from redis.asyncio import Redis

from app.core.config import Settings
from app.core.errors import ExternalServiceError

Message = dict[str, str]


@dataclass(frozen=True)
class AiResult[OutputT: BaseModel]:
    data: OutputT
    model: str
    input_tokens: int
    output_tokens: int
    cost_usd: Decimal
    latency_ms: int
    cached: bool


def strict_schema(model: type[BaseModel]) -> dict[str, Any]:
    """JSON schema accepted by strict structured-output mode (no extra keys, all required)."""
    schema = model.model_json_schema()

    def tighten(node: Any) -> None:
        if isinstance(node, dict):
            if node.get("type") == "object" and "properties" in node:
                node["additionalProperties"] = False
                node["required"] = list(node["properties"])
            for value in node.values():
                tighten(value)
        elif isinstance(node, list):
            for item in node:
                tighten(item)

    tighten(schema)
    return schema


class AiClient:
    def __init__(self, settings: Settings, redis: Redis | None = None) -> None:
        self.settings = settings
        self.redis = redis

    def _cache_key(self, model: str, messages: list[Message], schema: dict[str, Any]) -> str:
        raw = json.dumps({"m": model, "msg": messages, "s": schema}, sort_keys=True)
        return "ai:cache:" + hashlib.sha256(raw.encode()).hexdigest()

    async def complete_json[OutputT: BaseModel](
        self,
        *,
        messages: list[Message],
        output: type[OutputT],
        model: str | None = None,
        use_cache: bool = True,
    ) -> AiResult[OutputT]:
        if not self.settings.ai_configured:
            raise ExternalServiceError("No AI API key is configured.", code="AI_NOT_CONFIGURED")

        model = model or self.settings.ai_model_default
        schema = strict_schema(output)
        cache_key = self._cache_key(model, messages, schema)

        if use_cache and self.redis is not None:
            cached = await self.redis.get(cache_key)
            if cached:
                return AiResult(
                    output.model_validate_json(cached), model, 0, 0, Decimal(0), 0, True
                )

        started = perf_counter()
        attempt_messages = list(messages)
        input_tokens = output_tokens = 0
        cost = Decimal(0)
        for attempt in range(2):
            body = await self._post(model, attempt_messages, output.__name__, schema)
            usage = body.get("usage") or {}
            input_tokens += int(usage.get("prompt_tokens") or 0)
            output_tokens += int(usage.get("completion_tokens") or 0)
            cost += Decimal(str(usage.get("cost") or 0))
            content = _message_content(body)
            try:
                data = output.model_validate_json(_strip_fences(content))
                break
            except ValidationError as exc:
                if attempt == 1:
                    raise ExternalServiceError(
                        "The AI returned an invalid answer.",
                        code="AI_INVALID_OUTPUT",
                        details={"provider": "ai", "model": model},
                    ) from exc
                attempt_messages = [
                    *messages,
                    {"role": "assistant", "content": content},
                    {
                        "role": "user",
                        "content": "Your answer did not match the JSON schema. Errors: "
                        f"{exc.errors(include_url=False)}. Reply with corrected JSON only.",
                    },
                ]

        if use_cache and self.redis is not None:
            await self.redis.set(
                cache_key, data.model_dump_json(), ex=self.settings.ai_cache_ttl_seconds
            )
        return AiResult(
            data=data,
            model=model,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            cost_usd=cost,
            latency_ms=round((perf_counter() - started) * 1000),
            cached=False,
        )

    async def _post(
        self, model: str, messages: list[Message], name: str, schema: dict[str, Any]
    ) -> dict[str, Any]:
        payload = {
            "model": model,
            "messages": messages,
            "temperature": 0.2,
            "response_format": {
                "type": "json_schema",
                "json_schema": {"name": name, "strict": True, "schema": schema},
            },
            "usage": {"include": True},  # OpenRouter: report the real cost
        }
        headers = {
            "Authorization": f"Bearer {self.settings.ai_api_key}",
            "X-Title": self.settings.app_name,
        }
        try:
            async with httpx.AsyncClient(timeout=self.settings.ai_timeout_seconds) as client:
                response = await client.post(
                    f"{self.settings.ai_base_url.rstrip('/')}/chat/completions",
                    json=payload,
                    headers=headers,
                )
        except httpx.HTTPError as exc:
            raise ExternalServiceError(
                "The AI service is unreachable.", details={"provider": "ai"}
            ) from exc
        if response.status_code != 200:
            raise ExternalServiceError(
                "The AI service returned an error.",
                details={"provider": "ai", "status": response.status_code},
            )
        result: dict[str, Any] = response.json()
        return result


def _message_content(body: dict[str, Any]) -> str:
    try:
        return str(body["choices"][0]["message"]["content"] or "")
    except (KeyError, IndexError, TypeError) as exc:
        raise ExternalServiceError(
            "The AI service returned an unexpected response.", details={"provider": "ai"}
        ) from exc


def _strip_fences(text: str) -> str:
    text = text.strip()
    if text.startswith("```"):
        text = text.split("\n", 1)[1] if "\n" in text else ""
        text = text.rsplit("```", 1)[0]
    return text.strip()
