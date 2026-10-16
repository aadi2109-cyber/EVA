"""
Durable state for the authority side: task policies (immutable once stored), approvals (single-use flags
persisted before ALLOW is returned) and the kill switch. SQLite, same file as the audit log.
A restart therefore keeps live tasks working and never forgets a kill switch or a consumed approval.
Write failures raise; callers treat that as DENY (fail closed).
"""
from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from contracts.models import ApprovalRequest, KillSwitchState, TaskPolicy

_DDL = """
CREATE TABLE IF NOT EXISTS task_policies (
    task_id TEXT PRIMARY KEY,
    policy_json TEXT NOT NULL,
    user_request TEXT NOT NULL,
    created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS approvals (
    approval_id TEXT PRIMARY KEY,
    task_id TEXT NOT NULL,
    approval_json TEXT NOT NULL,
    action_hash TEXT NOT NULL,
    approved INTEGER NOT NULL DEFAULT 0,
    consumed INTEGER NOT NULL DEFAULT 0,
    user_id TEXT,
    created_at TEXT NOT NULL,
    expires_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_approvals_task ON approvals(task_id);
CREATE TABLE IF NOT EXISTS kill_switch (
    id INTEGER PRIMARY KEY CHECK (id = 1),
    state_json TEXT NOT NULL,
    updated_at TEXT NOT NULL
);
"""


class GuardStore:
    def __init__(self, db_path: str | Path) -> None:
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        with self._conn() as c:
            c.executescript(_DDL)

    def _conn(self) -> sqlite3.Connection:
        c = sqlite3.connect(str(self.db_path), timeout=5)
        c.execute("PRAGMA journal_mode=WAL;")
        c.row_factory = sqlite3.Row
        return c

    # ---- policies: insert-only (a task's policy can never be replaced or widened) ----
    def put_policy(self, policy: TaskPolicy, user_request: str) -> bool:
        """Returns True if stored, False if a policy already existed (left untouched)."""
        with self._conn() as c:
            cur = c.execute("INSERT OR IGNORE INTO task_policies VALUES (?,?,?,?)",
                            (policy.task_id, policy.model_dump_json(), user_request, datetime.now(timezone.utc).isoformat()))
            return cur.rowcount == 1

    def get_policy(self, task_id: str) -> tuple[TaskPolicy, str] | None:
        with self._conn() as c:
            r = c.execute("SELECT policy_json, user_request FROM task_policies WHERE task_id=?", (task_id,)).fetchone()
        return (TaskPolicy.model_validate_json(r["policy_json"]), r["user_request"]) if r else None

    # ---- approvals ----
    def put_approval(self, rec: dict[str, Any]) -> None:
        a: ApprovalRequest = rec["approval"]
        with self._conn() as c:
            c.execute(
                """INSERT INTO approvals VALUES (?,?,?,?,?,?,?,?,?)
                   ON CONFLICT(approval_id) DO UPDATE SET approved=excluded.approved, consumed=excluded.consumed, user_id=excluded.user_id""",
                (a.approval_id, a.task_id, a.model_dump_json(), rec["action_hash"], int(rec["approved"]), int(rec["consumed"]),
                 rec.get("user_id"), rec["created_at"].isoformat(), rec["expires_at"].isoformat()))

    def get_approval(self, approval_id: str) -> dict[str, Any] | None:
        with self._conn() as c:
            r = c.execute("SELECT * FROM approvals WHERE approval_id=?", (approval_id,)).fetchone()
        if not r:
            return None
        return {"approval": ApprovalRequest.model_validate_json(r["approval_json"]), "action_hash": r["action_hash"],
                "approved": bool(r["approved"]), "consumed": bool(r["consumed"]), "user_id": r["user_id"],
                "created_at": datetime.fromisoformat(r["created_at"]), "expires_at": datetime.fromisoformat(r["expires_at"])}

    # ---- kill switch ----
    def put_kill_switch(self, ks: KillSwitchState) -> None:
        with self._conn() as c:
            c.execute("INSERT INTO kill_switch VALUES (1,?,?) ON CONFLICT(id) DO UPDATE SET state_json=excluded.state_json, updated_at=excluded.updated_at",
                      (ks.model_dump_json(), datetime.now(timezone.utc).isoformat()))

    def get_kill_switch(self) -> KillSwitchState | None:
        with self._conn() as c:
            r = c.execute("SELECT state_json FROM kill_switch WHERE id=1").fetchone()
        return KillSwitchState.model_validate_json(r["state_json"]) if r else None
