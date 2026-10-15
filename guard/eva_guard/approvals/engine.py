"""
Approvals Engine.
Owner: SEC-2 (Authority-side Security)
"""

from __future__ import annotations

import logging
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any

from contracts.models import (
    ApprovalRequest,
    SubmitApprovalRequest,
    SubmitApprovalResponse,
)
from ..gateway import canonical_json, compute_action_hash

logger = logging.getLogger(__name__)


class ApprovalsEngine:
    """
    Manages action approvals bound to exact cryptographic action hashes.
    Ensures single-use, expiration, and argument tampering detection.
    """

    def __init__(self, ttl_minutes: int = 10) -> None:
        self.ttl_minutes = ttl_minutes
        self._approvals: dict[str, dict[str, Any]] = {}

    def register_approval(self, approval: ApprovalRequest, user_id: str | None = None) -> None:
        self._approvals[approval.approval_id] = {
            "approval": approval,
            "action_hash": approval.action_hash,
            "approved": False,
            "consumed": False,
            "user_id": user_id,
            "created_at": datetime.now(timezone.utc),
            "expires_at": approval.expires_at,
        }

    def verify_approval(
        self, approval_id: str, tool: str, args: dict[str, Any], action_hash: str
    ) -> tuple[bool, ApprovalRequest | None, bool]:
        """
        Verifies if an approval is valid, approved, not expired, and hash matches.
        Returns: (is_valid, approval_record, is_mismatch)
        """
        record = self._approvals.get(approval_id)
        if not record:
            return False, None, False

        now = datetime.now(timezone.utc)
        if record["expires_at"] < now:
            return False, record["approval"], False

        if record["consumed"]:
            return False, record["approval"], False

        if not record["approved"]:
            return False, record["approval"], False

        if record["action_hash"] != action_hash:
            return False, record["approval"], True

        # Mark consumed on successful verification (single use)
        record["consumed"] = True
        return True, record["approval"], False

    def submit(self, approval_id: str, req: SubmitApprovalRequest) -> SubmitApprovalResponse:
        """
        Processes human approval or edits.
        """
        event_id = f"evt-appr-{uuid.uuid4().hex[:8]}"
        record = self._approvals.get(approval_id)
        if not record:
            return SubmitApprovalResponse(
                status="expired",
                approval=None,
                event_id=event_id,
            )

        now = datetime.now(timezone.utc)
        if record["expires_at"] < now:
            return SubmitApprovalResponse(
                status="expired",
                approval=None,
                event_id=event_id,
            )

        # If args were edited, void previous approval and require re-approval
        if req.edited_args is not None:
            old_appr: ApprovalRequest = record["approval"]
            tool_name = old_appr.exact_action["tool"]
            new_id = f"appr-{uuid.uuid4().hex[:10]}"
            new_hash = compute_action_hash(tool_name, req.edited_args)
            new_expires = now + timedelta(minutes=self.ttl_minutes)

            new_sources = {k: "edited by user" for k in req.edited_args.keys()}

            new_appr = ApprovalRequest(
                approval_id=new_id,
                task_id=old_appr.task_id,
                exact_action={"tool": tool_name, "args": req.edited_args},
                arg_sources=new_sources,
                action_hash=new_hash,
                expires_at=new_expires,
            )
            # Register new and void old
            record["consumed"] = True
            self.register_approval(new_appr, user_id=req.user_id)

            return SubmitApprovalResponse(
                status="re_approval_required",
                approval=new_appr,
                event_id=event_id,
            )

        if req.approved:
            record["approved"] = True
            return SubmitApprovalResponse(
                status="approved",
                approval=record["approval"],
                event_id=event_id,
            )
        else:
            record["approved"] = False
            record["consumed"] = True
            return SubmitApprovalResponse(
                status="denied",
                approval=None,
                event_id=event_id,
            )
