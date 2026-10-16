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

    def __init__(self, ttl_minutes: int = 10, store: Any = None) -> None:
        self.ttl_minutes = ttl_minutes
        self._store = store  # optional GuardStore: write-through, lazy load; failures propagate (=> DENY)
        self._approvals: dict[str, dict[str, Any]] = {}

    def _get(self, approval_id: str) -> dict[str, Any] | None:
        rec = self._approvals.get(approval_id)
        if rec is None and self._store is not None:
            rec = self._store.get_approval(approval_id)
            if rec is not None:
                self._approvals[approval_id] = rec
        return rec

    def _persist(self, rec: dict[str, Any]) -> None:
        if self._store is not None:
            self._store.put_approval(rec)

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
        self._persist(self._approvals[approval.approval_id])

    def verify_approval(
        self, approval_id: str, tool: str, args: dict[str, Any], action_hash: str, task_id: str | None = None
    ) -> tuple[bool, ApprovalRequest | None, bool]:
        """
        Verifies if an approval is valid, approved, not expired, and hash matches.
        Returns: (is_valid, approval_record, is_mismatch)
        """
        record = self._get(approval_id)
        if not record:
            return False, None, False

        # An approval is bound to the task it was issued for.
        if task_id is not None and record["approval"].task_id != task_id:
            return False, record["approval"], True

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
        try:
            self._persist(record)
        except Exception:
            record["consumed"] = False
            raise  # cannot prove single use -> caller denies
        return True, record["approval"], False

    def submit(self, approval_id: str, req: SubmitApprovalRequest) -> SubmitApprovalResponse:
        """
        Processes human approval or edits.
        """
        event_id = f"evt-appr-{uuid.uuid4().hex[:8]}"
        record = self._get(approval_id)
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
            self._persist(record)
            self.register_approval(new_appr, user_id=req.user_id)

            return SubmitApprovalResponse(
                status="re_approval_required",
                approval=new_appr,
                event_id=event_id,
            )

        if req.approved:
            record["approved"] = True
            record["user_id"] = req.user_id
            self._persist(record)
            return SubmitApprovalResponse(
                status="approved",
                approval=record["approval"],
                event_id=event_id,
            )
        else:
            record["approved"] = False
            record["consumed"] = True
            self._persist(record)
            return SubmitApprovalResponse(
                status="denied",
                approval=None,
                event_id=event_id,
            )
