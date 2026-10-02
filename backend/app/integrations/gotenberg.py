"""Gotenberg client: HTML → PDF via headless Chromium (reuses the legacy /analyze approach)."""

import httpx

from app.core.config import Settings
from app.core.errors import ExternalServiceError


class GotenbergClient:
    def __init__(self, base_url: str, timeout: float = 60.0) -> None:
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout

    @classmethod
    def from_settings(cls, settings: Settings) -> "GotenbergClient":
        return cls(settings.gotenberg_url, settings.gotenberg_timeout_seconds)

    async def html_to_pdf(self, html: str) -> bytes:
        files = {"files": ("index.html", html.encode("utf-8"), "text/html")}
        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                response = await client.post(
                    f"{self.base_url}/forms/chromium/convert/html", files=files
                )
        except httpx.HTTPError as exc:
            raise ExternalServiceError(
                "The PDF service is unreachable.", details={"provider": "gotenberg"}
            ) from exc
        if response.status_code != 200 or not response.content.startswith(b"%PDF"):
            raise ExternalServiceError(
                "The PDF service could not render the document.",
                details={"provider": "gotenberg", "status": response.status_code},
            )
        return response.content

    async def check(self) -> None:
        async with httpx.AsyncClient(timeout=5.0) as client:
            response = await client.get(f"{self.base_url}/health")
        response.raise_for_status()
