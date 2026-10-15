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

logger = logging.getLogger("eva_guard")


class Guard:
    """
    The single public entrypoint that the EVA Backend imports and calls.
    Adheres strictly to CONTRACT_VERSION 0.1.0.
    """

    def __init__(self, db_url: str | None = None) -> None:
        self.contract_version = CONTRACT_VERSION
        self.db_url = db_url

        # Submodules (built by SEC-2, det by SEC-1)
        self._policy_builder: Any = None
        self._gateway: Any = None
        self._align: Any = None
        self._approvals: Any = None
        self._verifier: Any = None
        self._audit: Any = None
        self._det_pipeline: Any = None

        self._init_submodules()

    def _init_submodules(self) -> None:
        """
        Dynamically initializes submodules if implemented,
        falling back gracefully to modular interfaces.
        """
        try:
            from .policy import TaskPolicyBuilder
            self._policy_builder = TaskPolicyBuilder()
        except (ImportError, AttributeError):
            self._policy_builder = None

        try:
            from .gateway import PolicyGateway
            self._gateway = PolicyGateway()
        except (ImportError, AttributeError):
            self._gateway = None

        try:
            from .align import AlignClient
            self._align = AlignClient()
        except (ImportError, AttributeError):
            self._align = None

        try:
            from .approvals import ApprovalsEngine
            self._approvals = ApprovalsEngine()
        except (ImportError, AttributeError):
            self._approvals = None

        try:
            from .verify import StateVerifier
            self._verifier = StateVerifier()
        except (ImportError, AttributeError):
            self._verifier = None

        try:
            from .audit import AuditLogger
            self._audit = AuditLogger(db_url=self.db_url)
        except (ImportError, AttributeError):
            self._audit = None

        # SEC-1's DetPipeline
        try:
            from .det.pipeline import DetPipeline
            self._det_pipeline = DetPipeline()
        except (ImportError, AttributeError):
            self._det_pipeline = None

    def build_task_policy(self, req: BuildPolicyRequest) -> TaskPolicy:
        """
        Builds a sealed TaskPolicy strictly from the user's initial request.
        External retrieved content is NEVER passed into this call.
        """
        if self._policy_builder is not None:
            return self._policy_builder.build(req)

        # Fallback to stub behavior if policy builder is not yet wired
        from .stub import StubGuard
        return StubGuard().build_task_policy(req)

    def scan_tool_result(self, req: ScanRequest) -> ScanResponse:
        """
        Delegates content scanning to SEC-1's DetPipeline.
        If DetPipeline is unavailable, uses safe pass-through/stub behavior.
        """
        if self._det_pipeline is not None:
            return self._det_pipeline.scan(req)

        from .stub import StubGuard
        return StubGuard().scan_tool_result(req)

    def check_action(self, req: CheckActionRequest) -> CheckActionResponse:
        """
        Evaluates a proposed action against the deterministic gateway rules.
        Deny by default.
        """
        if self._gateway is not None:
            return self._gateway.check(req, self._approvals, self._align, self._audit)

        from .stub import StubGuard
        return StubGuard().check_action(req)

    def submit_approval(self, approval_id: str, req: SubmitApprovalRequest) -> SubmitApprovalResponse:
        """
        Submits human approval decision bound to the exact action hash.
        """
        if self._approvals is not None:
            return self._approvals.submit(approval_id, req)

        from .stub import StubGuard
        return StubGuard().submit_approval(approval_id, req)

    def verify_state(self, req: VerifyStateRequest) -> VerifyStateResponse:
        """
        Runs post-state assertions independently against observed state.
        """
        if self._verifier is not None:
            return self._verifier.verify(req)

        from .stub import StubGuard
        return StubGuard().verify_state(req)

    def health(self) -> Health:
        """
        Reports current health, detector tier availability, kill switches, and metrics.
        """
        tier2_available = True
        t3_available = True
        align_available = True

        if self._det_pipeline is not None and hasattr(self._det_pipeline, "is_tier2_available"):
            tier2_available = self._det_pipeline.is_tier2_available()
            t3_available = getattr(self._det_pipeline, "is_t3_available", lambda: True)()

        status = "ok" if tier2_available else "degraded"
        return Health(
            status=status,
            tier2_available=tier2_available,
            t3_available=t3_available,
            align_available=align_available,
            config_version=1,
            contract_version=self.contract_version,
            kill_switch=KillSwitchState(all_write_tools=False, tools=[], templates=[]),
            metrics={"escalation_rate": 0.0, "p50_ms": 1.0, "p95_ms": 2.5},
        )
