"""OllamaProvider against a mocked Ollama server: wire format, tool calls, and failure modes."""

from __future__ import annotations

import asyncio
import json

import httpx
import pytest

from app.model import ModelEventType, ModelProviderError, OllamaProvider
from app.model import ollama as ollama_mod
from app.agent.orchestrator import TaskOrchestrator
from app.guard_client.factory import set_guard_client
from app.guard_client.in_process import InProcessGuardClient

pytestmark = pytest.mark.asyncio

TOOLS = [{"type": "function", "function": {"name": "gmail.search", "description": "d", "parameters": {"type": "object"}}}]


def nd(*chunks) -> bytes:
    return ("\n".join(c if isinstance(c, str) else json.dumps(c) for c in chunks) + "\n").encode()


def chunk(content="", done=False, tool_calls=None, **extra):
    msg = {"role": "assistant", "content": content}
    if tool_calls is not None:
        msg["tool_calls"] = tool_calls
    return {"model": "m", "message": msg, "done": done, **extra}


def provider(handler, **kw) -> OllamaProvider:
    return OllamaProvider(base_url="https://ollama.test", api_key="sk-test", model="gpt-oss:20b-cloud",
                          transport=httpx.MockTransport(handler), **kw)


async def collect(p, messages=None, tools=None):
    return [e async for e in p.step(messages or [{"role": "user", "content": "hi"}], tools)]


async def test_request_format_and_text_stream():
    seen = {}

    def handler(req: httpx.Request):
        seen["url"], seen["auth"], seen["body"] = str(req.url), req.headers.get("authorization"), json.loads(req.content)
        return httpx.Response(200, content=nd(chunk("Hel"), chunk("lo"), chunk("", done=True, done_reason="stop")))

    evs = await collect(provider(handler), tools=TOOLS)
    assert seen["url"] == "https://ollama.test/api/chat"
    assert seen["auth"] == "Bearer sk-test"
    assert seen["body"]["model"] == "gpt-oss:20b-cloud" and seen["body"]["stream"] is True
    assert seen["body"]["tools"] == TOOLS
    assert [e.type for e in evs] == [ModelEventType.TEXT_DELTA, ModelEventType.TEXT_DELTA, ModelEventType.DONE]
    assert "".join(e.text for e in evs) == "Hello"


async def test_no_auth_header_without_key():
    seen = {}

    def handler(req):
        seen["auth"] = req.headers.get("authorization")
        return httpx.Response(200, content=nd(chunk("ok", done=True)))

    await collect(OllamaProvider(base_url="http://x", api_key="", model="m", transport=httpx.MockTransport(handler)))
    assert seen["auth"] is None


async def test_tool_calls_object_and_string_arguments():
    calls = [
        {"function": {"name": "gmail.search", "arguments": {"query": "invoice"}}},
        {"id": "abc", "function": {"name": "gmail.read", "arguments": '{"message_id": "msg-001"}'}},
        {"function": {"name": "files.list", "arguments": "not json"}},
        {"function": {"name": "files.read", "arguments": ["list"]}},
        {"function": {"name": "  "}},          # blank name: ignored
        {"function": "oops"}, "junk",           # malformed: ignored
    ]
    evs = await collect(provider(lambda r: httpx.Response(200, content=nd(chunk(tool_calls=calls), chunk(done=True)))))
    tcs = [e for e in evs if e.type == ModelEventType.TOOL_CALL]
    assert [(t.tool_name, t.tool_args) for t in tcs] == [
        ("gmail.search", {"query": "invoice"}), ("gmail.read", {"message_id": "msg-001"}),
        ("files.list", {}), ("files.read", {}),
    ]
    assert tcs[1].call_id == "abc" and tcs[0].call_id.startswith("call-") and tcs[0].call_id != tcs[2].call_id
    assert evs[-1].type == ModelEventType.DONE


async def test_too_many_tool_calls_rejected():
    calls = [{"function": {"name": "web.search", "arguments": {"query": str(i)}}} for i in range(20)]
    with pytest.raises(ModelProviderError, match="too many"):
        await collect(provider(lambda r: httpx.Response(200, content=nd(chunk(tool_calls=calls), chunk(done=True)))))


@pytest.mark.parametrize("status", [400, 401, 404, 429, 500, 503])
async def test_http_errors_raise_without_leaking_body_or_key(status):
    p = provider(lambda r: httpx.Response(status, text="secret-internal-detail sk-test"))
    with pytest.raises(ModelProviderError) as ei:
        await collect(p)
    assert str(status) in str(ei.value) and "secret-internal-detail" not in str(ei.value) and "sk-test" not in str(ei.value)


async def test_error_chunk_in_stream_raises():
    with pytest.raises(ModelProviderError):
        await collect(provider(lambda r: httpx.Response(200, content=nd(chunk("par"), {"error": "model overloaded"}))))


async def test_few_malformed_lines_tolerated_many_rejected():
    ok = nd(chunk("a"), "{not json", "[1,2]", chunk("b", done=True))
    evs = await collect(provider(lambda r: httpx.Response(200, content=ok)))
    assert "".join(e.text for e in evs) == "ab"
    with pytest.raises(ModelProviderError, match="malformed"):
        await collect(provider(lambda r: httpx.Response(200, content=nd(*["{bad"] * 10))))


async def test_stream_cut_without_done():
    # partial output then EOF: usable (DONE synthesised); no output at all: error
    evs = await collect(provider(lambda r: httpx.Response(200, content=nd(chunk("partial")))))
    assert evs[-1].type == ModelEventType.DONE and evs[0].text == "partial"
    with pytest.raises(ModelProviderError, match="no output"):
        await collect(provider(lambda r: httpx.Response(200, content=b"")))


async def test_connection_errors_and_timeouts():
    def boom(req):
        raise httpx.ConnectError("refused")

    with pytest.raises(ModelProviderError, match="ConnectError"):
        await collect(provider(boom))

    def slow_read(req):
        raise httpx.ReadTimeout("slow")

    with pytest.raises(ModelProviderError, match="ReadTimeout"):
        await collect(provider(slow_read))


async def test_total_deadline(monkeypatch):
    monkeypatch.setattr(ollama_mod, "TOTAL_DEADLINE_S", 0.2)

    class Hang(httpx.AsyncBaseTransport):
        async def handle_async_request(self, request):
            await asyncio.sleep(5)

    p = OllamaProvider(base_url="http://x", api_key="k", model="m", transport=Hang())
    with pytest.raises(ModelProviderError, match="timed out"):
        await collect(p)


async def test_orchestrator_fails_task_when_model_down(stub_guard_client):
    """A provider failure ends the task as failed; the error is not presented as the model's answer."""
    orch = TaskOrchestrator(
        task_id="t-model-down", user_id="u-md", user_role="user", user_request="List my files",
        model_provider=provider(lambda r: httpx.Response(503, text="down")), guard_client=stub_guard_client,
    )
    res = await orch.run()
    assert res["status"] == "failed" and "Model unavailable" in res["final_text"]
