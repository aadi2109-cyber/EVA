"""
EVA Guard - Public Facade Class (Guard)
Contract Version: 0.1.0
Owner: SEC-2 (Authority-side Security)
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
import os
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
from .store import GuardStore

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
        # Durable authority state lives next to the audit log (same SQLite file).
        self._store = GuardStore(self._audit.db_path)
        self._approvals = ApprovalsEngine(store=self._store)
        self._verifier = StateVerifier(audit_logger=self._audit)

        # In-memory store of active task policies & original requests
        self._policies: dict[str, tuple[TaskPolicy, str]] = {}
        self._config = self._load_config()
        self.apply_config(self._config)
        # A kill switch must survive restarts (never fail open by forgetting it).
        ks = self._store.get_kill_switch()
        if ks is not None:
            self._gateway.set_kill_switch(ks)

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

    DEFAULT_CONFIG: dict[str, Any] = {
        "version": 1,
        "minimum_detector_posture": "tier2_required",   # posture given to side-effect task policies
        "failure_mode": "fail_closed",
        "block_threshold": 0.85,
        "t3_enabled": True,
        "align_enabled": True,
    }
    CONFIG_DOMAINS: dict[str, Any] = {
        "minimum_detector_posture": {"tier2_required", "tier1_ok_readonly", "tier1_only_warning"},
        "failure_mode": {"fail_closed", "tier1_only_warning"},
        "block_threshold": lambda v: isinstance(v, (int, float)) and not isinstance(v, bool) and 0.0 < v <= 1.0,
        "t3_enabled": lambda v: isinstance(v, bool),
        "align_enabled": lambda v: isinstance(v, bool),
    }

    def _load_config(self) -> dict[str, Any]:
        cfg = self._store.latest_config()
        if cfg is None:
            cfg = dict(self.DEFAULT_CONFIG)
            self._store.put_config_version(1, cfg, "system", None, None)
        return cfg

    def get_config(self) -> dict[str, Any]:
        return dict(self._config)

    def validate_config_changes(self, changes: dict[str, Any]) -> None:
        for k, v in changes.items():
            dom = self.CONFIG_DOMAINS.get(k)
            if dom is None:
                raise ValueError(f"unknown config key {k!r}")
            ok = dom(v) if callable(dom) else v in dom
            if not ok:
                raise ValueError(f"invalid value for {k!r}")

    @staticmethod
    def is_lowering(old: dict[str, Any], changes: dict[str, Any]) -> bool:
        """True when a change weakens security posture (all changes still need a second admin; this labels them)."""
        return (changes.get("minimum_detector_posture", old["minimum_detector_posture"]) != "tier2_required"
                or changes.get("failure_mode", old["failure_mode"]) != "fail_closed"
                or changes.get("t3_enabled", old["t3_enabled"]) is False
                or changes.get("align_enabled", old["align_enabled"]) is False
                or changes.get("block_threshold", old["block_threshold"]) > old["block_threshold"])

    def reset_config_for_tests(self) -> None:
        """Test/eval only: drop config versions and proposals back to defaults. Refuses outside eval/dev/test."""
        if os.getenv("APP_ENV", "dev").lower() not in ("eval", "dev", "test"):
            raise RuntimeError("reset_config_for_tests is not available in this environment")
        with self._store._conn() as c:
            c.execute("DELETE FROM config_versions"); c.execute("DELETE FROM config_proposals")
        cfg = dict(self.DEFAULT_CONFIG)
        self._store.put_config_version(1, cfg, "system", None, None)
        self.apply_config(cfg)

    def apply_config(self, cfg: dict[str, Any]) -> None:
        self._config = dict(cfg)
        self._align.enabled = bool(cfg.get("align_enabled", True))
        self._policy_builder.side_effect_posture = cfg.get("minimum_detector_posture", "tier2_required")

    def commit_config(self, changes: dict[str, Any], changed_by: str, approved_by: str, proposal_id: str) -> dict[str, Any]:
        new = {**self._config, **changes, "version": self._config["version"] + 1}
        self._store.put_config_version(new["version"], new, changed_by, approved_by, proposal_id)  # raises => not applied
        self.apply_config(new)
        return new

    def _load_policy(self, task_id: str) -> tuple[TaskPolicy, str] | None:
        hit = self._policies.get(task_id)
        if hit is None:
            hit = self._store.get_policy(task_id)
            if hit is not None:
                self._policies[task_id] = hit
        return hit

    def _audit_safe(self, task_id: str, etype: str, actor: str, payload: dict[str, Any]) -> None:
        try:
            self._audit.log_event(task_id=task_id, event_type=etype, actor=actor, payload=payload)
        except Exception as e:  # noqa: BLE001
            logger.error(f"Audit failure ({etype}): {e}")

    @staticmethod
    def _guard_error(text: str) -> CheckActionResponse:
        return CheckActionResponse(
            decision="DENY", reasons=[ReasonCode.GUARD_ERROR], reason_text=text,
            align={"verdict": "unavailable", "score": None}, approval=None,
            contract_version=CONTRACT_VERSION, event_id="err-guard-failsafe")

    def build_task_policy(self, req: BuildPolicyRequest) -> TaskPolicy:
        """
        Builds a sealed TaskPolicy strictly from the user's initial request.
        External retrieved content is NEVER passed into this call.
        """
        existing = self._load_policy(req.task_id)
        if existing is not None:
            # Policies are immutable per task: a repeat/retry returns the stored one and can never widen it.
            self._audit_safe(req.task_id, "policy.rebuild_ignored", f"user:{req.user_id}", {"origin": existing[0].origin})
            return existing[0]
        policy = self._policy_builder.build(req)
        self._store.put_policy(policy, req.user_request)  # raises on failure -> no policy, nothing can run
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

        if resp.disposition in ("quarantined", "held"):
            self._enqueue_review(req, resp)

        return resp

    def _enqueue_review(self, req: ScanRequest, resp: ScanResponse) -> None:
        """Held/quarantined content goes to the human review queue (metadata only, never raw text)."""
        try:
            self._store.put_review_item({
                "id": resp.event_id, "task_id": req.task_id, "call_id": req.call_id, "tool": req.tool,
                "disposition": resp.disposition, "fields": [f.name for f in req.fields],
                "t1_signals": resp.det_summary.t1_signals, "warnings": resp.warnings, "status": "pending",
                "created_at": datetime.now(timezone.utc).isoformat()})
        except Exception as e:  # noqa: BLE001 - review queue is informational; never blocks the (already safe) scan result
            logger.error(f"Review enqueue failed: {e}")

    def check_action(self, req: CheckActionRequest) -> CheckActionResponse:
        """
        Evaluates a proposed action against the deterministic gateway rules.
        Deny by default. Fail-safe audit.
        """
        tier2_available = True
        if self._det_pipeline is not None and hasattr(self._det_pipeline, "is_tier2_available"):
            tier2_available = self._det_pipeline.is_tier2_available()

        try:
            policy_tuple = self._load_policy(req.task_id)
        except Exception as e:  # noqa: BLE001
            logger.error(f"Policy store read failed: {e}")
            return self._guard_error("Policy store unavailable")
        policy = policy_tuple[0] if policy_tuple else None
        original_request = policy_tuple[1] if policy_tuple else None

        # Check action through deterministic gateway
        try:
            resp = self._gateway.check(
                req=req,
                policy=policy,
                tier2_available=tier2_available,
                approvals_engine=self._approvals,
                align_client=self._align,
                original_request=original_request,
            )
        except Exception as e:  # noqa: BLE001 - any internal failure (incl. approval persistence) fails closed
            logger.error(f"Gateway failure, denying: {e}")
            return self._guard_error("Internal gateway error")

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
        # Approver must be the task owner; anyone else's decision is refused (and recorded).
        rec = self._approvals._get(approval_id)
        if rec is not None:
            pol = self._load_policy(rec["approval"].task_id)
            if pol is None or pol[0].user_id != req.user_id:
                self._audit_safe(rec["approval"].task_id, "approval.rejected_wrong_user", f"user:{req.user_id}",
                                 {"approval_id": approval_id})
                return SubmitApprovalResponse(status="denied", approval=None, event_id=f"evt-appr-wronguser")
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
