"""Storage, Gotenberg and AI client — external services mocked."""

import asyncio
import json
from pathlib import Path

import httpx
import pytest
import respx
from fakeredis.aioredis import FakeRedis
from pydantic import BaseModel

from app.core.config import Settings
from app.core.errors import ExternalServiceError
from app.integrations.ai import AiClient, strict_schema
from app.integrations.gotenberg import GotenbergClient
from app.integrations.storage import LocalStorage, make_key
from tests.fakes import FAKE_PDF, chat_response

# ---------- storage ----------


async def test_local_storage_round_trip(tmp_path: Path) -> None:
    storage = LocalStorage(tmp_path)
    key = make_key("users/abc/tasks", "My Résumé.pdf")

    stored = await storage.save(key, b"hello", "application/pdf")

    assert stored.size == 5
    assert key.endswith("-My_R_sum_.pdf")
    assert await storage.read(key) == b"hello"
    await storage.delete(key)
    with pytest.raises(Exception, match="not found"):
        await storage.read(key)


@pytest.mark.parametrize("key", ["../outside.txt", "a/../../b", "/abs/path", "a\\b"])
async def test_local_storage_rejects_unsafe_keys(tmp_path: Path, key: str) -> None:
    with pytest.raises(ValueError):
        await LocalStorage(tmp_path).save(key, b"x", "text/plain")


async def test_local_storage_health_check(tmp_path: Path) -> None:
    await LocalStorage(tmp_path).check()


# ---------- gotenberg ----------


@respx.mock
async def test_gotenberg_converts_html_to_pdf() -> None:
    route = respx.post("http://gotenberg.test/forms/chromium/convert/html").mock(
        return_value=httpx.Response(200, content=FAKE_PDF)
    )

    pdf = await GotenbergClient("http://gotenberg.test").html_to_pdf("<h1>Hi</h1>")

    assert pdf == FAKE_PDF
    assert b'filename="index.html"' in route.calls.last.request.content


@respx.mock
@pytest.mark.parametrize(
    "response",
    [httpx.Response(500, content=b"boom"), httpx.Response(200, content=b"<html>not a pdf")],
)
async def test_gotenberg_errors_become_external_service_errors(response: httpx.Response) -> None:
    respx.post("http://gotenberg.test/forms/chromium/convert/html").mock(return_value=response)

    with pytest.raises(ExternalServiceError) as exc:
        await GotenbergClient("http://gotenberg.test").html_to_pdf("<p>x</p>")

    assert exc.value.details["provider"] == "gotenberg"


@respx.mock
async def test_gotenberg_unreachable() -> None:
    respx.post("http://gotenberg.test/forms/chromium/convert/html").mock(
        side_effect=httpx.ConnectError("refused")
    )

    with pytest.raises(ExternalServiceError, match="unreachable"):
        await GotenbergClient("http://gotenberg.test").html_to_pdf("<p>x</p>")


# ---------- AI client ----------


class Answer(BaseModel):
    ok: bool
    message: str


MESSAGES = [{"role": "user", "content": "ping"}]
COMPLETIONS = "https://ai.test/v1/chat/completions"


def test_strict_schema_requires_every_field_and_no_extras() -> None:
    schema = strict_schema(Answer)

    assert schema["additionalProperties"] is False
    assert set(schema["required"]) == {"ok", "message"}


@respx.mock
async def test_ai_client_returns_validated_output_with_usage(settings: Settings) -> None:
    route = respx.post(COMPLETIONS).mock(
        return_value=chat_response({"ok": True, "message": "hi"}, cost=0.0005)
    )

    result = await AiClient(settings).complete_json(messages=MESSAGES, output=Answer)

    assert result.data == Answer(ok=True, message="hi")
    assert (result.input_tokens, result.output_tokens) == (12, 8)
    assert str(result.cost_usd) == "0.0005"
    assert result.cached is False
    sent = json.loads(route.calls.last.request.content)
    assert sent["model"] == "test/model"
    assert sent["response_format"]["type"] == "json_schema"
    assert sent["max_tokens"] == settings.ai_max_output_tokens
    assert sent["reasoning"] == {"effort": "low"}
    assert sent["provider"] == {"sort": "throughput"}
    assert route.calls.last.request.headers["Authorization"] == "Bearer test-ai-key"


@respx.mock
async def test_ai_client_retries_once_on_invalid_json(settings: Settings) -> None:
    route = respx.post(COMPLETIONS).mock(
        side_effect=[
            chat_response("not json at all"),
            chat_response('```json\n{"ok": true, "message": "fixed"}\n```'),
        ]
    )

    result = await AiClient(settings).complete_json(messages=MESSAGES, output=Answer)

    assert result.data.message == "fixed"
    assert route.call_count == 2
    assert (result.input_tokens, result.output_tokens) == (24, 16)  # both attempts counted


@respx.mock
async def test_ai_client_gives_up_after_second_invalid_answer(settings: Settings) -> None:
    respx.post(COMPLETIONS).mock(side_effect=[chat_response("nope"), chat_response("{}")])

    with pytest.raises(ExternalServiceError) as exc:
        await AiClient(settings).complete_json(messages=MESSAGES, output=Answer)

    assert exc.value.code == "AI_INVALID_OUTPUT"


@respx.mock
async def test_ai_client_caches_identical_requests(settings: Settings) -> None:
    route = respx.post(COMPLETIONS).mock(return_value=chat_response({"ok": True, "message": "a"}))
    client = AiClient(settings, FakeRedis(decode_responses=True))

    first = await client.complete_json(messages=MESSAGES, output=Answer)
    second = await client.complete_json(messages=MESSAGES, output=Answer)

    assert route.call_count == 1
    assert first.cached is False and second.cached is True
    assert second.data == first.data
    assert second.cost_usd == 0


@respx.mock
async def test_ai_client_provider_error(settings: Settings) -> None:
    respx.post(COMPLETIONS).mock(return_value=httpx.Response(401, json={"error": "bad key"}))

    with pytest.raises(ExternalServiceError) as exc:
        await AiClient(settings).complete_json(messages=MESSAGES, output=Answer)

    assert exc.value.details["status"] == 401


@respx.mock
async def test_ai_client_gives_up_on_a_response_that_never_ends(settings: Settings) -> None:
    async def slow(request: httpx.Request) -> httpx.Response:
        await asyncio.sleep(5)  # e.g. a model stuck emitting whitespace
        return chat_response({"ok": True, "message": "late"})

    respx.post(COMPLETIONS).mock(side_effect=slow)
    quick = settings.model_copy(update={"ai_timeout_seconds": 0.2})

    with pytest.raises(ExternalServiceError, match="did not answer within"):
        await AiClient(quick).complete_json(messages=MESSAGES, output=Answer)


async def test_ai_client_without_key_is_not_configured(settings: Settings) -> None:
    no_key = settings.model_copy(update={"ai_api_key": ""})

    with pytest.raises(ExternalServiceError) as exc:
        await AiClient(no_key).complete_json(messages=MESSAGES, output=Answer)

    assert exc.value.code == "AI_NOT_CONFIGURED"
