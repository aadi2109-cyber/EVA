"""
Tests for contracts models and serialization.
"""

from datetime import datetime, timezone
import pytest
from contracts.models import (
    CONTRACT_VERSION,
    Trust,
    SourceType,
    Provenance,
    ReasonCode,
    BuildPolicyRequest,
    TaskPolicy,
    ScanField,
    ScanRequest,
    SanitizedField,
    DetSummary,
    ScanResponse,
    CheckActionRequest,
    ApprovalRequest,
    CheckActionResponse,
    SubmitApprovalRequest,
    SubmitApprovalResponse,
    StateAssertion,
    VerifyStateRequest,
    VerifyStateResponse,
    Health,
    KillSwitchState,
    SSEEventType,
    SSEMessage,
    KillSwitchRequest,
    KillSwitchScope,
    ConfigProposalRequest,
    ConfigProposalResponse,
    ReviewDecisionRequest,
    AuditEvent,
    AuditVerifyResponse,
)


def test_contract_version():
    assert CONTRACT_VERSION == "0.1.0"


def test_provenance_immutability():
    prov = Provenance(
        source_id="msg-123",
        source_type=SourceType.EMAIL,
        field="body",
        retrieval_path=["gmail.search", "gmail.read"],
        trust=Trust.UNTRUSTED,
    )
    assert prov.source_id == "msg-123"
    assert prov.trust == Trust.UNTRUSTED

    with pytest.raises(Exception):
        prov.source_id = "mutated"  # type: ignore


def test_task_policy_serialization():
    now = datetime.now(timezone.utc)
    policy = TaskPolicy(
        task_id="t-1",
        user_id="u-1",
        version=1,
        created_at=now,
        expires_at=now,
        allowed_operations=["gmail.read", "gmail.search"],
        allowed_data_scope=[],
        allowed_destinations=["*@corp.com"],
        prohibited_side_effects=["gmail.send"],
        approval_required_for=["gmail.draft"],
        minimum_detector_posture="tier2_required",
        failure_mode="fail_closed",
        max_steps=10,
        origin="template",
    )
    data = policy.model_dump()
    reconstructed = TaskPolicy.model_validate(data)
    assert reconstructed.task_id == "t-1"
    assert reconstructed.allowed_operations == ["gmail.read", "gmail.search"]


def test_scan_models():
    prov = Provenance(
        source_id="mail-1",
        source_type=SourceType.EMAIL,
        trust=Trust.UNTRUSTED,
    )
    req = ScanRequest(
        task_id="t-1",
        call_id="c-1",
        tool="gmail.read",
        fields=[ScanField(name="body", text="Hello world", provenance=prov)],
    )
    assert req.tool == "gmail.read"

    resp = ScanResponse(
        disposition="pass",
        fields=[
            SanitizedField(
                name="body",
                text="Hello world",
                sentences_total=1,
                sentences_removed=0,
                quarantined=False,
            )
        ],
        det_summary=DetSummary(
            t1_signals=[],
            t2_max_score=0.1,
            t3_used=False,
            t3_verdict="benign",
            latency_ms={"total": 1.2},
        ),
        tier2_available=True,
        warnings=[],
        event_id="evt-1",
    )
    assert resp.disposition == "pass"
    assert resp.contract_version == CONTRACT_VERSION


def test_check_action_models():
    now = datetime.now(timezone.utc)
    appr = ApprovalRequest(
        approval_id="appr-1",
        task_id="t-1",
        exact_action={"tool": "gmail.send", "args": {"to": "alice@corp.com"}},
        arg_sources={"to": "typed by user"},
        action_hash="abcdef123456",
        expires_at=now,
    )
    resp = CheckActionResponse(
        decision="REQUIRE_APPROVAL",
        reasons=[ReasonCode.APPROVAL_REQUIRED],
        reason_text="Approval needed for send",
        align={"verdict": "aligned", "score": 0.9},
        approval=appr,
        event_id="evt-2",
    )
    assert resp.decision == "REQUIRE_APPROVAL"
    assert resp.approval.approval_id == "appr-1"
