"""web.search provider interface: mock in eval, Ollama web-search API behind a mocked server."""

from __future__ import annotations

import json

import httpx
import pytest
from pydantic import ValidationError

from app.config import Settings, settings
from app.tools.base import ToolContext
from app.tools.web import WebSearchTool
from app.tools.web_search import (
    MAX_QUERY_CHARS, MAX_RESULTS, MAX_SNIPPET_CHARS, MockSearchProvider, OllamaSearchProvider,
    SearchError, clean_query, get_search_provider, set_search_provider,
)

pytestmark = pytest.mark.asyncio
CTX = ToolContext(task_id="t", user_id="u", call_id="c")


@pytest.fixture(autouse=True)
def _reset():
    yield
    set_search_provider(None)


def server(handler) -> OllamaSearchProvider:
    return OllamaSearchProvider(base_url="https://ollama.test", api_key="sk-test", transport=httpx.MockTransport(handler))


async def test_default_provider_is_mock_and_tool_returns_untrusted_results():
    assert isinstance(get_search_provider(), MockSearchProvider)
    res = await WebSearchTool().run({"query": "agent safety"}, CTX)
    f = res.scan_fields[0]
    assert "agent safety" in f.text and f.provenance.trust.value == "untrusted"
    assert res.raw_output["results"][0]["url"].startswith("https://example.com/")


async def test_eval_always_uses_mock_even_if_configured(monkeypatch):
    monkeypatch.setattr(settings, "WEB_SEARCH_PROVIDER", "ollama")
    monkeypatch.setattr(settings, "APP_ENV", "eval")
    assert isinstance(get_search_provider(), MockSearchProvider)
    monkeypatch.setattr(settings, "APP_ENV", "dev")
    assert isinstance(get_search_provider(), OllamaSearchProvider)


async def test_config_refuses_real_search_in_eval():
    with pytest.raises(ValidationError):
        Settings(APP_ENV="eval", WEB_SEARCH_PROVIDER="ollama", _env_file=None)
    Settings(APP_ENV="dev", WEB_SEARCH_PROVIDER="ollama", _env_file=None)


async def test_ollama_request_and_response_mapping():
    seen = {}

    def handler(req: httpx.Request):
        seen.update(url=str(req.url), auth=req.headers["authorization"], body=json.loads(req.content))
        return httpx.Response(200, json={"results": [
            {"title": "T1", "url": "https://a.test/1", "content": "snippet one"},
            {"title": "T2", "url": "http://b.test/2", "content": "x" * 5000},
        ]})

    out = await server(handler).search("quantum computing", 5)
    assert seen == {"url": "https://ollama.test/api/web_search", "auth": "Bearer sk-test",
                    "body": {"query": "quantum computing", "max_results": 5}}
    assert [r.url for r in out] == ["https://a.test/1", "http://b.test/2"]
    assert len(out[1].snippet) == MAX_SNIPPET_CHARS


async def test_results_are_sanitised_and_capped():
    raw = [{"title": "ok\x00\x1b[31m", "url": "javascript:alert(1)", "content": "bad scheme dropped"},
           {"title": "file", "url": "file:///etc/passwd", "content": "dropped"},
           "junk", {"title": "no url"}] + [{"title": f"r{i}", "url": f"https://x.test/{i}", "content": "c"} for i in range(20)]
    out = await server(lambda r: httpx.Response(200, json={"results": raw})).search("q", 99)
    assert len(out) == MAX_RESULTS and all(r.url.startswith("https://x.test/") for r in out)


@pytest.mark.parametrize("resp", [
    httpx.Response(401, text="bad key sk-test"), httpx.Response(429), httpx.Response(500),
    httpx.Response(200, text="not json"), httpx.Response(200, json={"results": "nope"}), httpx.Response(200, json=[1]),
])
async def test_backend_failures_raise_searcherror_without_leaking(resp):
    with pytest.raises(SearchError) as ei:
        await server(lambda r: resp).search("q")
    assert "sk-test" not in str(ei.value)


async def test_network_error_and_missing_key():
    def boom(req):
        raise httpx.ConnectTimeout("t")

    with pytest.raises(SearchError, match="ConnectTimeout"):
        await server(boom).search("q")
    with pytest.raises(SearchError, match="not configured"):
        await OllamaSearchProvider(base_url="https://x", api_key="").search("q")


async def test_tool_surfaces_search_errors_as_tool_errors():
    set_search_provider(server(lambda r: httpx.Response(503)))
    with pytest.raises(RuntimeError, match="503"):
        await WebSearchTool().run({"query": "q"}, CTX)


async def test_query_cleaning():
    assert clean_query("  hello\x00 world\n ") == "hello  world"
    assert len(clean_query("a" * 1000)) == MAX_QUERY_CHARS
    with pytest.raises(SearchError):
        clean_query(" \x00 ")
    set_search_provider(server(lambda r: httpx.Response(200, json={"results": []})))
    res = await WebSearchTool().run({"query": "nothing"}, CTX)
    assert res.scan_fields[0].text == "(no results)"
