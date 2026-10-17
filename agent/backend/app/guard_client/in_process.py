"""
In-process GuardClient implementation directly invoking eva_guard facade or StubGuard.
"""

from __future__ import annotations

import logging
from typing import Any

from contracts.models import (
    BuildPolicyRequest,
    CheckActionRequest,
    CheckActionResponse,
    Health,
    ScanRequest,
    ScanResponse,
    SubmitApprovalRequest,
    SubmitApprovalResponse,
    TaskPolicy,
    VerifyStateRequest,
    VerifyStateResponse,
)
from app.eval import hooks
from app.guard_client.base import GuardError

logger = logging.getLogger(__name__)


class InProcessGuardClient:
    """Invokes eva_guard.api.Guard directly in-process (StubGuard only when explicitly injected)."""

    def __init__(self, guard_instance: Any = None) -> None:
        self._policies = {}
        self._init_error: str | None = None
        self._guard_obj: Any = None
        if guard_instance is not None:  # explicit injection (tests, eval harness)
            self._guard_obj = guard_instance
            return
        # NEVER fall back to the test-only StubGuard: if the real facade cannot load, every guard call
        # fails closed (GuardError -> deny/held) and /api/health reports the guard as down.
        try:
            from eva_guard.api import Guard

            self._guard_obj = Guard()
            logger.info("InProcessGuardClient initialized with eva_guard.api.Guard facade")
        except Exception as e:  # pragma: no cover - exercised via monkeypatch in tests
            self._init_error = f"{type(e).__name__}: {e}"
            logger.error("eva_guard.api.Guard failed to load (%s); guard unavailable, failing closed", self._init_error)

    @property
    def _guard(self) -> Any:
        if self._guard_obj is None:
            raise GuardError(f"Guard unavailable: real eva_guard failed to load ({self._init_error})")
        return self._guard_obj

    @property
    def implementation(self) -> str:
        """Which guard is really behind this client (shown in /api/health)."""
        if self._guard_obj is None:
            return "unavailable"
        t = type(self._guard_obj)
        return f"{t.__module__}.{t.__name__}"

    _policies: dict[str, TaskPolicy]

    def _check_injected_down(self) -> None:
        hooks.raise_if_unreachable()

    async def build_task_policy(self, req: BuildPolicyRequest) -> TaskPolicy:
        self._check_injected_down()
        try:
            policy = self._guard.build_task_policy(req)
            self._policies[req.task_id] = policy
            return policy
        except Exception as e:
            logger.error("Guard build_task_policy failed: %s", e)
            raise GuardError(f"build_task_policy failed: {e}") from e

    async def scan_tool_result(self, req: ScanRequest) -> ScanResponse:
        self._check_injected_down()
        try:
            resp = self._guard.scan_tool_result(req)
            if hooks.profile() == "off":
                return hooks.passthrough_scan(req, resp)
            return hooks.adjust_scan(resp)
        except Exception as e:
            logger.error("Guard scan_tool_result failed: %s", e)
            raise GuardError(f"scan_tool_result failed: {e}") from e

    async def check_action(self, req: CheckActionRequest) -> CheckActionResponse:
        self._check_injected_down()
        try:
            override = hooks.profile_check(req, self._policies.get(req.task_id))
            if override is not None:
                return override
            return hooks.adjust_check(req, self._guard.check_action(req))
        except Exception as e:
            logger.error("Guard check_action failed: %s", e)
            raise GuardError(f"check_action failed: {e}") from e

    async def submit_approval(self, approval_id: str, req: SubmitApprovalRequest) -> SubmitApprovalResponse:
        self._check_injected_down()
        try:
            return self._guard.submit_approval(approval_id, req)
        except Exception as e:
            logger.error("Guard submit_approval failed: %s", e)
            raise GuardError(f"submit_approval failed: {e}") from e

    async def verify_state(self, req: VerifyStateRequest) -> VerifyStateResponse:
        self._check_injected_down()
        try:
            return self._guard.verify_state(req)
        except Exception as e:
            logger.error("Guard verify_state failed: %s", e)
            raise GuardError(f"verify_state failed: {e}") from e

    async def health(self) -> Health:
        self._check_injected_down()
        try:
            return hooks.adjust_health(self._guard.health())
        except Exception as e:
            logger.error("Guard health check failed: %s", e)
            raise GuardError(f"health failed: {e}") from e
