"""
Tests for the Guard facade class.
"""

from contracts.models import (
    BuildPolicyRequest,
    CheckActionRequest,
    Provenance,
    ScanField,
    ScanRequest,
    SourceType,
    Trust,
)
from eva_guard.api import Guard


def test_guard_facade_instantiation():
    guard = Guard()
    health = guard.health()
    assert health.status in ("ok", "degraded")
    assert health.contract_version == "0.1.0"


def test_guard_facade_build_policy():
    guard = Guard()
    req = BuildPolicyRequest(
        task_id="t-1",
        user_id="u-1",
        user_role="user",
        user_request="Read my emails",
        available_tools=["gmail.search", "gmail.read"],
    )
    policy = guard.build_task_policy(req)
    assert policy.task_id == "t-1"
    assert "gmail.read" in policy.allowed_operations


def test_guard_facade_scan():
    guard = Guard()
    prov = Provenance(source_id="msg-1", source_type=SourceType.EMAIL, trust=Trust.UNTRUSTED)
    req = ScanRequest(
        task_id="t-1",
        call_id="c-1",
        tool="gmail.read",
        fields=[ScanField(name="body", text="Hello clean text", provenance=prov)],
    )
    resp = guard.scan_tool_result(req)
    assert resp.disposition == "pass"


def test_guard_facade_check_action():
    guard = Guard()
    req = CheckActionRequest(
        task_id="t-1",
        call_id="c-1",
        tool="gmail.search",
        args={"query": "test"},
        read_only=True,
    )
    resp = guard.check_action(req)
    assert resp.decision == "ALLOW"
