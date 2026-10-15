"""
Tests for Approvals Engine.
"""

from contracts.models import ApprovalRequest, SubmitApprovalRequest
from eva_guard.approvals import ApprovalsEngine
from eva_guard.gateway import compute_action_hash
from datetime import datetime, timedelta, timezone


def test_approvals_lifecycle():
    engine = ApprovalsEngine(ttl_minutes=5)
    now = datetime.now(timezone.utc)
    tool = "gmail.send"
    args = {"to": "bob@corp.com", "subject": "Quarterly Report"}
    h = compute_action_hash(tool, args)

    appr = ApprovalRequest(
        approval_id="appr-test-1",
        task_id="task-1",
        exact_action={"tool": tool, "args": args},
        arg_sources={"to": "typed by user"},
        action_hash=h,
        expires_at=now + timedelta(minutes=5),
    )
    engine.register_approval(appr, user_id="u-1")

    # Not approved yet -> verification fails
    valid, _, _ = engine.verify_approval("appr-test-1", tool, args, h)
    assert valid is False

    # Human approves
    sub_resp = engine.submit("appr-test-1", SubmitApprovalRequest(user_id="u-1", approved=True))
    assert sub_resp.status == "approved"

    # Now verified -> True
    valid, rec, mismatch = engine.verify_approval("appr-test-1", tool, args, h)
    assert valid is True
    assert mismatch is False

    # Single-use: verifying again immediately fails (consumed)
    valid_second, _, _ = engine.verify_approval("appr-test-1", tool, args, h)
    assert valid_second is False


def test_approvals_edited_args_voids_and_re_approvals():
    engine = ApprovalsEngine(ttl_minutes=5)
    now = datetime.now(timezone.utc)
    tool = "gmail.send"
    args = {"to": "bob@corp.com", "subject": "Quarterly Report"}
    h = compute_action_hash(tool, args)

    appr = ApprovalRequest(
        approval_id="appr-test-2",
        task_id="task-1",
        exact_action={"tool": tool, "args": args},
        arg_sources={"to": "typed by user"},
        action_hash=h,
        expires_at=now + timedelta(minutes=5),
    )
    engine.register_approval(appr, user_id="u-1")

    # User edits destination address
    edited_args = {"to": "charlie@corp.com", "subject": "Quarterly Report"}
    sub_resp = engine.submit(
        "appr-test-2",
        SubmitApprovalRequest(user_id="u-1", approved=True, edited_args=edited_args),
    )
    assert sub_resp.status == "re_approval_required"
    assert sub_resp.approval is not None
    assert sub_resp.approval.exact_action["args"]["to"] == "charlie@corp.com"

    # Old approval was voided/consumed
    valid, _, _ = engine.verify_approval("appr-test-2", tool, args, h)
    assert valid is False
