"""
Tests for Task Policy Builder.
"""

from contracts.models import BuildPolicyRequest
from eva_guard.policy import TaskPolicyBuilder, classify_intent, extract_destinations


def test_extract_destinations():
    text = "Send an email to alice@example.com and cc bob@corp.org, check https://docs.example.com/guide."
    dests = extract_destinations(text)
    assert "alice@example.com" in dests
    assert "bob@corp.org" in dests
    assert "https://docs.example.com/guide" in dests


def test_classify_intent():
    assert classify_intent("Please summarize my unread emails from today") == "mailbox_summarize"
    assert classify_intent("Draft a reply to the invoice from ACME") == "draft_reply"
    assert classify_intent("Send an email to john@example.com with the quarterly report") == "send_email_to_named_recipient"
    assert classify_intent("Search the web for python asyncio docs") == "web_research"
    assert classify_intent("Check the files in my workspace directory") == "file_work"


def test_policy_builder_send_email_least_privilege():
    builder = TaskPolicyBuilder()
    req = BuildPolicyRequest(
        task_id="t-send-1",
        user_id="user-42",
        user_role="user",
        user_request="Email the Q3 report to finance@corp.com",
        available_tools=["gmail.search", "gmail.read", "gmail.draft", "gmail.send", "files.read", "files.write"],
    )
    policy = builder.build(req)

    # Allowed destinations should include only what the user typed
    assert "finance@corp.com" in policy.allowed_destinations

    # Allowed operations
    assert "gmail.send" in policy.allowed_operations
    assert "gmail.draft" in policy.allowed_operations

    # Files.write was not in send_email template -> must be in prohibited_side_effects
    assert "files.write" in policy.prohibited_side_effects

    # Side effect allowed -> posture must be tier2_required
    assert policy.minimum_detector_posture == "tier2_required"

    # Exact approval required for send
    assert "gmail.send" in policy.approval_required_for


def test_policy_builder_read_only_summarize():
    builder = TaskPolicyBuilder()
    req = BuildPolicyRequest(
        task_id="t-sum-1",
        user_id="user-42",
        user_role="user",
        user_request="Summarize emails and pending invoices",
        available_tools=["gmail.search", "gmail.read", "gmail.send"],
    )
    policy = builder.build(req)

    assert "gmail.send" not in policy.allowed_operations
    assert "gmail.send" in policy.prohibited_side_effects
    assert policy.minimum_detector_posture == "tier1_ok_readonly"
