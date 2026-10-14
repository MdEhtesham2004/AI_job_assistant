"""Permitted public page fetch for a job description (Feature doc Module 03).

Plain HTTP GET only: respects robots.txt, 10 s timeout, no login, no CAPTCHA, no headless
browser. Private/internal addresses are refused (the URL comes from a third party).
"""

import asyncio
import ipaddress
import json
import re
import socket
from html import unescape
from html.parser import HTMLParser
from typing import Any
from urllib.parse import urljoin, urlparse
from urllib.robotparser import RobotFileParser

import httpx

from app.core.config import Settings

USER_AGENT = "Mozilla/5.0 (compatible; AIJobAssistant/1.0; +personal job search tool)"
MAX_BYTES = 2 * 1024 * 1024
MAX_REDIRECTS = 5

_BLOCK_TAGS = {
    "p", "div", "br", "li", "ul", "ol", "h1", "h2", "h3", "h4", "h5", "h6",
    "section", "article", "tr", "table", "header", "footer",
}  # fmt: skip
_SKIP_TAGS = {"script", "style", "noscript", "svg", "nav", "header", "footer", "form", "iframe"}


class PageFetchError(Exception):
    """The page could not be used; `reason` is shown to the user."""

    def __init__(self, reason: str) -> None:
        super().__init__(reason)
        self.reason = reason


async def _check_public(url: str) -> None:
    parsed = urlparse(url)
    if parsed.scheme not in ("http", "https") or not parsed.hostname:
        raise PageFetchError("The apply link is not a web address.")
    try:
        infos = await asyncio.get_running_loop().getaddrinfo(parsed.hostname, None)
    except socket.gaierror as exc:
        raise PageFetchError("The job page's website could not be found.") from exc
    for info in infos:
        address = ipaddress.ip_address(info[4][0])
        if not address.is_global:
            raise PageFetchError("The job page points to a private network address.")


async def _robots_allows(client: httpx.AsyncClient, url: str) -> bool:
    parsed = urlparse(url)
    robots_url = f"{parsed.scheme}://{parsed.netloc}/robots.txt"
    try:
        response = await client.get(robots_url)
    except httpx.HTTPError:
        return False
    if response.status_code >= 500:
        return False  # server trouble: be conservative
    if response.status_code >= 400:
        return True  # no robots.txt → allowed
    parser = RobotFileParser()
    parser.parse(response.text.splitlines())
    return parser.can_fetch(USER_AGENT, url)


async def fetch_job_description(url: str, settings: Settings) -> str:
    timeout = settings.job_page_fetch_timeout_seconds
    async with httpx.AsyncClient(
        timeout=timeout, headers={"User-Agent": USER_AGENT}, follow_redirects=False
    ) as client:
        try:
            async with asyncio.timeout(timeout * 3):
                await _check_public(url)
                if not await _robots_allows(client, url):
                    raise PageFetchError(
                        "The website does not allow automatic reading (robots.txt)."
                    )
                response = await _get(client, url)
        except TimeoutError as exc:
            raise PageFetchError("The job page took too long to answer.") from exc
        except httpx.HTTPError as exc:
            raise PageFetchError("The job page could not be loaded.") from exc

    if response.status_code in (401, 403):
        raise PageFetchError("The job page needs a login or blocks automatic access.")
    if response.status_code >= 400:
        raise PageFetchError(f"The job page answered with an error ({response.status_code}).")
    if "html" not in response.headers.get("content-type", "html"):
        raise PageFetchError("The apply link is not a web page.")
    return extract_description(
        response.content[:MAX_BYTES].decode(response.encoding or "utf-8", "replace")
    )


async def _get(client: httpx.AsyncClient, url: str) -> httpx.Response:
    for _ in range(MAX_REDIRECTS + 1):
        response = await client.get(url)
        if response.is_redirect and response.headers.get("location"):
            url = urljoin(url, response.headers["location"])
            await _check_public(url)  # every hop must be public too
            continue
        return response
    raise PageFetchError("The job page redirects too often.")


# ---------- extraction ----------


def extract_description(html: str) -> str:
    """Prefer schema.org JobPosting (most job boards embed it), else the page's main text."""
    posting = _json_ld_description(html)
    if posting:
        return posting
    return html_to_text(html, main_only=True)


def _json_ld_description(html: str) -> str | None:
    for block in re.findall(
        r'<script[^>]+type=["\']application/ld\+json["\'][^>]*>(.*?)</script>',
        html,
        flags=re.IGNORECASE | re.DOTALL,
    ):
        try:
            data = json.loads(block.strip())
        except ValueError:
            continue
        for node in _walk(data):
            if node.get("@type") == "JobPosting" and isinstance(node.get("description"), str):
                return html_to_text(unescape(node["description"]))
    return None


def _walk(data: Any) -> list[dict[str, Any]]:
    if isinstance(data, list):
        return [node for item in data for node in _walk(item)]
    if isinstance(data, dict):
        return [data, *_walk(data.get("@graph", []))]
    return []


class _TextParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.parts: list[str] = []
        self.main_parts: list[str] = []
        self._skip = 0
        self._main = 0

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag in _SKIP_TAGS:
            self._skip += 1
        if tag in ("main", "article"):
            self._main += 1
        if tag in _BLOCK_TAGS:
            self._add("\n")

    def handle_endtag(self, tag: str) -> None:
        if tag in _SKIP_TAGS and self._skip:
            self._skip -= 1
        if tag in ("main", "article") and self._main:
            self._main -= 1
        if tag in _BLOCK_TAGS:
            self._add("\n")

    def handle_data(self, data: str) -> None:
        if not self._skip:
            self._add(data)

    def _add(self, text: str) -> None:
        self.parts.append(text)
        if self._main:
            self.main_parts.append(text)


def html_to_text(html: str, *, main_only: bool = False) -> str:
    parser = _TextParser()
    parser.feed(html)
    parts = parser.main_parts if main_only and "".join(parser.main_parts).strip() else parser.parts
    lines = [" ".join(line.split()) for line in "".join(parts).splitlines()]
    out: list[str] = []
    for line in lines:
        if line or (out and out[-1]):
            out.append(line)
    return "\n".join(out).strip()
