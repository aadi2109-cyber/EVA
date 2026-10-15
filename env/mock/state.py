"""
Observable mock state for EVA environment and State Verifier.
Maintains state for sent mail, drafts, file hashes, and outbound HTTP requests.
"""

from __future__ import annotations

import copy
import hashlib
import json
from pathlib import Path
from typing import Any


class MockEnvironmentState:
    """Singleton/Instance tracking observable mock state."""

    def __init__(self, mailbox_path: Path | None = None, workspace_dir: Path | None = None) -> None:
        self.mailbox_path = mailbox_path or Path(__file__).parent / "mailbox.json"
        self.workspace_dir = workspace_dir or Path(__file__).parent / "workspace"

        self.initial_sent_count: int = 0
        self.sent_messages: list[dict[str, Any]] = []
        self.drafts: list[dict[str, Any]] = []
        self.outbound_http_requests: list[str] = []
        self.initial_file_hashes: dict[str, str] = {}
        self.mock_custom_state: dict[str, Any] = {}

        self.snapshot_initial_state()

    def snapshot_initial_state(self) -> None:
        """Capture initial baseline state for verification diffs."""
        self.initial_sent_count = len(self.sent_messages)
        self.initial_file_hashes = self._compute_all_file_hashes()

    def _compute_all_file_hashes(self) -> dict[str, str]:
        hashes = {}
        if self.workspace_dir.exists():
            for p in self.workspace_dir.rglob("*"):
                if p.is_file():
                    try:
                        hashes[str(p.name)] = hashlib.sha256(p.read_bytes()).hexdigest()
                    except Exception:
                        pass
        return hashes

    def record_sent_mail(self, to: str, subject: str, body: str, draft_id: str | None = None) -> dict[str, Any]:
        msg = {
            "id": f"sent-{len(self.sent_messages) + 1}",
            "to": to,
            "subject": subject,
            "body": body,
            "draft_id": draft_id,
        }
        self.sent_messages.append(msg)
        return msg

    def record_draft(self, to: str, subject: str, body: str) -> dict[str, Any]:
        draft = {
            "id": f"draft-{len(self.drafts) + 1}",
            "to": to,
            "subject": subject,
            "body": body,
        }
        self.drafts.append(draft)
        return draft

    def record_http_request(self, url: str) -> None:
        self.outbound_http_requests.append(url)

    def set_custom_state(self, key: str, value: Any) -> None:
        self.mock_custom_state[key] = value

    def observe_state(self) -> dict[str, Any]:
        """
        Produce observed state dictionary matching StateVerifier expectations.
        """
        current_hashes = self._compute_all_file_hashes()
        new_sent = max(0, len(self.sent_messages) - self.initial_sent_count)

        observed: dict[str, Any] = {
            "new_sent_count": new_sent,
            "sent_messages": copy.deepcopy(self.sent_messages),
            "created_draft_ids": [d["id"] for d in self.drafts],
            "drafts": copy.deepcopy(self.drafts),
            "initial_file_hashes": copy.deepcopy(self.initial_file_hashes),
            "current_file_hashes": current_hashes,
            "file_hashes": current_hashes,
            "outbound_http_requests": list(self.outbound_http_requests),
        }
        observed.update(self.mock_custom_state)
        return observed

    def reset(self) -> None:
        """Reset mutable records to initial empty state."""
        self.sent_messages.clear()
        self.drafts.clear()
        self.outbound_http_requests.clear()
        self.mock_custom_state.clear()
        self.snapshot_initial_state()


# Global default singleton instance for runtime and tests
state = MockEnvironmentState()
