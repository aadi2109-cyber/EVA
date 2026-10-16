"""
Gmail connector tools: gmail.search, gmail.read, gmail.draft, gmail.send.
Supports unified GMAIL_MODE=mock|real.
In gmail.read, returns subject, from, date, body, snippet as SEPARATE scan fields.
Extracts hidden HTML text (display:none, zero-size, comments) so security scanner observes it.
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any
from pydantic import BaseModel, Field

from contracts.models import Provenance, ScanField, SourceType, Trust
from app.config import settings
from app.tools.base import ToolContext, ToolExecutionResult
from env.mock.state import state as mock_state


def extract_html_text_with_hidden(html_content: str) -> str:
    """
    Extract visible and hidden text from HTML.
    Ensures hidden elements (display:none, visibility:hidden, font-size:0, comments)
    are captured into the text string so the security scanner sees them.
    """
    if not html_content:
        return ""

    # Extract HTML comments as text
    comments = re.findall(r"<!--(.*?)-->", html_content, re.DOTALL)
    comment_text = "\n".join([c.strip() for c in comments if c.strip()])

    # Find hidden elements
    hidden_blocks = re.findall(
        r"""<[^>]+style\s*=\s*['"][^'"]*(?:display\s*:\s*none|visibility\s*:\s*hidden|font-size\s*:\s*0)[^'"]*['"][^>]*>(.*?)</[^>]+>""",
        html_content,
        re.DOTALL | re.IGNORECASE,
    )
    hidden_text = "\n".join([re.sub(r"<[^>]+>", " ", h).strip() for h in hidden_blocks if h.strip()])

    # Strip tags for general text
    clean_text = re.sub(r"<[^>]+>", " ", html_content)
    clean_text = re.sub(r"\s+", " ", clean_text).strip()

    combined_parts = [clean_text]
    if comment_text:
        combined_parts.append(f"[HTML_COMMENT: {comment_text}]")
    if hidden_text:
        combined_parts.append(f"[HIDDEN_TEXT: {hidden_text}]")

    return "\n\n".join(combined_parts)


def _load_mock_mailbox() -> list[dict[str, Any]]:
    candidates = [
        Path("env/mock/mailbox.json"),
        Path(__file__).resolve().parents[4] / "env" / "mock" / "mailbox.json",
        Path(__file__).resolve().parents[3] / "env" / "mock" / "mailbox.json",
    ]
    for p in candidates:
        if p.exists():
            try:
                return json.loads(p.read_text(encoding="utf-8"))
            except Exception:
                return []
    return []


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
        q = validated.query.lower()

        if settings.GMAIL_MODE == "real":
            # For real Gmail mode, if credentials exist, invoke Gmail API; else mock fallback
            # (Mock fallback is default until human supplies OAuth creds)
            pass

        messages = _load_mock_mailbox()
        matching = []
        for m in messages:
            target_str = f"{m.get('subject', '')} {m.get('from', '')} {m.get('snippet', '')} {m.get('body', '')}".lower()
            if q in target_str or q in [lbl.lower() for lbl in m.get("labels", [])]:
                matching.append({
                    "id": m["id"],
                    "from": m.get("from", ""),
                    "subject": m.get("subject", ""),
                    "date": m.get("date", ""),
                    "snippet": m.get("snippet", ""),
                })
                if len(matching) >= validated.max_results:
                    break

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
        messages = _load_mock_mailbox()
        target = next((m for m in messages if m["id"] == validated.message_id), None)

        if not target:
            raise ValueError(f"Gmail message with ID '{validated.message_id}' not found")

        raw_body = target.get("body", "")
        # Process any HTML in body
        parsed_body = extract_html_text_with_hidden(raw_body) if "<" in raw_body and ">" in raw_body else raw_body

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
            raw_output=target,
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
        draft = mock_state.record_draft(to=validated.to, subject=validated.subject, body=validated.body)

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

        # In real mode with allowlist configured, check recipient
        if settings.GMAIL_MODE == "real" and settings.GMAIL_SEND_ALLOWLIST:
            allowed = [e.strip().lower() for e in settings.GMAIL_SEND_ALLOWLIST.split(",") if e.strip()]
            if validated.to.lower() not in allowed:
                raise ValueError(f"Recipient '{validated.to}' not permitted by GMAIL_SEND_ALLOWLIST")

        # Record in mock state (and mock sent box)
        sent = mock_state.record_sent_mail(
            to=validated.to,
            subject=validated.subject,
            body=validated.body,
            draft_id=validated.draft_id,
        )

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
