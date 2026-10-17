"""
HTTP GuardClient implementation calling EVA Guard service via REST API.
Enforces strict timeouts (3s check, 5s scan) and fail-closed error handling.
"""

from __future__ import annotations

import logging
from typing import Any
import httpx

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
from app.eval import hooks
from app.guard_client.base import GuardClient, GuardDownError, GuardError

logger = logging.getLogger(__name__)


class HttpGuardClient:
    """Interacts with the EVA Guard standalone HTTP service."""

    def __init__(
        self,
        base_url: str | None = None,
        token: str | None = None,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        self.base_url = (base_url or settings.GUARD_SERVICE_URL).rstrip("/")
        self.token = token or settings.GUARD_SERVICE_TOKEN
        self._transport = transport  # tests: in-process ASGI transport
        self.headers = {
            "Authorization": f"Bearer {self.token}",
            "Content-Type": "application/json",
        }

    def _client(self, timeout: float) -> httpx.AsyncClient:
        return httpx.AsyncClient(timeout=timeout, transport=self._transport)

    def _check_injected_down(self) -> None:
        hooks.raise_if_unreachable()

    async def _post_with_retry(self, path: str, json_data: dict[str, Any], timeout: float, is_idempotent: bool = True) -> dict[str, Any]:
        """POST with fail-closed semantics.

        Exactly one retry, and only for idempotent calls that failed with a
        connection-level error (connect failure / reset / dropped read).
        Timeouts and HTTP errors are never retried.
        """
        self._check_injected_down()
        url = f"{self.base_url}{path}"
        max_attempts = 2 if is_idempotent else 1

        for attempt in range(1, max_attempts + 1):
            try:
                async with self._client(timeout) as client:
                    resp = await client.post(url, json=json_data, headers=self.headers)
            except httpx.TimeoutException as e:
                logger.error("Guard timeout on %s: %s", path, e)
                raise GuardError(f"Guard request timed out on {path}: {e}") from e
            except (httpx.ConnectError, httpx.ReadError, httpx.WriteError, httpx.RemoteProtocolError) as e:
                logger.error("Guard connection error on %s (attempt %d): %s", path, attempt, e)
                if attempt == max_attempts:
                    raise GuardDownError(f"Guard unreachable at {url}: {e}") from e
                continue
            except Exception as e:
                logger.error("Guard unexpected HTTP error on %s: %s", path, e)
                raise GuardError(f"Guard request failed on {path}: {e}") from e

            if resp.status_code >= 400:
                raise GuardError(f"Guard service returned HTTP {resp.status_code} on {path}")
            try:
                data = resp.json()
            except ValueError as e:
                raise GuardError(f"Guard returned non-JSON response on {path}") from e
            if not isinstance(data, dict):
                raise GuardError(f"Guard returned unexpected payload on {path}")
            return data

        raise GuardDownError(f"Guard failed after {max_attempts} attempts on {path}")

    @staticmethod
    def _parse(model: Any, data: dict[str, Any], what: str) -> Any:
        try:
            return model.model_validate(data)
        except Exception as e:
            raise GuardError(f"Guard returned malformed {what} response: {e}") from e

    async def build_task_policy(self, req: BuildPolicyRequest) -> TaskPolicy:
        data = await self._post_with_retry("/v1/policy", req.model_dump(mode="json"), timeout=3.0, is_idempotent=True)
        return self._parse(TaskPolicy, data, "policy")

    async def scan_tool_result(self, req: ScanRequest) -> ScanResponse:
        data = await self._post_with_retry("/v1/scan", req.model_dump(mode="json"), timeout=5.0, is_idempotent=True)
        return self._parse(ScanResponse, data, "scan")

    async def check_action(self, req: CheckActionRequest) -> CheckActionResponse:
        data = await self._post_with_retry("/v1/check-action", req.model_dump(mode="json"), timeout=3.0, is_idempotent=True)
        return self._parse(CheckActionResponse, data, "check_action")

    async def submit_approval(self, approval_id: str, req: SubmitApprovalRequest) -> SubmitApprovalResponse:
        data = await self._post_with_retry(f"/v1/approvals/{approval_id}", req.model_dump(mode="json"), timeout=3.0, is_idempotent=False)
        return self._parse(SubmitApprovalResponse, data, "submit_approval")

    async def verify_state(self, req: VerifyStateRequest) -> VerifyStateResponse:
        data = await self._post_with_retry("/v1/verify-state", req.model_dump(mode="json"), timeout=3.0, is_idempotent=True)
        return self._parse(VerifyStateResponse, data, "verify_state")

    async def record_event(self, task_id: str, event_type: str, actor: str, payload: dict) -> str:
        self._check_injected_down()
        body = {"task_id": task_id, "event_type": event_type, "actor": actor, "payload": payload}
        data = await self._post_with_retry("/v1/audit/events", body, timeout=3.0, is_idempotent=False)
        try:
            return str(data["event_id"])
        except (KeyError, TypeError) as e:
            raise GuardError(f"record_event returned a malformed response: {e}") from e

    async def health(self) -> Health:
        self._check_injected_down()
        url = f"{self.base_url}/v1/health"
        try:
            async with self._client(3.0) as client:
                resp = await client.get(url, headers=self.headers)
            if resp.status_code != 200:
                raise GuardError(f"Guard health returned HTTP {resp.status_code}")
            return Health.model_validate(resp.json())
        except Exception as e:
            logger.error("Guard health check failed: %s", e)
            raise GuardDownError(f"Guard health endpoint unreachable: {e}") from e
