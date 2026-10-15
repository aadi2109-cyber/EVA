"""
Base tool interfaces and context for EVA Agent Backend.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Protocol, runtime_checkable
from pydantic import BaseModel

from contracts.models import Provenance, ScanField, SourceType, Trust


@dataclass
class ToolContext:
    task_id: str
    user_id: str
    call_id: str
    env_mode: str = "dev"  # dev, eval, prod


@dataclass
class ToolExecutionResult:
    call_id: str
    tool_name: str
    scan_fields: list[ScanField]
    raw_output: dict[str, Any] = field(default_factory=dict)
    text_summary: str = ""


class Tool(Protocol):
    name: str
    description: str
    args_schema: type[BaseModel]
    read_only: bool
    risk_class: str  # read, write_low, write_high
    destination_args: list[str]

    async def run(self, args: dict[str, Any], context: ToolContext) -> ToolExecutionResult:
        ...

    def observe_state(self) -> dict[str, Any]:
        ...
