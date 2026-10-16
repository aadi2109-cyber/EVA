"""
Tool Registry for EVA Agent Backend.
Maintains the complete tool catalogue specified in contracts v0.
Read-only status is strictly determined from the registry, NEVER from model output.
"""

from __future__ import annotations

from typing import Any
from app.tools.base import Tool
from app.tools.files import FilesListTool, FilesReadTool, FilesSearchTool, FilesWriteTool
from app.tools.gmail import GmailDraftTool, GmailReadTool, GmailSearchTool, GmailSendTool
from app.tools.messages import MessagesHistoryTool, MessagesSendTool
from app.tools.telegram import TelegramHistoryTool, TelegramReadTool, TelegramSendTool
from app.tools.web import WebFetchTool, WebSearchTool


class ToolRegistry:
    def __init__(self) -> None:
        self._tools: dict[str, Tool] = {}
        self._register_default_tools()

    def _register_default_tools(self) -> None:
        defaults: list[Tool] = [
            GmailSearchTool(),
            GmailReadTool(),
            GmailDraftTool(),
            GmailSendTool(),
            FilesListTool(),
            FilesReadTool(),
            FilesSearchTool(),
            FilesWriteTool(),
            WebSearchTool(),
            WebFetchTool(),
            MessagesHistoryTool(),
            MessagesSendTool(),
            TelegramReadTool(),
            TelegramHistoryTool(),
            TelegramSendTool(),
        ]
        for tool in defaults:
            self.register(tool)

    def register(self, tool: Tool) -> None:
        self._tools[tool.name] = tool

    def get(self, name: str) -> Tool | None:
        return self._tools.get(name)

    def list_tool_names(self) -> list[str]:
        return list(self._tools.keys())

    def list_tools(self) -> list[Tool]:
        return list(self._tools.values())

    def is_read_only(self, tool_name: str) -> bool:
        tool = self.get(tool_name)
        if not tool:
            return True  # Unknown tool fails closed
        return tool.read_only

    def get_destination_args(self, tool_name: str) -> list[str]:
        tool = self.get(tool_name)
        return tool.destination_args if tool else []

    def to_model_tools(self) -> list[dict[str, Any]]:
        """
        Export tool schemas formatted for Ollama / OpenAI tool-calling specifications.
        """
        tools_spec = []
        for name, tool in self._tools.items():
            schema = tool.args_schema.model_json_schema()
            tools_spec.append({
                "type": "function",
                "function": {
                    "name": name,
                    "description": tool.description,
                    "parameters": schema,
                },
            })
        return tools_spec


# Singleton default registry
tool_registry = ToolRegistry()
