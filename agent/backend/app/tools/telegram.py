"""
Telegram connector tools: telegram.history, telegram.read, and telegram.send.
Reads incoming Telegram messages with UNTRUSTED provenance and scans them.
Sends telegram messages through deterministic gateway approval.
"""

from __future__ import annotations

from typing import Any
from pydantic import BaseModel, Field

from contracts.models import Provenance, ScanField, SourceType, Trust
from app.connectors.telegram import telegram_connector
from app.tools.base import ToolContext, ToolExecutionResult
from env.mock.state import state as mock_state


# ------------------------------------------------------------------------------
# 1. telegram.read / telegram.history
# ------------------------------------------------------------------------------
class TelegramReadArgs(BaseModel):
    chat_id: str = Field(..., description="Target Telegram chat ID to read messages from")
    limit: int = Field(default=20, ge=1, le=100, description="Max messages to fetch")


class TelegramReadTool:
    name = "telegram.read"
    description = "Read messages from a Telegram chat. Output is untrusted and scanned."
    args_schema = TelegramReadArgs
    read_only = True
    risk_class = "read"
    destination_args = ["chat_id"]

    async def run(self, args: dict[str, Any], context: ToolContext) -> ToolExecutionResult:
        validated = TelegramReadArgs.model_validate(args)
        msgs = await telegram_connector.get_history(validated.chat_id, limit=validated.limit)

        formatted_lines = []
        scan_fields = []

        if not msgs:
            text_summary = f"No messages found for chat {validated.chat_id}."
            scan_fields.append(
                ScanField(
                    name="messages",
                    text=text_summary,
                    provenance=Provenance(
                        source_id=f"telegram:{validated.chat_id}",
                        source_type=SourceType.TELEGRAM,
                        field="messages",
                        retrieval_path=[context.call_id],
                        trust=Trust.UNTRUSTED,
                    ),
                )
            )
        else:
            for idx, msg in enumerate(msgs):
                sender = msg.get("sender", "unknown")
                text = msg.get("text", "")
                formatted_lines.append(f"[{sender}]: {text}")
                scan_fields.append(
                    ScanField(
                        name=f"message_{idx}",
                        text=text,
                        provenance=Provenance(
                            source_id=f"telegram:{validated.chat_id}:{msg.get('id', idx)}",
                            source_type=SourceType.TELEGRAM,
                            field="text",
                            retrieval_path=[context.call_id],
                            trust=Trust.UNTRUSTED,
                        ),
                    )
                )
            text_summary = "\n".join(formatted_lines)

        return ToolExecutionResult(
            call_id=context.call_id,
            tool_name=self.name,
            scan_fields=scan_fields,
            raw_output={"chat_id": validated.chat_id, "count": len(msgs), "messages": msgs},
            text_summary=text_summary,
        )

    def observe_state(self) -> dict[str, Any]:
        return mock_state.observe_state()


class TelegramHistoryTool(TelegramReadTool):
    name = "telegram.history"
    description = "Retrieve conversation history from a Telegram chat. Output is untrusted and scanned."


# ------------------------------------------------------------------------------
# 2. telegram.send
# ------------------------------------------------------------------------------
class TelegramSendArgs(BaseModel):
    chat_id: str = Field(..., description="Target Telegram chat ID")
    text: str = Field(..., description="Message text to send")


class TelegramSendTool:
    name = "telegram.send"
    description = "Send a message to a Telegram chat. Always requires human approval."
    args_schema = TelegramSendArgs
    read_only = False
    risk_class = "write_high"
    destination_args = ["chat_id"]

    async def run(self, args: dict[str, Any], context: ToolContext) -> ToolExecutionResult:
        validated = TelegramSendArgs.model_validate(args)

        result = await telegram_connector.send_message(
            chat_id=validated.chat_id,
            text=validated.text,
        )

        scan_field = ScanField(
            name="send_status",
            text=f"Telegram message successfully delivered to chat '{validated.chat_id}'",
            provenance=Provenance(
                source_id=f"telegram-send:{validated.chat_id}",
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
            raw_output=result,
            text_summary=f"Sent Telegram message to {validated.chat_id}: {validated.text}",
        )

    def observe_state(self) -> dict[str, Any]:
        return mock_state.observe_state()
