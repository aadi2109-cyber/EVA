"""
Observable mock state for EVA environment and State Verifier.
Maintains state for sent mail, drafts, file hashes, and outbound HTTP requests.
"""

from __future__ import annotations

import copy
import hashlib
import json
import os
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
        self.blocked_http_requests: list[str] = []
        self.initial_file_hashes: dict[str, str] = {}
        self.mock_custom_state: dict[str, Any] = {}

        # Optional cross-process persistence (MOCK_STATE_FILE) so `python -m env.mock.reset`
        # can reset the state of an already running API process / compose service.
        self.state_file: Path | None = Path(os.environ["MOCK_STATE_FILE"]) if os.environ.get("MOCK_STATE_FILE") else None
        self._loaded_mtime: float = 0.0
        self.snapshot_initial_state()
        self._load()

    _PERSISTED = ("sent_messages", "drafts", "outbound_http_requests", "blocked_http_requests", "mock_custom_state", "initial_sent_count")

    def _persist(self) -> None:
        if not self.state_file:
            return
        try:
            self.state_file.parent.mkdir(parents=True, exist_ok=True)
            tmp = self.state_file.with_suffix(".tmp")
            tmp.write_text(json.dumps({k: getattr(self, k) for k in self._PERSISTED}, default=str), encoding="utf-8")
            tmp.replace(self.state_file)
            self._loaded_mtime = self.state_file.stat().st_mtime
        except OSError:
            pass

    def _load(self) -> None:
        if not self.state_file or not self.state_file.exists():
            return
        try:
            mtime = self.state_file.stat().st_mtime
            if mtime == self._loaded_mtime:
                return
            data = json.loads(self.state_file.read_text(encoding="utf-8"))
            for k in self._PERSISTED:
                if k in data:
                    setattr(self, k, data[k])
            self._loaded_mtime = mtime
        except (OSError, ValueError):
            pass

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

    def record_sent_mail(
        self, to: str, subject: str, body: str, draft_id: str | None = None, message_id: str | None = None
    ) -> dict[str, Any]:
        msg = {
            "id": message_id or f"sent-{len(self.sent_messages) + 1}",
            "to": to,
            "subject": subject,
            "body": body,
            "draft_id": draft_id,
        }
        self._load()
        self.sent_messages.append(msg)
        self._persist()
        return msg

    def record_draft(self, to: str, subject: str, body: str, draft_id: str | None = None) -> dict[str, Any]:
        draft = {
            "id": draft_id or f"draft-{len(self.drafts) + 1}",
            "to": to,
            "subject": subject,
            "body": body,
        }
        self._load()
        self.drafts.append(draft)
        self._persist()
        return draft

    def record_http_request(self, url: str) -> None:
        self._load()
        self.outbound_http_requests.append(url)
        self._persist()

    def record_blocked_http_request(self, url: str) -> None:
        """A fetch the tool refused (policy) - kept separate from requests actually made."""
        self._load()
        self.blocked_http_requests.append(url)
        self._persist()

    def set_custom_state(self, key: str, value: Any) -> None:
        self._load()
        self.mock_custom_state[key] = value
        self._persist()

    def observe_state(self) -> dict[str, Any]:
        """
        Produce observed state dictionary matching StateVerifier expectations.
        """
        self._load()
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
            "blocked_http_requests": list(self.blocked_http_requests),
        }
        observed.update(self.mock_custom_state)
        return observed

    def reset(self) -> None:
        """Reset mutable records to initial empty state."""
        self.sent_messages.clear()
        self.drafts.clear()
        self.outbound_http_requests.clear()
        self.blocked_http_requests.clear()
        self.mock_custom_state.clear()
        self.snapshot_initial_state()
        self._persist()


# Global default singleton instance for runtime and tests
state = MockEnvironmentState()
