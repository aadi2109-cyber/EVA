"""
Ollama cloud model provider implementation supporting streaming and tool calls.
"""

from __future__ import annotations

import json
import logging
import uuid
from typing import Any, AsyncIterator
import httpx

from app.config import settings
from app.model.base import ModelEvent, ModelEventType, ModelProvider

logger = logging.getLogger(__name__)


class OllamaProvider:
    """Client for Ollama Cloud (or local Ollama) chat API."""

    def __init__(
        self,
        base_url: str | None = None,
        api_key: str | None = None,
        model: str | None = None,
    ) -> None:
        self.base_url = (base_url or settings.OLLAMA_BASE_URL).rstrip("/")
        self.api_key = api_key or settings.OLLAMA_API_KEY
        self.model = model or settings.OLLAMA_MODEL

    async def step(
        self,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]] | None = None,
    ) -> AsyncIterator[ModelEvent]:
        url = f"{self.base_url}/api/chat"
        headers = {"Content-Type": "application/json"}
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"

        payload: dict[str, Any] = {
            "model": self.model,
            "messages": messages,
            "stream": True,
        }
        if tools:
            payload["tools"] = tools

        async with httpx.AsyncClient(timeout=60.0) as client:
            try:
                async with client.stream("POST", url, json=payload, headers=headers) as response:
                    if response.status_code != 200:
                        error_text = await response.aread()
                        logger.error("Ollama API error: status %d, body: %s", response.status_code, error_text)
                        yield ModelEvent(
                            type=ModelEventType.TEXT_DELTA,
                            text=f"Model provider error (status {response.status_code})",
                        )
                        yield ModelEvent(type=ModelEventType.DONE)
                        return

                    async for line in response.aiter_lines():
                        if not line or not line.strip():
                            continue
                        try:
                            chunk = json.loads(line)
                        except Exception:
                            continue

                        msg = chunk.get("message", {})
                        content = msg.get("content", "")
                        if content:
                            yield ModelEvent(type=ModelEventType.TEXT_DELTA, text=content)

                        # Check for tool_calls array
                        tool_calls = msg.get("tool_calls", [])
                        for tc in tool_calls:
                            fn = tc.get("function", {})
                            name = fn.get("name")
                            args = fn.get("arguments", {})
                            if isinstance(args, str):
                                try:
                                    args = json.loads(args)
                                except Exception:
                                    args = {}
                            cid = tc.get("id") or f"call-{uuid.uuid4().hex[:8]}"
                            yield ModelEvent(
                                type=ModelEventType.TOOL_CALL,
                                call_id=cid,
                                tool_name=name,
                                tool_args=args,
                            )

                        if chunk.get("done", False):
                            yield ModelEvent(type=ModelEventType.DONE)
                            return

            except Exception as e:
                logger.error("Failed to connect to Ollama: %s", e)
                yield ModelEvent(type=ModelEventType.TEXT_DELTA, text=f"Error connecting to model: {e}")
                yield ModelEvent(type=ModelEventType.DONE)
