"""
Task Policy Builder implementation.
Owner: SEC-2 (Authority-side Security)
"""

from __future__ import annotations

import logging
import os
import re
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

import yaml
from contracts.models import BuildPolicyRequest, ScopeRule, TaskPolicy

logger = logging.getLogger(__name__)

TEMPLATES_DIR = Path(__file__).parent / "templates"

EMAIL_REGEX = re.compile(r"[a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+")
URL_REGEX = re.compile(r"https?://[^\s]+")

SANDBOX_TOKEN = "workspace:*"
WRITE_INTENT_REGEX = re.compile(r"\b(write|save|create|edit|update|overwrite|append|rename|export to)\b", re.I)
WRITE_TOOLS = {"gmail.send", "gmail.draft", "files.write", "messages.send"}


def extract_destinations(text: str) -> list[str]:
    """
    Extracts explicit email addresses and URLs from the user's typed text.
    """
    emails = EMAIL_REGEX.findall(text)
    urls = URL_REGEX.findall(text)
    destinations: list[str] = []
    for email in emails:
        clean = email.strip().rstrip(".,;:!?)").lower()
        if clean and clean not in destinations:
            destinations.append(clean)
    for url in urls:
        clean = url.strip().rstrip(".,;:!?)")
        if clean and clean not in destinations:
            destinations.append(clean)
    return destinations


def classify_intent(user_request: str) -> str:
    """
    Deterministic rule-based intent classification for template selection.
    """
    req_lower = user_request.lower()
    has_target_email = bool(EMAIL_REGEX.search(user_request))

    # Send email requests: user wants to send an email, email someone, or provided a target email address
    if has_target_email and any(k in req_lower for k in ["email", "send", "mail", "forward", "to"]):
        return "send_email_to_named_recipient"

    if any(k in req_lower for k in ["send email", "email to", "send an email", "forward to", "mail to"]):
        return "send_email_to_named_recipient"


    # Draft reply
    if any(k in req_lower for k in ["draft reply", "draft a reply", "draft an email", "create a draft"]):
        return "draft_reply"

    # Summarize / read mailbox
    if any(k in req_lower for k in ["summarize", "invoices", "unread", "digest", "summary"]):
        if any(k in req_lower for k in ["email", "mail", "inbox"]):
            return "mailbox_summarize"

    # Mailbox only
    if any(k in req_lower for k in ["email", "inbox", "mail", "gmail"]):
        return "read_only_mailbox"

    # Files only
    if any(k in req_lower for k in ["file", "files", "document", "workspace", "folder", "memo", "notes", ".txt", ".md", ".csv", ".pdf"]):
        return "file_work"

    # Web search
    if any(k in req_lower for k in ["search the web", "browse", "fetch url", "lookup online", "google"]):
        return "web_research"

    # Default to mixed read-only
    return "mixed_readonly"


class TaskPolicyBuilder:
    """
    Builds and validates task policies strictly from user input.
    Guarantees least privilege, immutable boundaries, and fallback on failure.
    """

    def __init__(self, templates_dir: Path | None = None) -> None:
        self.templates_dir = templates_dir or TEMPLATES_DIR
        self._templates: dict[str, dict[str, Any]] = {}
        self._load_templates()

    # Set from admin config (lowering it needs four-eyes). Only affects policies built afterwards.
    side_effect_posture: str = "tier2_required"

    def _load_templates(self) -> None:
        if not self.templates_dir.exists():
            return
        for file in self.templates_dir.glob("*.yaml"):
            try:
                with open(file, "r", encoding="utf-8") as f:
                    data = yaml.safe_load(f)
                    tid = data.get("template_id")
                    if tid:
                        self._templates[tid] = data
            except Exception as e:
                logger.error(f"Failed to load template {file}: {e}")

    def get_template(self, template_id: str) -> dict[str, Any]:
        return self._templates.get(template_id) or self._templates.get("restrictive_fallback", {})

    def build(self, req: BuildPolicyRequest) -> TaskPolicy:
        """
        Builds a TaskPolicy based on the user's typed request.
        """
        now = datetime.now(timezone.utc)
        expires_at = now + timedelta(hours=2)

        # 1. Determine template
        template_id = req.template_id or classify_intent(req.user_request)
        template = self._templates.get(template_id)
        origin = "template"

        if not template:
            template = self._templates.get("restrictive_fallback", {})
            origin = "restrictive_fallback"

        # 2. Filter allowed operations by available_tools from BE
        available = set(req.available_tools)
        tpl_allowed = template.get("allowed_operations", [])
        # Least privilege: files.write only when the user's own words ask for a write
        if "files.write" in tpl_allowed and not WRITE_INTENT_REGEX.search(req.user_request):
            tpl_allowed = [op for op in tpl_allowed if op != "files.write"]
        allowed_ops = [op for op in tpl_allowed if not available or op in available]

        # 3. Extract destinations from the user's request
        extracted_dests = extract_destinations(req.user_request)
        tpl_dests = template.get("allowed_destinations", [])
        # Combined allowed destinations
        allowed_destinations = list(dict.fromkeys(tpl_dests + extracted_dests))
        # File tools operate inside the sandbox workspace only (gateway enforces no traversal)
        if any(op.startswith("files.") for op in allowed_ops) and SANDBOX_TOKEN not in allowed_destinations:
            allowed_destinations.append(SANDBOX_TOKEN)

        # 4. Prohibited side effects: all write tools not explicitly permitted
        prohibited_side_effects = list(template.get("prohibited_side_effects", []))
        for tool in WRITE_TOOLS:
            if tool not in allowed_ops and tool not in prohibited_side_effects:
                prohibited_side_effects.append(tool)

        # 5. Determine approval requirements
        approval_required_for = list(template.get("approval_required_for", []))
        # Ensure any write tool in allowed_ops requires approval
        for tool in allowed_ops:
            if tool in WRITE_TOOLS and tool not in approval_required_for:
                approval_required_for.append(tool)

        # 6. Posture requirement: tier2_required for any side effect
        has_side_effect = any(op in WRITE_TOOLS for op in allowed_ops)
        posture = self.side_effect_posture if has_side_effect else template.get("minimum_detector_posture", "tier1_ok_readonly")

        # 7. Construct policy
        policy = TaskPolicy(
            task_id=req.task_id,
            user_id=req.user_id,
            version=1,
            created_at=now,
            expires_at=expires_at,
            allowed_operations=allowed_ops,
            allowed_data_scope=[],
            allowed_destinations=allowed_destinations,
            prohibited_side_effects=prohibited_side_effects,
            approval_required_for=approval_required_for,
            minimum_detector_posture=posture,
            failure_mode=template.get("failure_mode", "fail_closed"),
            max_steps=template.get("max_steps", 12),
            origin=origin,
        )

        return policy
