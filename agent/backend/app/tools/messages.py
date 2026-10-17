"""
Messaging tools: messages.history and messages.send.
Sends to a mock channel; history reads from database.
"""

from __future__ import annotations

from typing import Any
from pydantic import BaseModel, Field
from sqlalchemy import select

from contracts.models import Provenance, ScanField, SourceType, Trust
from app.db.database import async_session_factory
from app.db.models import Message
from app.tools.base import ToolContext, ToolExecutionResult
from env.mock.state import state as mock_state


# ------------------------------------------------------------------------------
# 1. messages.history
# ------------------------------------------------------------------------------
class MessagesHistoryArgs(BaseModel):
    thread_id: str | None = Field(default=None, description="Optional conversation or thread identifier")


class MessagesHistoryTool:
    name = "messages.history"
    description = "Retrieve in-app message history for the current task."
    args_schema = MessagesHistoryArgs
    read_only = True
    risk_class = "read"
    destination_args = []

    async def run(self, args: dict[str, Any], context: ToolContext) -> ToolExecutionResult:
        validated = MessagesHistoryArgs.model_validate(args)

        async with async_session_factory() as session:
            stmt = select(Message).where(Message.task_id == context.task_id).order_by(Message.created_at.asc())
            res = await session.execute(stmt)
            msgs = res.scalars().all()

        history_lines = [f"[{m.role.upper()}]: {m.content}" for m in msgs]
        text_summary = "\n".join(history_lines) or "No message history recorded."

        scan_field = ScanField(
            name="history",
            text=text_summary,
            provenance=Provenance(
                source_id=f"messages:{context.task_id}",
                source_type=SourceType.MESSAGE,
                field="history",
                retrieval_path=[context.call_id],
                trust=Trust.UNTRUSTED,
            ),
        )

        return ToolExecutionResult(
            call_id=context.call_id,
            tool_name=self.name,
            scan_fields=[scan_field],
            raw_output={"count": len(msgs)},
            text_summary=text_summary,
        )

    def observe_state(self) -> dict[str, Any]:
        return mock_state.observe_state()


# ------------------------------------------------------------------------------
# 2. messages.send
# ------------------------------------------------------------------------------
class MessagesSendArgs(BaseModel):
    channel: str = Field(..., description="Target messaging channel or recipient ID")
    text: str = Field(..., description="Message text to send")


class MessagesSendTool:
    name = "messages.send"
    description = "Send a message to an external messaging channel (mock). Always requires human approval."
    args_schema = MessagesSendArgs
    read_only = False
    risk_class = "write_high"
    destination_args = ["channel"]

    async def run(self, args: dict[str, Any], context: ToolContext) -> ToolExecutionResult:
        validated = MessagesSendArgs.model_validate(args)

        # Record mock message transmission
        obs = mock_state.observe_state()
        sent_msgs = obs.get("mock_sent_messages", [])
        sent_msgs.append({"channel": validated.channel, "text": validated.text})
        mock_state.set_custom_state("mock_sent_messages", sent_msgs)

        scan_field = ScanField(
            name="send_status",
            text=f"Message successfully delivered to channel '{validated.channel}'",
            provenance=Provenance(
                source_id=f"msg-send:{validated.channel}",
                source_type=SourceType.TOOL_OUTPUT,
                field="send_status",
                retrieval_path=[context.call_id],
                trust=Trust.SYSTEM,
            ),
        )

        return ToolExecutionResult(
            call_id=context.call_id,
            tool_name=self.name,
            scan_fields=[scan_field],
            raw_output={"channel": validated.channel, "status": "delivered"},
            text_summary=f"Sent to {validated.channel}: {validated.text}",
        )

    def observe_state(self) -> dict[str, Any]:
        return mock_state.observe_state()
