"""
Web tools: web.search and web.fetch.

web.fetch hardening:
  * http/https only, no URL credentials, explicit connect/read/total timeouts
  * response body capped at MAX_WEB_BYTES (streamed, truncated and flagged)
  * HTML converted to text; hidden text/comments extracted, never silently dropped
  * no cookies are stored or sent (cookie jar policy rejects everything)
  * redirects are followed manually (max MAX_REDIRECTS) and EVERY hop is re-validated
  * SSRF: every non-mock host is DNS-resolved on every hop; ALL returned addresses must be
    global (no loopback/private/link-local/CGNAT/metadata, incl. IPv4-mapped IPv6 and odd numeric
    forms like 2130706433). The connection is then pinned to the checked IP (Host header and
    TLS SNI/cert name preserved), so DNS rebinding between check and connect cannot redirect it
  * APP_ENV=eval: only the mock web server (env/mock/web) is reachable; any other
    host is refused before a socket is opened
"""

from __future__ import annotations

import asyncio
import http.cookiejar
import ipaddress
import socket
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, urljoin, urlparse

import httpx
from pydantic import BaseModel, Field

from contracts.models import Provenance, ScanField, SourceType, Trust
from app.config import settings
from app.tools.base import ToolContext, ToolExecutionResult
from app.tools.web_search import SearchError, clean_query, get_search_provider
from app.tools.htmltext import extract_html_text_with_hidden, looks_like_html
from env.mock.state import state as mock_state

MAX_WEB_BYTES = 512 * 1024  # 512 KB cap on the decoded body
MAX_REDIRECTS = 5
FETCH_TIMEOUT = httpx.Timeout(5.0, connect=3.0)
TOTAL_DEADLINE_S = 10.0
ALLOWED_CONTENT_TYPES = ("text/", "application/json", "application/xhtml", "application/xml")

# Hosts served by the in-process mock web server (never touch the network).
MOCK_WEB_HOSTS = {"localhost", "127.0.0.1", "mock.eva.local", "example.com", "www.example.com", "docs.example.com"}
MOCK_WEB_DIR_CANDIDATES = [
    Path(__file__).resolve().parents[4] / "env" / "mock" / "web",
    Path("env/mock/web"),
]


class UrlNotAllowed(ValueError):
    """Raised when a URL (or a redirect hop) violates the fetch policy."""


def _extract_text_from_html(html: str) -> str:
    return extract_html_text_with_hidden(html)


def _mock_web_dir() -> Path:
    return next((c for c in MOCK_WEB_DIR_CANDIDATES if c.exists()), MOCK_WEB_DIR_CANDIDATES[0])


def is_mock_host(host: str | None) -> bool:
    return (host or "").lower() in MOCK_WEB_HOSTS


def check_url_allowed(url: str) -> httpx.URL:
    """Validate one URL (initial or redirect hop). Raises UrlNotAllowed."""
    try:
        parsed = urlparse(url)
        host = (parsed.hostname or "").lower()
        port = parsed.port
    except ValueError as e:
        raise UrlNotAllowed(f"Malformed URL: {e}") from e
    if parsed.scheme not in ("http", "https"):
        raise UrlNotAllowed(f"URL scheme '{parsed.scheme}' is not allowed")
    if not host:
        raise UrlNotAllowed("URL has no host")
    if parsed.username or parsed.password:
        raise UrlNotAllowed("URLs with embedded credentials are not allowed")
    if is_mock_host(host):
        return httpx.URL(url)
    if settings.APP_ENV == "eval":
        raise UrlNotAllowed(f"Host '{host}' is not reachable in eval mode (mock web server only)")
    try:
        ip = ipaddress.ip_address(host)
        if not ip.is_global:
            raise UrlNotAllowed(f"Non-public address '{host}' is not allowed")
    except ValueError as e:
        if isinstance(e, UrlNotAllowed):
            raise
        if host.endswith((".local", ".internal", ".localhost", ".lan")):
            raise UrlNotAllowed(f"Internal hostname '{host}' is not allowed") from e
    if port not in (None, 80, 443):
        raise UrlNotAllowed(f"Port {port} is not allowed")
    return httpx.URL(url)


Resolver = Any  # async (host: str) -> list[str]
_resolver: Resolver | None = None  # tests inject fake DNS here


def set_resolver(resolver: Resolver | None) -> None:
    global _resolver
    _resolver = resolver


async def _system_resolve(host: str) -> list[str]:
    infos = await asyncio.get_running_loop().getaddrinfo(host, None, type=socket.SOCK_STREAM)
    return [info[4][0] for info in infos]


def _ip_is_public(addr: str) -> bool:
    try:
        ip = ipaddress.ip_address(addr.split("%", 1)[0])
    except ValueError:
        return False
    mapped = getattr(ip, "ipv4_mapped", None)
    if mapped is not None:  # ::ffff:127.0.0.1 and friends
        ip = mapped
    return ip.is_global and not ip.is_multicast


async def resolve_public_ips(host: str) -> list[str]:
    """Resolve `host` and require every address to be public. Raises UrlNotAllowed otherwise."""
    try:
        addrs = await (_resolver or _system_resolve)(host)
    except (OSError, UnicodeError) as e:
        raise UrlNotAllowed(f"Host '{host}' could not be resolved") from e
    if not addrs:
        raise UrlNotAllowed(f"Host '{host}' did not resolve to any address")
    bad = [a for a in addrs if not _ip_is_public(a)]
    if bad:
        raise UrlNotAllowed(f"Host '{host}' resolves to a non-public address ({bad[0]})")
    return addrs


class MockWebTransport(httpx.AsyncBaseTransport):
    """Serves env/mock/web/* for mock hosts. `/redirect?to=<url>` answers 302 (for redirect tests)."""

    async def handle_async_request(self, request: httpx.Request) -> httpx.Response:
        path = request.url.path
        if path.rstrip("/").endswith("/redirect"):
            target = parse_qs(request.url.query.decode()).get("to", [""])[0]
            return httpx.Response(302, headers={"Location": target}, request=request)
        name = Path(path).name
        web_dir = _mock_web_dir()
        candidate = (web_dir / name) if name and "." in name else web_dir / "index.html"
        if not candidate.is_file() or candidate.resolve().parent != web_dir.resolve():
            candidate = web_dir / "index.html"
        if candidate.is_file():
            body = candidate.read_bytes()
        else:
            body = f"<html><body><h1>Mock Content for {request.url}</h1><p>Sample documentation.</p></body></html>".encode()
        return httpx.Response(200, headers={"Content-Type": "text/html; charset=utf-8"}, content=body, request=request)


_real_transport: httpx.AsyncBaseTransport | None = None  # tests inject a mock Internet here


def set_web_transport(transport: httpx.AsyncBaseTransport | None) -> None:
    global _real_transport
    _real_transport = transport


class _RoutingTransport(httpx.AsyncBaseTransport):
    def __init__(self) -> None:
        self.mock = MockWebTransport()
        self.real = _real_transport or httpx.AsyncHTTPTransport()
        self.requested: list[str] = []

    async def handle_async_request(self, request: httpx.Request) -> httpx.Response:
        self.requested.append(str(request.url))
        if is_mock_host(request.url.host):
            return await self.mock.handle_async_request(request)
        # Defence in depth: the real transport is never reachable in eval.
        if settings.APP_ENV == "eval":
            raise UrlNotAllowed(f"Host '{request.url.host}' is not reachable in eval mode")
        # Resolve + validate on EVERY hop, then pin the connection to the validated IP.
        host = request.url.host
        addrs = await resolve_public_ips(host)
        pinned = httpx.Request(
            request.method,
            request.url.copy_with(host=addrs[0]),
            headers=request.headers,  # keeps the original Host header
            extensions={**request.extensions, "sni_hostname": host},  # TLS SNI + cert name
        )
        return await self.real.handle_async_request(pinned)

    async def aclose(self) -> None:
        await self.real.aclose()


@dataclass
class FetchResult:
    final_url: str
    status: int
    text: str
    truncated: bool = False
    redirects: list[str] = field(default_factory=list)


async def fetch_url(url: str) -> FetchResult:
    """Fetch with timeouts, size cap, no cookies, and per-hop re-validation."""
    async with asyncio.timeout(TOTAL_DEADLINE_S):
        return await _fetch_url(url)


async def _fetch_url(url: str) -> FetchResult:
    current = check_url_allowed(url)
    routing = _RoutingTransport()
    redirects: list[str] = []
    async with httpx.AsyncClient(
        transport=routing,
        timeout=FETCH_TIMEOUT,
        follow_redirects=False,
        headers={"User-Agent": "EVA-Agent/1.0", "Accept": "text/html,text/plain,application/json;q=0.9,*/*;q=0.1"},
    ) as client:
        # No cookies: jar rejects every cookie; also cleared after each hop.
        client.cookies.jar.set_policy(http.cookiejar.DefaultCookiePolicy(allowed_domains=[]))
        for _ in range(MAX_REDIRECTS + 1):
            mock_state.record_http_request(str(current))
            async with client.stream("GET", current) as resp:
                client.cookies.clear()
                if resp.is_redirect and "location" in resp.headers:
                    nxt = urljoin(str(current), resp.headers["location"])
                    try:
                        current = check_url_allowed(nxt)
                    except UrlNotAllowed:
                        mock_state.record_blocked_http_request(nxt)
                        raise
                    redirects.append(nxt)
                    continue
                if resp.status_code >= 400:
                    raise ValueError(f"HTTP request to {current} returned status {resp.status_code}")
                ctype = resp.headers.get("content-type", "text/plain").split(";")[0].strip().lower()
                if not ctype.startswith(ALLOWED_CONTENT_TYPES):
                    raise ValueError(f"Unsupported content type '{ctype}'")
                buf = bytearray()
                truncated = False
                async for chunk in resp.aiter_bytes():
                    buf.extend(chunk)
                    if len(buf) > MAX_WEB_BYTES:
                        del buf[MAX_WEB_BYTES:]
                        truncated = True
                        break
                charset = resp.charset_encoding or "utf-8"
                try:
                    body = bytes(buf).decode(charset, errors="replace")
                except LookupError:
                    body = bytes(buf).decode("utf-8", errors="replace")
                text = extract_html_text_with_hidden(body) if (ctype != "text/plain" and looks_like_html(body)) else body
                return FetchResult(str(current), resp.status_code, text.strip(), truncated, redirects)
    raise ValueError(f"Too many redirects (>{MAX_REDIRECTS}) fetching {url}")


# ------------------------------------------------------------------------------
# 1. web.search
# ------------------------------------------------------------------------------
class WebSearchArgs(BaseModel):
    query: str = Field(..., description="Web search query")


class WebSearchTool:
    name = "web.search"
    description = "Search the web for information."
    args_schema = WebSearchArgs
    read_only = True
    risk_class = "read"
    destination_args = []

    async def run(self, args: dict[str, Any], context: ToolContext) -> ToolExecutionResult:
        validated = WebSearchArgs.model_validate(args)

        try:
            query = clean_query(validated.query)
            results = [
                {"title": r.title, "url": r.url, "snippet": r.snippet}
                for r in await get_search_provider().search(query)
            ]
        except SearchError as e:
            raise RuntimeError(str(e)) from e

        summary_text = "\n".join([f"[{r['title']}]({r['url']}): {r['snippet']}" for r in results]) or "(no results)"
        scan_field = ScanField(
            name="search_results",
            text=summary_text,
            provenance=Provenance(
                source_id=f"web-search:{validated.query}",
                source_type=SourceType.WEB,
                field="search_results",
                retrieval_path=[context.call_id],
                trust=Trust.UNTRUSTED,
            ),
        )

        return ToolExecutionResult(
            call_id=context.call_id,
            tool_name=self.name,
            scan_fields=[scan_field],
            raw_output={"results": results},
            text_summary=summary_text,
        )

    def observe_state(self) -> dict[str, Any]:
        return mock_state.observe_state()


# ------------------------------------------------------------------------------
# 2. web.fetch
# ------------------------------------------------------------------------------
class WebFetchArgs(BaseModel):
    url: str = Field(..., description="URL of the web page to fetch")


class WebFetchTool:
    name = "web.fetch"
    description = "Fetch and extract text content from a web URL."
    args_schema = WebFetchArgs
    read_only = True
    risk_class = "read"
    destination_args = ["url"]

    async def run(self, args: dict[str, Any], context: ToolContext) -> ToolExecutionResult:
        validated = WebFetchArgs.model_validate(args)
        try:
            result = await fetch_url(validated.url)
        except UrlNotAllowed:
            mock_state.record_blocked_http_request(validated.url)
            raise
        except TimeoutError as e:
            raise RuntimeError(f"Fetching {validated.url} timed out") from e
        except httpx.HTTPError as e:
            raise RuntimeError(f"Failed to fetch URL {validated.url}: {type(e).__name__}") from e

        text = result.text + ("\n[TRUNCATED: size cap reached]" if result.truncated else "")
        scan_field = ScanField(
            name="page_content",
            text=text,
            provenance=Provenance(
                source_id=validated.url,
                source_type=SourceType.WEB,
                field="page_content",
                retrieval_path=[context.call_id],
                trust=Trust.UNTRUSTED,
            ),
        )
        return ToolExecutionResult(
            call_id=context.call_id,
            tool_name=self.name,
            scan_fields=[scan_field],
            raw_output={
                "url": validated.url,
                "final_url": result.final_url,
                "status": result.status,
                "redirects": result.redirects,
                "truncated": result.truncated,
                "content_length": len(text),
            },
            text_summary=text[:500],
        )

    def observe_state(self) -> dict[str, Any]:
        return mock_state.observe_state()
