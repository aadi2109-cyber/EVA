"""
ModelProvider interface and event stream definitions for EVA Agent Backend.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, AsyncIterator, Protocol, runtime_checkable


class ModelProviderError(RuntimeError):
    """The model backend failed (HTTP error, bad/empty stream, timeout). The task fails closed;
    provider error text is never fed back to the model as if it were an answer."""


class ModelEventType(str, Enum):
    TEXT_DELTA = "text_delta"
    TOOL_CALL = "tool_call"
    DONE = "done"


@dataclass
class ModelEvent:
    type: ModelEventType
    text: str = ""
    call_id: str = ""
    tool_name: str = ""
    tool_args: dict[str, Any] = field(default_factory=dict)


@runtime_checkable
class ModelProvider(Protocol):
    """Protocol for LLM reasoning and step generation."""

    def step(
        self,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]] | None = None,
    ) -> AsyncIterator[ModelEvent]:
        """Generate the next assistant response step (text stream or tool proposal)."""
        ...
