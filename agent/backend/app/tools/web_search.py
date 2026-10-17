"""web.search providers behind one interface.

* MockSearchProvider  : deterministic results (APP_ENV=eval, tests, default).
* OllamaSearchProvider: Ollama web-search API  POST {OLLAMA_BASE_URL}/api/web_search
                        body {query, max_results}; Bearer OLLAMA_API_KEY;
                        response {results:[{title,url,content}]}.
                        (Documented at docs.ollama.com/capabilities/web-search; verified from the
                        published docs only, not against a live key.)

Results are untrusted data: titles/snippets are length-capped, URLs must be http(s), and the
provider can never be selected in APP_ENV=eval (mock-only rule).
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from typing import Protocol
from urllib.parse import urlparse

import httpx

from app.config import settings

logger = logging.getLogger(__name__)

MAX_RESULTS = 5
MAX_QUERY_CHARS = 256
MAX_TITLE_CHARS = 200
MAX_SNIPPET_CHARS = 500
SEARCH_TIMEOUT = httpx.Timeout(connect=5.0, read=10.0, write=5.0, pool=5.0)
_CONTROL = re.compile(r"[\x00-\x1f\x7f]")


class SearchError(RuntimeError):
    """Search backend failed; surfaced to the model as a generic tool error."""


@dataclass
class SearchResult:
    title: str
    url: str
    snippet: str


class SearchProvider(Protocol):
    async def search(self, query: str, max_results: int = MAX_RESULTS) -> list[SearchResult]: ...


def clean_query(query: str) -> str:
    q = _CONTROL.sub(" ", query).strip()
    if not q:
        raise SearchError("Empty search query")
    return q[:MAX_QUERY_CHARS]


def _clip(text: object, limit: int) -> str:
    return _CONTROL.sub(" ", text).strip()[:limit] if isinstance(text, str) else ""


class MockSearchProvider:
    async def search(self, query: str, max_results: int = MAX_RESULTS) -> list[SearchResult]:
        return [
            SearchResult(f"Result 1 for {query}", "https://example.com/docs/agent-safety",
                         "EVA Agent uses deterministic policy gateways and sanitizes untrusted input."),
            SearchResult(f"Result 2 for {query}", "https://example.com/docs/architecture",
                         "Comprehensive multi-agent architecture with in-process and HTTP guard clients."),
        ][:max_results]


class OllamaSearchProvider:
    def __init__(self, base_url: str | None = None, api_key: str | None = None,
                 transport: httpx.AsyncBaseTransport | None = None) -> None:
        self.base_url = (base_url or settings.OLLAMA_BASE_URL).rstrip("/")
        self.api_key = api_key if api_key is not None else settings.OLLAMA_API_KEY
        self._transport = transport

    async def search(self, query: str, max_results: int = MAX_RESULTS) -> list[SearchResult]:
        if not self.api_key:
            raise SearchError("Web search is not configured (missing API key)")
        n = max(1, min(max_results, MAX_RESULTS))
        try:
            async with httpx.AsyncClient(timeout=SEARCH_TIMEOUT, transport=self._transport) as client:
                resp = await client.post(
                    f"{self.base_url}/api/web_search",
                    json={"query": query, "max_results": n},
                    headers={"Authorization": f"Bearer {self.api_key}"},
                )
        except httpx.HTTPError as e:
            logger.error("web search request failed: %s", type(e).__name__)
            raise SearchError(f"Web search unavailable ({type(e).__name__})") from e
        if resp.status_code != 200:
            logger.error("web search status %d", resp.status_code)
            raise SearchError(f"Web search unavailable (status {resp.status_code})")
        try:
            raw = resp.json().get("results")
        except (ValueError, AttributeError) as e:
            raise SearchError("Web search returned an invalid response") from e
        if not isinstance(raw, list):
            raise SearchError("Web search returned an invalid response")

        out: list[SearchResult] = []
        for item in raw:
            if not isinstance(item, dict):
                continue
            url = item.get("url")
            if not isinstance(url, str) or urlparse(url).scheme not in ("http", "https"):
                continue
            out.append(SearchResult(_clip(item.get("title"), MAX_TITLE_CHARS), url[:2000],
                                    _clip(item.get("content"), MAX_SNIPPET_CHARS)))
            if len(out) >= n:
                break
        return out


_override: SearchProvider | None = None


def set_search_provider(provider: SearchProvider | None) -> None:
    global _override
    _override = provider


def get_search_provider() -> SearchProvider:
    if _override is not None:
        return _override
    # Eval is mock-only, regardless of configuration.
    if settings.APP_ENV == "eval" or settings.WEB_SEARCH_PROVIDER == "mock":
        return MockSearchProvider()
    return OllamaSearchProvider()
