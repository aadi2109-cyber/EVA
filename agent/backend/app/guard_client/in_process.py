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
from app.config import settings
from app.guard_client.base import GuardClient, GuardDownError, GuardError

logger = logging.getLogger(__name__)


class InProcessGuardClient:
    """Invokes eva_guard.api.Guard (or StubGuard) directly in-process."""

    def __init__(self, guard_instance: Any = None) -> None:
        if guard_instance is not None:
            self._guard = guard_instance
        else:
            # Try importing Guard facade first, fall back to StubGuard
            try:
                from eva_guard.api import Guard
                self._guard = Guard()
                logger.info("InProcessGuardClient initialized with eva_guard.api.Guard facade")
            except Exception as e:
                logger.warning(
                    "Failed to initialize eva_guard.api.Guard facade (%s); falling back to StubGuard", e
                )
                from eva_guard.stub import StubGuard
                self._guard = StubGuard()

    def _check_injected_down(self) -> None:
        if settings.APP_ENV == "eval" and settings.INJECT_GUARD_UNREACHABLE:
            raise GuardDownError("Injected failure: guard service is unreachable")

    async def build_task_policy(self, req: BuildPolicyRequest) -> TaskPolicy:
        self._check_injected_down()
        try:
            return self._guard.build_task_policy(req)
        except Exception as e:
            logger.error("Guard build_task_policy failed: %s", e)
            raise GuardError(f"build_task_policy failed: {e}") from e

    async def scan_tool_result(self, req: ScanRequest) -> ScanResponse:
        self._check_injected_down()
        try:
            return self._guard.scan_tool_result(req)
        except Exception as e:
            logger.error("Guard scan_tool_result failed: %s", e)
            raise GuardError(f"scan_tool_result failed: {e}") from e

    async def check_action(self, req: CheckActionRequest) -> CheckActionResponse:
        self._check_injected_down()
        try:
            return self._guard.check_action(req)
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
            return self._guard.health()
        except Exception as e:
            logger.error("Guard health check failed: %s", e)
            raise GuardError(f"health failed: {e}") from e
