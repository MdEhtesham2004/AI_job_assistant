"""Phase 14 production hardening: security headers, body-size limit, API rate limit.

All three are plain ASGI middlewares (no request buffering). Nginx sets the same limits
in front (defence in depth); these keep the API safe when it is reached directly.
"""

import json

from starlette.types import ASGIApp, Message, Receive, Scope, Send

from app.core.errors import LimitExceededError
from app.core.rate_limit import SlidingWindowRateLimiter

# Swagger UI needs its CDN assets; everything else is JSON and never framed.
_DOCS_PREFIXES = ("/docs", "/openapi.json", "/redoc")


class SecurityHeadersMiddleware:
    def __init__(self, app: ASGIApp, *, api_prefix: str, hsts: bool) -> None:
        self.app = app
        self.docs = tuple(api_prefix + p for p in _DOCS_PREFIXES)
        self.hsts = hsts

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        is_docs = str(scope.get("path", "")).startswith(self.docs)

        async def send_with_headers(message: Message) -> None:
            if message["type"] == "http.response.start":
                headers = list(message.get("headers", []))
                extra = {
                    b"x-content-type-options": b"nosniff",
                    b"x-frame-options": b"DENY",
                    b"referrer-policy": b"strict-origin-when-cross-origin",
                    b"permissions-policy": b"camera=(), microphone=(), geolocation=()",
                    b"cross-origin-opener-policy": b"same-origin",
                }
                if not is_docs:
                    extra[b"content-security-policy"] = (
                        b"default-src 'none'; frame-ancestors 'none'"
                    )
                if self.hsts:
                    extra[b"strict-transport-security"] = b"max-age=31536000; includeSubDomains"
                present = {name.lower() for name, _ in headers}
                headers += [(k, v) for k, v in extra.items() if k not in present]
                message["headers"] = headers
            await send(message)

        await self.app(scope, receive, send_with_headers)


async def _reject(
    send: Send, status: int, code: str, message: str, retry_after: int | None
) -> None:
    body = json.dumps(
        {"error": {"code": code, "message": message, "details": {}, "request_id": None}}
    ).encode()
    headers = [(b"content-type", b"application/json"), (b"content-length", str(len(body)).encode())]
    if retry_after:
        headers.append((b"retry-after", str(retry_after).encode()))
    await send({"type": "http.response.start", "status": status, "headers": headers})
    await send({"type": "http.response.body", "body": body})


class BodySizeLimitMiddleware:
    """413 for requests that declare (or stream) more than `max_bytes`."""

    def __init__(self, app: ASGIApp, *, max_bytes: int) -> None:
        self.app = app
        self.max_bytes = max_bytes

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http" or self.max_bytes <= 0:
            await self.app(scope, receive, send)
            return
        declared = dict(scope["headers"]).get(b"content-length")
        if declared and declared.isdigit() and int(declared) > self.max_bytes:
            await _reject(send, 413, "FILE_TOO_LARGE", "The request is too large.", None)
            return
        received = 0

        async def counted_receive() -> Message:
            nonlocal received
            message = await receive()
            if message["type"] == "http.request":
                received += len(message.get("body", b""))
                if received > self.max_bytes:
                    raise LimitExceededError("The request is too large.")
            return message

        await self.app(scope, counted_receive, send)


class ApiRateLimitMiddleware:
    """Per-client-IP request budget for the whole API (auth has its own stricter limits).

    In-process (per API worker); Nginx's `limit_req` does the same across workers.
    """

    def __init__(self, app: ASGIApp, *, per_minute: int, limiter: SlidingWindowRateLimiter) -> None:
        self.app = app
        self.per_minute = per_minute
        self.limiter = limiter

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http" or self.per_minute <= 0 or scope.get("method") == "OPTIONS":
            await self.app(scope, receive, send)
            return
        headers = dict(scope["headers"])
        forwarded = headers.get(b"x-real-ip") or headers.get(b"x-forwarded-for", b"").split(b",")[0]
        client = forwarded.decode().strip() or (scope.get("client") or ("unknown",))[0]
        try:
            self.limiter.check(f"api:{client}", limit=self.per_minute, window_seconds=60)
        except LimitExceededError as exc:
            await _reject(
                send,
                429,
                "RATE_LIMITED",
                "Too many requests. Please slow down.",
                int(exc.details.get("retry_after", 60)),
            )
            return
        await self.app(scope, receive, send)
