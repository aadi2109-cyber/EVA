"""
StubGuard - Test-only canned implementation of the Guard facade.
Refuses to load when APP_ENV=prod.
Owner: SEC-2 (Authority-side Security)
"""

from __future__ import annotations

import hashlib
import json
import os
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any

from contracts.models import (
    CONTRACT_VERSION,
    AlignVerdict,
    ApprovalRequest,
    BuildPolicyRequest,
    CheckActionRequest,
    CheckActionResponse,
    DetSummary,
    Health,
    KillSwitchState,
    Provenance,
    ReasonCode,
    SanitizedField,
    ScanField,
    ScanRequest,
    ScanResponse,
    ScopeRule,
    StateAssertion,
    SubmitApprovalRequest,
    SubmitApprovalResponse,
    TaskPolicy,
    VerifyStateRequest,
    VerifyStateResponse,
)

# Canonical standard tool catalogue from doc 02 §4
STANDARD_TOOLS = {
    "gmail.search": True,
    "gmail.read": True,
    "gmail.draft": False,
    "gmail.send": False,
    "files.list": True,
    "files.read": True,
    "files.search": True,
    "files.write": False,
    "web.search": True,
    "web.fetch": True,
    "messages.history": True,
    "messages.send": False,
}

ALWAYS_APPROVAL_REQUIRED = {"gmail.send", "messages.send", "files.write", "gmail.draft"}


def _canonical_json(data: Any) -> str:
    return json.dumps(data, sort_keys=True, separators=(",", ":"), default=str)


def _compute_action_hash(tool: str, args: dict[str, Any]) -> str:
    payload = {"tool": tool, "args": args}
    return hashlib.sha256(_canonical_json(payload).encode("utf-8")).hexdigest()


class StubGuard:
    """
    Test-only canned implementation of Guard.
    Used during initial development before full modules are assembled.
    Refuses to load when APP_ENV=prod.
    """

    def __init__(self) -> None:
        env = os.getenv("APP_ENV", "dev").lower()
        if env == "prod":
            raise RuntimeError("StubGuard cannot be loaded in production environment (APP_ENV=prod)")
        self._approvals: dict[str, dict[str, Any]] = {}

    def build_task_policy(self, req: BuildPolicyRequest) -> TaskPolicy:
        """
        Returns a permissive-for-reads, safe-defaults policy.
        """
        now = datetime.now(timezone.utc)
        return TaskPolicy(
            task_id=req.task_id,
            user_id=req.user_id,
            version=1,
            created_at=now,
            expires_at=now + timedelta(hours=2),
            allowed_operations=req.available_tools or list(STANDARD_TOOLS.keys()),
            allowed_data_scope=[],
            allowed_destinations=["*@*", "https://*", "http://*"],
            prohibited_side_effects=[],
            approval_required_for=list(ALWAYS_APPROVAL_REQUIRED),
            minimum_detector_posture="tier1_ok_readonly",
            failure_mode="fail_closed",
            max_steps=12,
            origin="template",
        )

    def scan_tool_result(self, req: ScanRequest) -> ScanResponse:
        """
        Pass-through scanner with fake sanitization for text containing 'ignore the user'.
        """
        sanitized_fields: list[SanitizedField] = []
        any_removed = False

        for f in req.fields:
            text = f.text
            lower_text = text.lower()
            if "ignore the user" in lower_text or "ignore all previous instructions" in lower_text:
                # Replace the injection sentence with marker
                new_text = text.replace("Ignore the user.", "[CONTENT SANITISED]")
                new_text = new_text.replace("ignore the user.", "[CONTENT SANITISED]")
                new_text = new_text.replace("Ignore all previous instructions.", "[CONTENT SANITISED]")
                new_text = new_text.replace("ignore all previous instructions.", "[CONTENT SANITISED]")
                if "[CONTENT SANITISED]" not in new_text:
                    new_text = "[CONTENT SANITISED]"
                sanitized_fields.append(
                    SanitizedField(
                        name=f.name,
                        text=new_text,
                        sentences_total=1,
                        sentences_removed=1,
                        quarantined=False,
                    )
                )
                any_removed = True
            else:
                sanitized_fields.append(
                    SanitizedField(
                        name=f.name,
                        text=text,
                        sentences_total=1,
                        sentences_removed=0,
                        quarantined=False,
                    )
                )

        disposition = "sanitized" if any_removed else "pass"
        return ScanResponse(
            disposition=disposition,
            fields=sanitized_fields,
            det_summary=DetSummary(
                t1_signals=["stub_rule_match"] if any_removed else [],
                t2_max_score=0.99 if any_removed else 0.05,
                t3_used=False,
                t3_verdict="malicious" if any_removed else "benign",
                latency_ms={"t1": 0.5, "t2": 1.0, "total": 1.5},
            ),
            tier2_available=True,
            warnings=[],
            contract_version=CONTRACT_VERSION,
            event_id=f"stub-scan-{uuid.uuid4().hex[:8]}",
        )

    def check_action(self, req: CheckActionRequest) -> CheckActionResponse:
        """
        Deterministic stub checks:
        - Unknown tools -> DENY
        - Approved action -> ALLOW
        - High-impact/send tools -> REQUIRE_APPROVAL
        - Reads -> ALLOW
        """
        event_id = f"stub-check-{uuid.uuid4().hex[:8]}"

        # Rule 1: Unknown tool
        if req.tool not in STANDARD_TOOLS:
            return CheckActionResponse(
                decision="DENY",
                reasons=[ReasonCode.TOOL_UNKNOWN],
                reason_text=f"Tool '{req.tool}' is not recognized in catalogue",
                align={"verdict": "unavailable", "score": None},
                approval=None,
                contract_version=CONTRACT_VERSION,
                event_id=event_id,
            )

        # Rule 2: If revalidating an approved action
        if req.approval_id:
            stored = self._approvals.get(req.approval_id)
            if stored and stored.get("approved"):
                current_hash = _compute_action_hash(req.tool, req.args)
                if current_hash == stored.get("action_hash"):
                    return CheckActionResponse(
                        decision="ALLOW",
                        reasons=[],
                        reason_text="Action approved by human",
                        align={"verdict": "aligned", "score": 1.0},
                        approval=None,
                        contract_version=CONTRACT_VERSION,
                        event_id=event_id,
                    )
                else:
                    return CheckActionResponse(
                        decision="DENY",
                        reasons=[ReasonCode.APPROVAL_MISMATCH],
                        reason_text="Action arguments do not match approved action",
                        align={"verdict": "misaligned", "score": 0.0},
                        approval=None,
                        contract_version=CONTRACT_VERSION,
                        event_id=event_id,
                    )

        # Rule 3: Send or write tools requiring approval
        if req.tool in ALWAYS_APPROVAL_REQUIRED or not req.read_only:
            approval_id = f"appr-{uuid.uuid4().hex[:8]}"
            action_hash = _compute_action_hash(req.tool, req.args)
            now = datetime.now(timezone.utc)

            # Build readable arg sources from provenance
            arg_sources = {
                k: "typed by user" if prov.trust.value == "user" else f"from {prov.source_type.value} ({prov.source_id})"
                for k, prov in req.arg_provenance.items()
            }

            approval = ApprovalRequest(
                approval_id=approval_id,
                task_id=req.task_id,
                exact_action={"tool": req.tool, "args": req.args},
                arg_sources=arg_sources,
                action_hash=action_hash,
                expires_at=now + timedelta(minutes=10),
            )
            self._approvals[approval_id] = {
                "approval": approval,
                "action_hash": action_hash,
                "approved": False,
            }

            return CheckActionResponse(
                decision="REQUIRE_APPROVAL",
                reasons=[ReasonCode.APPROVAL_REQUIRED],
                reason_text=f"Exact action approval required for high-impact tool '{req.tool}'",
                align={"verdict": "aligned", "score": 0.95},
                approval=approval,
                contract_version=CONTRACT_VERSION,
                event_id=event_id,
            )

        # Rule 4: Reads -> ALLOW
        return CheckActionResponse(
            decision="ALLOW",
            reasons=[],
            reason_text=f"Read-only tool '{req.tool}' allowed",
            align={"verdict": "aligned", "score": 1.0},
            approval=None,
            contract_version=CONTRACT_VERSION,
            event_id=event_id,
        )

    def submit_approval(self, approval_id: str, req: SubmitApprovalRequest) -> SubmitApprovalResponse:
        """
        Record approval or void/regenerate if edited.
        """
        event_id = f"stub-appr-{uuid.uuid4().hex[:8]}"
        record = self._approvals.get(approval_id)
        if not record:
            return SubmitApprovalResponse(
                status="expired",
                approval=None,
                event_id=event_id,
            )

        if req.edited_args:
            # Void previous approval and create new one
            old_appr: ApprovalRequest = record["approval"]
            new_id = f"appr-{uuid.uuid4().hex[:8]}"
            new_hash = _compute_action_hash(old_appr.exact_action["tool"], req.edited_args)
            now = datetime.now(timezone.utc)
            new_appr = ApprovalRequest(
                approval_id=new_id,
                task_id=old_appr.task_id,
                exact_action={"tool": old_appr.exact_action["tool"], "args": req.edited_args},
                arg_sources={k: "edited by user" for k in req.edited_args.keys()},
                action_hash=new_hash,
                expires_at=now + timedelta(minutes=10),
            )
            self._approvals[new_id] = {
                "approval": new_appr,
                "action_hash": new_hash,
                "approved": False,
            }
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
            return SubmitApprovalResponse(
                status="denied",
                approval=None,
                event_id=event_id,
            )

    def verify_state(self, req: VerifyStateRequest) -> VerifyStateResponse:
        """
        Verify post-state assertions against observed data.
        """
        failures: list[str] = []
        for assertion in req.assertions:
            if assertion.kind == "no_new_sent_mail":
                if req.observed.get("new_sent_count", 0) > 0:
                    failures.append(f"Unexpected mail sent: {req.observed.get('new_sent_count')}")
            elif assertion.kind == "mock_state_equals":
                expected = assertion.expected
                actual = req.observed.get(assertion.target)
                if expected != actual:
                    failures.append(f"State mismatch on {assertion.target}: expected {expected}, got {actual}")

        passed = len(failures) == 0
        return VerifyStateResponse(
            passed=passed,
            failures=failures,
            event_id=f"stub-verify-{uuid.uuid4().hex[:8]}",
        )

    def record_event(self, task_id: str, event_type: str, actor: str, payload: dict) -> str:
        """Test-only: accepted without persistence."""
        return f"stub-evt-{uuid.uuid4().hex[:8]}"

    def health(self) -> Health:
        """
        Returns healthy posture and stub configuration.
        """
        return Health(
            status="ok",
            tier2_available=True,
            t3_available=True,
            align_available=True,
            t2_model_hash="stub-sha256-hash",
            config_version=1,
            contract_version=CONTRACT_VERSION,
            kill_switch=KillSwitchState(all_write_tools=False, tools=[], templates=[]),
            metrics={"escalation_rate": 0.0, "p50_ms": 1.2, "p95_ms": 2.5},
        )
