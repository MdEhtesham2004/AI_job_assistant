"""Voice services for the mock interview (Phase 15): short-lived browser tokens.

Two speech-to-speech services, same contract: the backend makes a single-use token whose
session config (model, voice, instructions, transcription of both sides) is fixed here,
so the browser cannot change the interviewer; the API key never leaves the server.

- OpenAI Realtime: the browser connects over WebRTC (``RealtimeClient``).
- Gemini Live: the browser connects over a WebSocket and streams 16 kHz PCM
  (``GeminiLiveClient``).
"""

import contextlib
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any, Protocol

import httpx

from app.core.config import Settings
from app.core.errors import ExternalServiceError


@dataclass(frozen=True)
class RealtimeToken:
    value: str
    expires_at: datetime
    session_id: str | None
    model: str
    provider: str = "openai"
    connect_url: str = ""  # where the browser connects (WebRTC SDP / WebSocket)


class VoiceClient(Protocol):
    @property
    def configured(self) -> bool: ...

    async def create_token(self, instructions: str, *, minutes: int = 6) -> RealtimeToken: ...


class RealtimeClient:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings

    @property
    def configured(self) -> bool:
        return bool(self.settings.realtime_api_key)

    def session_config(self, instructions: str) -> dict[str, Any]:
        s = self.settings
        return {
            "type": "realtime",
            "model": s.realtime_model,
            "instructions": instructions,
            "output_modalities": ["audio"],
            "max_output_tokens": 600,  # one spoken turn; keeps a runaway answer cheap
            "audio": {
                "input": {
                    "transcription": {"model": s.realtime_transcription_model, "language": "en"},
                    "noise_reduction": {"type": "near_field"},
                    # Semantic VAD waits for the end of a thought, not just a pause.
                    "turn_detection": {"type": "semantic_vad", "eagerness": "low"},
                },
                "output": {"voice": s.realtime_voice},
            },
        }

    async def create_token(self, instructions: str, *, minutes: int = 6) -> RealtimeToken:
        if not self.configured:
            raise ExternalServiceError(
                "Mock interviews need an OpenAI key (OPENAI_REALTIME_API_KEY).",
                code="REALTIME_NOT_CONFIGURED",
                details={"provider": "openai"},
            )
        body = {
            "expires_after": {
                "anchor": "created_at",
                "seconds": self.settings.realtime_token_seconds,
            },
            "session": self.session_config(instructions),
        }
        try:
            async with httpx.AsyncClient(timeout=20) as client:
                response = await client.post(
                    f"{self.settings.realtime_base_url.rstrip('/')}/realtime/client_secrets",
                    json=body,
                    headers={"Authorization": f"Bearer {self.settings.realtime_api_key}"},
                )
        except httpx.HTTPError as exc:
            raise ExternalServiceError(
                "The voice service could not be reached.", details={"provider": "openai"}
            ) from exc
        if response.status_code in (401, 403):
            raise ExternalServiceError(
                "The OpenAI key was rejected (check OPENAI_REALTIME_API_KEY and billing).",
                code="REALTIME_AUTH_FAILED",
                details={"provider": "openai", "status": response.status_code},
            )
        if response.status_code >= 400:
            message = ""
            with contextlib.suppress(ValueError):
                message = str(response.json().get("error", {}).get("message", ""))[:200]
            raise ExternalServiceError(
                f"The voice service refused the session. {message}".strip(),
                details={"provider": "openai", "status": response.status_code},
            )
        data = response.json()
        session = data.get("session") or {}
        return RealtimeToken(
            value=str(data["value"]),
            expires_at=datetime.fromtimestamp(int(data["expires_at"]), UTC),
            session_id=session.get("id"),
            model=str(session.get("model") or self.settings.realtime_model),
            provider="openai",
            connect_url=f"{self.settings.realtime_base_url.rstrip('/')}/realtime/calls",
        )


GEMINI_WS_PATH = (
    "/ws/google.ai.generativelanguage.v1beta.GenerativeService.BidiGenerateContentConstrained"
)


class GeminiLiveClient:
    """Gemini Live: a single-use ephemeral token locked to our interview session config."""

    def __init__(self, settings: Settings) -> None:
        self.settings = settings

    @property
    def configured(self) -> bool:
        return bool(self.settings.gemini_api_key)

    def session_setup(self, instructions: str) -> dict[str, Any]:
        """BidiGenerateContentSetup locked into the token (REST field names; the SDKs call
        this `liveConnectConstraints`, which the REST API rejects — found live)."""
        voice = {"prebuiltVoiceConfig": {"voiceName": self.settings.gemini_live_voice}}
        return {
            "model": f"models/{self.settings.gemini_live_model}",
            "generationConfig": {
                "responseModalities": ["AUDIO"],
                "speechConfig": {"voiceConfig": voice},
            },
            "systemInstruction": {"parts": [{"text": instructions}]},
            # Text of both sides, for captions and the transcript (no audio is kept).
            "inputAudioTranscription": {},
            "outputAudioTranscription": {},
        }

    async def create_token(self, instructions: str, *, minutes: int = 6) -> RealtimeToken:
        if not self.configured:
            raise ExternalServiceError(
                "Mock interviews need a Gemini key (GEMINI_API_KEY).",
                code="REALTIME_NOT_CONFIGURED",
                details={"provider": "gemini"},
            )
        now = datetime.now(UTC)
        model = self.settings.gemini_live_model
        start_by = now + timedelta(seconds=self.settings.realtime_token_seconds)
        body = {
            "uses": 1,  # one call per token; a reconnect asks for a new one
            "expireTime": (now + timedelta(minutes=minutes + 5)).isoformat(),
            "newSessionExpireTime": start_by.isoformat(),
            "bidiGenerateContentSetup": self.session_setup(instructions),
        }
        base = self.settings.gemini_base_url.rstrip("/")
        try:
            async with httpx.AsyncClient(timeout=20) as client:
                response = await client.post(
                    f"{base}/v1beta/auth_tokens",
                    json=body,
                    headers={"x-goog-api-key": self.settings.gemini_api_key},
                )
        except httpx.HTTPError as exc:
            raise ExternalServiceError(
                "The voice service could not be reached.", details={"provider": "gemini"}
            ) from exc
        if response.status_code in (401, 403):
            raise ExternalServiceError(
                "The Gemini key was rejected (check GEMINI_API_KEY).",
                code="REALTIME_AUTH_FAILED",
                details={"provider": "gemini", "status": response.status_code},
            )
        if response.status_code >= 400:
            message = ""
            with contextlib.suppress(ValueError):
                message = str(response.json().get("error", {}).get("message", ""))[:200]
            raise ExternalServiceError(
                f"The voice service refused the session. {message}".strip(),
                details={"provider": "gemini", "status": response.status_code},
            )
        data = response.json()
        ws_base = base.replace("https://", "wss://").replace("http://", "ws://")
        return RealtimeToken(
            value=str(data["name"]),
            expires_at=start_by,  # the call must start before this
            session_id=None,
            model=model,
            provider="gemini",
            connect_url=f"{ws_base}{GEMINI_WS_PATH}",
        )


def voice_client(settings: Settings) -> VoiceClient:
    """The service that runs the interviewer (Settings: INTERVIEW_VOICE_PROVIDER)."""
    if settings.voice_provider == "gemini":
        return GeminiLiveClient(settings)
    return RealtimeClient(settings)
