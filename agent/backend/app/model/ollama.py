"""
Ollama cloud model provider: streaming chat with tool calls.

Wire format (https://github.com/ollama/ollama/blob/main/docs/api.md, POST /api/chat):
  request : {model, messages[{role, content, tool_calls?, tool_name?}], tools[{type:"function",
             function:{name, description, parameters}}], stream}
  response: NDJSON chunks {model, created_at, message:{role, content, tool_calls?:[{function:{name,
            arguments:{...}}}]}, done:false} ... final chunk {done:true, done_reason, ...}
  auth    : `Authorization: Bearer <OLLAMA_API_KEY>` against https://ollama.com (cloud).
Tool-call ids are not part of the API, so ids are generated locally.

Failure policy: any HTTP error, error chunk, timeout or empty stream raises ModelProviderError
(the orchestrator fails the task). Provider error text is never yielded as model output.
"""

from __future__ import annotations

import asyncio
import json
import logging
import uuid
from typing import Any, AsyncIterator

import httpx

from app.config import settings
from app.model.base import ModelEvent, ModelEventType, ModelProviderError

logger = logging.getLogger(__name__)

TIMEOUT = httpx.Timeout(connect=10.0, read=60.0, write=10.0, pool=10.0)
TOTAL_DEADLINE_S = 180.0
MAX_BAD_LINES = 5
MAX_TOOL_CALLS_PER_STEP = 8


def _parse_tool_call(tc: Any) -> ModelEvent | None:
    if not isinstance(tc, dict):
        return None
    fn = tc.get("function")
    if not isinstance(fn, dict):
        return None
    name = fn.get("name")
    if not isinstance(name, str) or not name.strip():
        return None
    args = fn.get("arguments", {})
    if isinstance(args, str):
        try:
            args = json.loads(args)
        except ValueError:
            args = {}
    if not isinstance(args, dict):
        args = {}
    cid = tc.get("id")
    return ModelEvent(
        type=ModelEventType.TOOL_CALL,
        call_id=cid if isinstance(cid, str) and cid else f"call-{uuid.uuid4().hex[:8]}",
        tool_name=name.strip(),
        tool_args=args,
    )


class OllamaProvider:
    """Client for Ollama Cloud (or local Ollama) chat API."""

    def __init__(
        self,
        base_url: str | None = None,
        api_key: str | None = None,
        model: str | None = None,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        self.base_url = (base_url or settings.OLLAMA_BASE_URL).rstrip("/")
        self.api_key = api_key or settings.OLLAMA_API_KEY
        self.model = model or settings.OLLAMA_MODEL
        self._transport = transport  # tests inject a mock server

    async def step(
        self,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]] | None = None,
    ) -> AsyncIterator[ModelEvent]:
        try:
            async with asyncio.timeout(TOTAL_DEADLINE_S):
                async for ev in self._step(messages, tools):
                    yield ev
        except TimeoutError as e:
            raise ModelProviderError("Model request timed out") from e

    async def _step(
        self, messages: list[dict[str, Any]], tools: list[dict[str, Any]] | None
    ) -> AsyncIterator[ModelEvent]:
        url = f"{self.base_url}/api/chat"
        headers = {"Content-Type": "application/json"}
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"

        payload: dict[str, Any] = {"model": self.model, "messages": messages, "stream": True}
        if tools:
            payload["tools"] = tools

        produced = False
        tool_calls = 0
        bad_lines = 0
        try:
            async with httpx.AsyncClient(timeout=TIMEOUT, transport=self._transport) as client:
                async with client.stream("POST", url, json=payload, headers=headers) as response:
                    if response.status_code != 200:
                        body = (await response.aread())[:300]
                        # Status and a short body only: never log request headers (API key).
                        logger.error("Ollama API error: status %d body=%r", response.status_code, body)
                        raise ModelProviderError(f"Model provider error (status {response.status_code})")

                    async for line in response.aiter_lines():
                        if not line.strip():
                            continue
                        try:
                            chunk = json.loads(line)
                        except ValueError:
                            bad_lines += 1
                            if bad_lines > MAX_BAD_LINES:
                                raise ModelProviderError("Model stream is malformed")
                            continue
                        if not isinstance(chunk, dict):
                            bad_lines += 1
                            continue
                        if chunk.get("error"):
                            logger.error("Ollama stream error chunk: %r", str(chunk["error"])[:300])
                            raise ModelProviderError("Model provider reported an error")

                        msg = chunk.get("message")
                        if isinstance(msg, dict):
                            content = msg.get("content")
                            if isinstance(content, str) and content:
                                produced = True
                                yield ModelEvent(type=ModelEventType.TEXT_DELTA, text=content)
                            raw_calls = msg.get("tool_calls")
                            for tc in raw_calls if isinstance(raw_calls, list) else []:
                                ev = _parse_tool_call(tc)
                                if ev is None:
                                    continue
                                tool_calls += 1
                                if tool_calls > MAX_TOOL_CALLS_PER_STEP:
                                    raise ModelProviderError("Model proposed too many tool calls in one step")
                                produced = True
                                yield ev

                        if chunk.get("done") is True:
                            yield ModelEvent(type=ModelEventType.DONE)
                            return
        except ModelProviderError:
            raise
        except httpx.HTTPError as e:
            logger.error("Failed to reach Ollama: %s", type(e).__name__)
            raise ModelProviderError(f"Could not reach model provider ({type(e).__name__})") from e

        # Stream ended without a done chunk: usable only if it already produced output.
        if not produced:
            raise ModelProviderError("Model stream ended with no output")
        yield ModelEvent(type=ModelEventType.DONE)
