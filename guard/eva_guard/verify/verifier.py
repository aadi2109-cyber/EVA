"""
State Verifier.
Contract Version: 0.1.0
Owner: SEC-2 (Authority-side Security)
"""

from __future__ import annotations

import logging
import uuid
from typing import Any

from contracts.models import (
    StateAssertion,
    VerifyStateRequest,
    VerifyStateResponse,
)

logger = logging.getLogger(__name__)


class StateVerifier:
    """
    Independently verifies post-execution environment state against assertions.
    Takes observed state gathered from tools/connectors/mocks, NEVER from LLM output.
    """

    def __init__(self, audit_logger: Any = None) -> None:
        self.audit_logger = audit_logger

    def verify(self, req: VerifyStateRequest) -> VerifyStateResponse:
        failures: list[str] = []
        observed = req.observed or {}

        for assertion in req.assertions:
            kind = assertion.kind
            target = assertion.target
            expected = assertion.expected

            if kind == "no_new_sent_mail":
                sent_count = observed.get("new_sent_count", 0)
                if sent_count > 0:
                    failures.append(f"Assertion failed: no_new_sent_mail violated (observed {sent_count} new sent messages)")

            elif kind == "file_unchanged":
                # Check if target file hash changed
                initial_hash = observed.get("initial_file_hashes", {}).get(target)
                current_hash = observed.get("current_file_hashes", {}).get(target)
                if initial_hash is not None and current_hash is not None and initial_hash != current_hash:
                    failures.append(f"Assertion failed: file_unchanged violated for '{target}' (hash changed from {initial_hash} to {current_hash})")

            elif kind == "file_written_with_hash":
                actual_hash = observed.get("file_hashes", {}).get(target)
                if actual_hash != expected:
                    failures.append(f"Assertion failed: file_written_with_hash for '{target}' expected {expected}, got {actual_hash}")

            elif kind == "draft_created":
                draft_ids = observed.get("created_draft_ids", [])
                if target not in draft_ids and not draft_ids:
                    failures.append(f"Assertion failed: draft_created violated, draft '{target}' was not observed")

            elif kind == "no_outbound_http_to":
                outbound_requests = observed.get("outbound_http_requests", [])
                for req_entry in outbound_requests:
                    req_url = req_entry if isinstance(req_entry, str) else req_entry.get("url", "")
                    if target.lower() in req_url.lower():
                        failures.append(f"Assertion failed: no_outbound_http_to violated for '{target}' (found request to {req_url})")

            elif kind == "mock_state_equals":
                actual_val = observed.get(target)
                if actual_val != expected:
                    failures.append(f"Assertion failed: mock_state_equals for key '{target}' expected {expected}, got {actual_val}")

            else:
                failures.append(f"Unknown assertion kind '{kind}'")

        passed = len(failures) == 0
        event_id = f"evt-verify-{uuid.uuid4().hex[:10]}"

        if self.audit_logger is not None:
            try:
                self.audit_logger.log_event(
                    task_id=req.task_id,
                    event_type="state.verified",
                    actor="guard.verifier",
                    payload={"passed": passed, "failures": failures, "call_id": req.call_id},
                )
            except Exception as e:
                logger.error(f"Failed to audit state verification: {e}")

        return VerifyStateResponse(
            passed=passed,
            failures=failures,
            event_id=event_id,
        )
