"""
Gmail connector tools: gmail.search, gmail.read, gmail.draft, gmail.send.
Supports unified GMAIL_MODE=mock|real.
In gmail.read, returns subject, from, date, body, snippet as SEPARATE scan fields.
Extracts hidden HTML text (display:none, zero-size, comments) so security scanner observes it.
"""

from __future__ import annotations

from typing import Any
from pydantic import BaseModel, Field

from contracts.models import Provenance, ScanField, SourceType, Trust
from app.config import settings
from app.tools.base import ToolContext, ToolExecutionResult
from app.tools.gmail_backend import get_backend, load_mock_mailbox as _load_mock_mailbox  # noqa: F401
from app.tools.htmltext import extract_html, extract_html_text_with_hidden  # noqa: F401  (re-exported)
from env.mock.state import state as mock_state


def compose_body(plain: str, html: str) -> str:
    """Single text body for scanning. Hidden HTML text/comments are kept (labelled), never dropped."""
    if html and not plain:
        return extract_html(html).render()
    if html and plain:
        hidden = extract_html(html).hidden_only()
        return f"{plain}\n\n{hidden}" if hidden else plain
    return plain


# ------------------------------------------------------------------------------
# 1. gmail.search
# ------------------------------------------------------------------------------
class GmailSearchArgs(BaseModel):
    query: str = Field(..., description="Query to search messages (e.g. 'invoices', 'from:alice')")
    max_results: int = Field(default=10, description="Max messages to return")


class GmailSearchTool:
    name = "gmail.search"
    description = "Search Gmail messages by keyword, label, or sender."
    args_schema = GmailSearchArgs
    read_only = True
    risk_class = "read"
    destination_args = []

    async def run(self, args: dict[str, Any], context: ToolContext) -> ToolExecutionResult:
        validated = GmailSearchArgs.model_validate(args)
        matching = await get_backend(context.user_id).search(validated.query, validated.max_results)

        summary_lines = [
            f"ID: {m['id']} | From: {m['from']} | Subject: {m['subject']} | Date: {m['date']} | Snippet: {m['snippet']}"
            for m in matching
        ]
        text_summary = "\n".join(summary_lines) or "No messages matching query."

        scan_field = ScanField(
            name="search_results",
            text=text_summary,
            provenance=Provenance(
                source_id=f"gmail-search:{validated.query}",
                source_type=SourceType.EMAIL,
                field="search_results",
                retrieval_path=[context.call_id],
                trust=Trust.UNTRUSTED,
            ),
        )

        return ToolExecutionResult(
            call_id=context.call_id,
            tool_name=self.name,
            scan_fields=[scan_field],
            raw_output={"messages": matching, "count": len(matching)},
            text_summary=text_summary,
        )

    def observe_state(self) -> dict[str, Any]:
        return mock_state.observe_state()


# ------------------------------------------------------------------------------
# 2. gmail.read
# ------------------------------------------------------------------------------
class GmailReadArgs(BaseModel):
    message_id: str = Field(..., description="ID of the Gmail message to read")


class GmailReadTool:
    name = "gmail.read"
    description = "Read full details of a specific Gmail message."
    args_schema = GmailReadArgs
    read_only = True
    risk_class = "read"
    destination_args = []

    async def run(self, args: dict[str, Any], context: ToolContext) -> ToolExecutionResult:
        validated = GmailReadArgs.model_validate(args)
        target = await get_backend(context.user_id).read(validated.message_id)
        parsed_body = compose_body(target.get("body_plain", ""), target.get("body_html", ""))

        subject_val = target.get("subject", "")
        from_val = target.get("from", "")
        date_val = target.get("date", "")
        snippet_val = target.get("snippet", "")

        # Return separate scan fields for subject, from, date, body, snippet
        scan_fields = [
            ScanField(
                name="subject",
                text=subject_val,
                provenance=Provenance(
                    source_id=validated.message_id,
                    source_type=SourceType.EMAIL,
                    field="subject",
                    retrieval_path=[context.call_id],
                    trust=Trust.UNTRUSTED,
                ),
            ),
            ScanField(
                name="from",
                text=from_val,
                provenance=Provenance(
                    source_id=validated.message_id,
                    source_type=SourceType.EMAIL,
                    field="from",
                    retrieval_path=[context.call_id],
                    trust=Trust.UNTRUSTED,
                ),
            ),
            ScanField(
                name="date",
                text=date_val,
                provenance=Provenance(
                    source_id=validated.message_id,
                    source_type=SourceType.EMAIL,
                    field="date",
                    retrieval_path=[context.call_id],
                    trust=Trust.UNTRUSTED,
                ),
            ),
            ScanField(
                name="body",
                text=parsed_body,
                provenance=Provenance(
                    source_id=validated.message_id,
                    source_type=SourceType.EMAIL,
                    field="body",
                    retrieval_path=[context.call_id],
                    trust=Trust.UNTRUSTED,
                ),
            ),
            ScanField(
                name="snippet",
                text=snippet_val,
                provenance=Provenance(
                    source_id=validated.message_id,
                    source_type=SourceType.EMAIL,
                    field="snippet",
                    retrieval_path=[context.call_id],
                    trust=Trust.UNTRUSTED,
                ),
            ),
        ]

        text_summary = f"Subject: {subject_val}\nFrom: {from_val}\nDate: {date_val}\n\n{parsed_body}"
        return ToolExecutionResult(
            call_id=context.call_id,
            tool_name=self.name,
            scan_fields=scan_fields,
            raw_output={**target, "body": parsed_body},
            text_summary=text_summary,
        )

    def observe_state(self) -> dict[str, Any]:
        return mock_state.observe_state()


# ------------------------------------------------------------------------------
# 3. gmail.draft
# ------------------------------------------------------------------------------
class GmailDraftArgs(BaseModel):
    to: str = Field(..., description="Recipient email address")
    subject: str = Field(..., description="Draft subject line")
    body: str = Field(..., description="Draft email body")


class GmailDraftTool:
    name = "gmail.draft"
    description = "Create a draft email in Gmail."
    args_schema = GmailDraftArgs
    read_only = False
    risk_class = "write_low"
    destination_args = ["to"]

    async def run(self, args: dict[str, Any], context: ToolContext) -> ToolExecutionResult:
        validated = GmailDraftArgs.model_validate(args)
        draft = await get_backend(context.user_id).create_draft(validated.to, validated.subject, validated.body)

        scan_field = ScanField(
            name="draft_status",
            text=f"Draft created successfully with ID {draft['id']} for {validated.to}",
            provenance=Provenance(
                source_id=draft["id"],
                source_type=SourceType.TOOL_OUTPUT,
                field="draft_status",
                retrieval_path=[context.call_id],
                trust=Trust.SYSTEM,
            ),
        )

        return ToolExecutionResult(
            call_id=context.call_id,
            tool_name=self.name,
            scan_fields=[scan_field],
            raw_output=draft,
            text_summary=f"Created draft {draft['id']}",
        )

    def observe_state(self) -> dict[str, Any]:
        return mock_state.observe_state()


# ------------------------------------------------------------------------------
# 4. gmail.send
# ------------------------------------------------------------------------------
class GmailSendArgs(BaseModel):
    to: str = Field(..., description="Recipient email address")
    subject: str = Field(..., description="Email subject line")
    body: str = Field(..., description="Email body content")
    draft_id: str | None = Field(default=None, description="Optional draft ID being sent")


class GmailSendTool:
    name = "gmail.send"
    description = "Send an email via Gmail. High risk: always requires human approval."
    args_schema = GmailSendArgs
    read_only = False
    risk_class = "write_high"
    destination_args = ["to"]

    async def run(self, args: dict[str, Any], context: ToolContext) -> ToolExecutionResult:
        validated = GmailSendArgs.model_validate(args)

        sent = await get_backend(context.user_id).send(validated.to, validated.subject, validated.body, validated.draft_id)

        scan_field = ScanField(
            name="send_status",
            text=f"Email successfully sent to {validated.to} with message ID {sent['id']}",
            provenance=Provenance(
                source_id=sent["id"],
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
            raw_output=sent,
            text_summary=f"Sent email {sent['id']} to {validated.to}",
        )

    def observe_state(self) -> dict[str, Any]:
        return mock_state.observe_state()
