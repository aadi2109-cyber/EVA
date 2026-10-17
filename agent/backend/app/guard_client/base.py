"""
Abstract GuardClient Protocol and custom exceptions for EVA Agent Backend.
"""

from __future__ import annotations

from typing import Protocol, runtime_checkable

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


class GuardError(Exception):
    """Raised when Guard returns an error, times out, or is unreachable."""
    pass


class GuardDownError(GuardError):
    """Raised when Guard service is completely down or unreachable."""
    pass


@runtime_checkable
class GuardClient(Protocol):
    """Protocol for interacting with the EVA Guard security system."""

    async def build_task_policy(self, req: BuildPolicyRequest) -> TaskPolicy:
        """Derive task execution policy from user request only."""
        ...

    async def scan_tool_result(self, req: ScanRequest) -> ScanResponse:
        """Scan tool outputs before feeding them to the model context."""
        ...

    async def check_action(self, req: CheckActionRequest) -> CheckActionResponse:
        """Evaluate gateway policy rules before executing any tool call."""
        ...

    async def submit_approval(self, approval_id: str, req: SubmitApprovalRequest) -> SubmitApprovalResponse:
        """Submit a user approval or denial decision for an exact action."""
        ...

    async def verify_state(self, req: VerifyStateRequest) -> VerifyStateResponse:
        """Verify post-action environment state against policy assertions."""
        ...

    async def record_event(self, task_id: str, event_type: str, actor: str, payload: dict) -> str:
        """Append a backend-originated event (allowlisted types only) to the guard's audit chain."""
        ...

    async def health(self) -> Health:
        """Query guard operational status and detector posture."""
        ...
