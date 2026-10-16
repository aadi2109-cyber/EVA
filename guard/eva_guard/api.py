"""
EVA Guard - Public Facade Class (Guard)
Contract Version: 0.1.0
Owner: SEC-2 (Authority-side Security)
"""

from __future__ import annotations

import logging
from typing import Any

from contracts.models import (
    CONTRACT_VERSION,
    BuildPolicyRequest,
    TaskPolicy,
    ScanRequest,
    ScanResponse,
    CheckActionRequest,
    CheckActionResponse,
    SubmitApprovalRequest,
    SubmitApprovalResponse,
    VerifyStateRequest,
    VerifyStateResponse,
    Health,
    KillSwitchState,
    ReasonCode,
)

from .policy import TaskPolicyBuilder
from .gateway import PolicyGateway
from .align import AlignClient
from .approvals import ApprovalsEngine
from .verify import StateVerifier
from .audit import AuditLogger

logger = logging.getLogger("eva_guard")


class Guard:
    """
    The single public entrypoint that the EVA Backend imports and calls.
    Adheres strictly to CONTRACT_VERSION 0.1.0.
    """

    def __init__(self, db_url: str | None = None, t3_provider: Any = None) -> None:
        self.contract_version = CONTRACT_VERSION
        self.db_url = db_url
        self._t3_provider = t3_provider  # any det.t3.Tier3Provider; None => default LAYA adapter

        # Initialise core authority-side modules
        self._audit = AuditLogger(db_url=self.db_url)
        self._policy_builder = TaskPolicyBuilder()
        self._gateway = PolicyGateway()
        self._align = AlignClient()
        self._approvals = ApprovalsEngine()
        self._verifier = StateVerifier(audit_logger=self._audit)

        # In-memory store of active task policies & original requests
        self._policies: dict[str, tuple[TaskPolicy, str]] = {}

        # SEC-1's DetPipeline placeholder / dynamic import
        self._det_pipeline: Any = None
        self._init_det_pipeline()

    def _init_det_pipeline(self) -> None:
        try:
            from .det.pipeline import DetPipeline
            from .det.t3 import create_t3_provider
            t3 = self._t3_provider if self._t3_provider is not None else create_t3_provider()
            self._det_pipeline = DetPipeline(audit=None, t3=t3)
        except (ImportError, AttributeError):
            self._det_pipeline = None

    def build_task_policy(self, req: BuildPolicyRequest) -> TaskPolicy:
        """
        Builds a sealed TaskPolicy strictly from the user's initial request.
        External retrieved content is NEVER passed into this call.
        """
        policy = self._policy_builder.build(req)
        self._policies[req.task_id] = (policy, req.user_request)

        # Audit policy build event
        try:
            self._audit.log_event(
                task_id=req.task_id,
                event_type="policy.built",
                actor=f"user:{req.user_id}",
                payload={
                    "allowed_operations": policy.allowed_operations,
                    "allowed_destinations": policy.allowed_destinations,
                    "prohibited_side_effects": policy.prohibited_side_effects,
                    "approval_required_for": policy.approval_required_for,
                    "origin": policy.origin,
                },
            )
        except Exception as e:
            logger.error(f"Audit failure during policy build: {e}")

        return policy

    def scan_tool_result(self, req: ScanRequest) -> ScanResponse:
        """
        Delegates content scanning to SEC-1's DetPipeline.
        If DetPipeline is unavailable, uses safe fallback scanner.
        """
        if self._det_pipeline is not None and hasattr(self._det_pipeline, "scan"):
            resp = self._det_pipeline.scan(req)
        else:
            from .stub import StubGuard
            resp = StubGuard().scan_tool_result(req)
            if "DET_PIPELINE_ABSENT" not in resp.warnings:
                resp.warnings.append("DET_PIPELINE_ABSENT")

        # Audit scan event
        try:
            self._audit.log_event(
                task_id=req.task_id,
                event_type="det.scan",
                actor=f"tool:{req.tool}",
                payload={
                    "call_id": req.call_id,
                    "tool": req.tool,
                    "disposition": resp.disposition,
                    "det_summary": resp.det_summary.model_dump(),
                    "tier2_available": resp.tier2_available,
                },
            )
        except Exception as e:
            logger.error(f"Audit failure during scan: {e}")

        return resp

    def check_action(self, req: CheckActionRequest) -> CheckActionResponse:
        """
        Evaluates a proposed action against the deterministic gateway rules.
        Deny by default. Fail-safe audit.
        """
        tier2_available = True
        if self._det_pipeline is not None and hasattr(self._det_pipeline, "is_tier2_available"):
            tier2_available = self._det_pipeline.is_tier2_available()

        policy_tuple = self._policies.get(req.task_id)
        policy = policy_tuple[0] if policy_tuple else None
        original_request = policy_tuple[1] if policy_tuple else None

        # Check action through deterministic gateway
        resp = self._gateway.check(
            req=req,
            policy=policy,
            tier2_available=tier2_available,
            approvals_engine=self._approvals,
            align_client=self._align,
            original_request=original_request,
        )

        # Fail-safe audit write: if audit logging fails, DENY the action!
        try:
            self._audit.log_event(
                task_id=req.task_id,
                event_type="gateway.decision",
                actor=f"tool:{req.tool}",
                payload={
                    "call_id": req.call_id,
                    "tool": req.tool,
                    "decision": resp.decision,
                    "reasons": [r.value for r in resp.reasons],
                    "read_only": req.read_only,
                    "approval_id": req.approval_id,
                },
            )
        except Exception as e:
            logger.error(f"Fail-safe audit triggered: audit log failed ({e}), denying action")
            return CheckActionResponse(
                decision="DENY",
                reasons=[ReasonCode.GUARD_ERROR],
                reason_text="Fail-safe audit error: security event could not be logged",
                align={"verdict": "unavailable", "score": None},
                approval=None,
                contract_version=CONTRACT_VERSION,
                event_id="err-audit-failsafe",
            )

        return resp

    def submit_approval(self, approval_id: str, req: SubmitApprovalRequest) -> SubmitApprovalResponse:
        """
        Submits human approval decision bound to the exact action hash.
        """
        resp = self._approvals.submit(approval_id, req)

        # Audit approval resolution
        try:
            self._audit.log_event(
                task_id=approval_id,
                event_type="approval.resolved",
                actor=f"user:{req.user_id}",
                payload={
                    "approval_id": approval_id,
                    "status": resp.status,
                    "approved": req.approved,
                    "edited": req.edited_args is not None,
                },
            )
        except Exception as e:
            logger.error(f"Audit failure during submit approval: {e}")

        return resp

    def verify_state(self, req: VerifyStateRequest) -> VerifyStateResponse:
        """
        Runs post-state assertions independently against observed state.
        """
        return self._verifier.verify(req)

    def health(self) -> Health:
        """
        Reports current health, detector tier availability, kill switches, and metrics.
        """
        tier2_available = True
        t3_available = False
        det_metrics: dict[str, float] = {}
        align_available = self._align.is_available()

        if self._det_pipeline is not None and hasattr(self._det_pipeline, "is_tier2_available"):
            tier2_available = self._det_pipeline.is_tier2_available()
            t3_available = getattr(self._det_pipeline, "is_t3_available", lambda: False)()
            if hasattr(self._det_pipeline, "health"):
                det_metrics = {k: float(v) for k, v in self._det_pipeline.health().metrics.items()}

        status = "ok" if tier2_available else "degraded"
        return Health(
            status=status,
            tier2_available=tier2_available,
            t3_available=t3_available,
            align_available=align_available,
            config_version=1,
            contract_version=self.contract_version,
            kill_switch=self._gateway.kill_switch,
            metrics={"escalation_rate": 0.0, "p50_ms": 0.0, "p95_ms": 0.0, **det_metrics},
        )
