"""
ScriptedProvider for deterministic testing, evaluation scenarios, and hijack simulations.
"""

from __future__ import annotations

import uuid
from typing import Any, AsyncIterator
from app.model.base import ModelEvent, ModelEventType, ModelProvider


class ScriptedProvider:
    """
    Replays a sequence of pre-scripted steps (tool proposals or text streams).
    Thread-safe step counter advancing per step() invocation.
    """

    def __init__(self, steps: list[list[ModelEvent]] | None = None) -> None:
        self.steps: list[list[ModelEvent]] = steps or []
        self.current_step_index: int = 0

    def add_tool_call(self, tool_name: str, tool_args: dict[str, Any], call_id: str | None = None) -> ScriptedProvider:
        cid = call_id or f"call-{uuid.uuid4().hex[:8]}"
        events = [
            ModelEvent(type=ModelEventType.TOOL_CALL, call_id=cid, tool_name=tool_name, tool_args=tool_args),
            ModelEvent(type=ModelEventType.DONE),
        ]
        self.steps.append(events)
        return self

    def add_final_text(self, text: str) -> ScriptedProvider:
        events = [
            ModelEvent(type=ModelEventType.TEXT_DELTA, text=text),
            ModelEvent(type=ModelEventType.DONE),
        ]
        self.steps.append(events)
        return self

    async def step(
        self,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]] | None = None,
    ) -> AsyncIterator[ModelEvent]:
        if self.current_step_index < len(self.steps):
            events = self.steps[self.current_step_index]
            self.current_step_index += 1
            for event in events:
                yield event
        else:
            # Default fallback when steps exhausted
            yield ModelEvent(type=ModelEventType.TEXT_DELTA, text="Task processing completed.")
            yield ModelEvent(type=ModelEventType.DONE)

    def reset(self) -> None:
        self.current_step_index = 0
