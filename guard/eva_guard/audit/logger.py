"""
Hash-Chained Audit Log.
Contract Version: 0.1.0
Owner: SEC-2 (Authority-side Security)
"""

from __future__ import annotations

import hashlib
import json
import os
import logging
import re
import sqlite3
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from contracts.models import AuditEvent, AuditVerifyResponse

logger = logging.getLogger(__name__)

GENESIS_HASH = "0" * 64

# Sensitive pattern regexes for redaction
REDACTION_PATTERNS = [
    re.compile(r"bearer\s+[a-zA-Z0-9_\-\.]+", re.IGNORECASE),
    re.compile(r"(?:api[_-]?key|secret|password|token)(?:\s+(?:key|password|token|secret))?[:=\s]+[a-zA-Z0-9_\-\.]+", re.IGNORECASE),
]




def canonical_json(data: Any) -> str:
    return json.dumps(data, sort_keys=True, separators=(",", ":"), default=str)


def redact_text(text: str) -> str:
    """
    Redacts sensitive keys/tokens and truncates snippets to max 120 chars.
    """
    result = text
    for pattern in REDACTION_PATTERNS:
        result = pattern.sub("[REDACTED_SECRET]", result)
    if len(result) > 120:
        result = result[:117] + "..."
    return result


def sanitize_payload(payload: Any) -> Any:
    """
    Recursively redacts text in payloads to ensure raw secrets or injection bodies
    never enter the permanent audit table.
    """
    if isinstance(payload, str):
        return redact_text(payload)
    if isinstance(payload, dict):
        return {k: sanitize_payload(v) for k, v in payload.items()}
    if isinstance(payload, list):
        return [sanitize_payload(v) for v in payload]
    return payload


class AuditLogger:
    """
    Append-only tamper-evident hash-chained audit logger.
    Guarantees fail-safe audit: if write fails, raises AuditError so caller denies.
    """

    def __init__(self, db_path: str | Path | None = None, db_url: str | None = None) -> None:
        if db_path is None:
            if db_url and db_url.startswith("sqlite:///"):
                self.db_path = Path(db_url.replace("sqlite:///", ""))
            else:
                self.db_path = Path(os.getenv("GUARD_DB_PATH", "./guard.db"))
        else:
            self.db_path = Path(db_path)

        self._init_db()

    def _get_connection(self) -> sqlite3.Connection:
        conn = sqlite3.connect(str(self.db_path))
        conn.execute("PRAGMA journal_mode=WAL;")
        conn.row_factory = sqlite3.Row
        return conn

    def _init_db(self) -> None:
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        with self._get_connection() as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS audit_events (
                    id TEXT PRIMARY KEY,
                    ts TEXT NOT NULL,
                    task_id TEXT NOT NULL,
                    type TEXT NOT NULL,
                    actor TEXT NOT NULL,
                    payload_json TEXT NOT NULL,
                    config_version INTEGER NOT NULL,
                    model_versions TEXT NOT NULL,
                    prev_hash TEXT NOT NULL,
                    hash TEXT NOT NULL
                );
                """
            )
            conn.execute("CREATE INDEX IF NOT EXISTS idx_audit_task ON audit_events(task_id);")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_audit_type ON audit_events(type);")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_audit_ts ON audit_events(ts);")
            conn.commit()

    def get_last_hash(self) -> str:
        with self._get_connection() as conn:
            cursor = conn.execute("SELECT hash FROM audit_events ORDER BY rowid DESC LIMIT 1;")
            row = cursor.fetchone()
            if row:
                return str(row["hash"])
        return GENESIS_HASH

    def _compute_hash(self, prev_hash: str, row_dict: dict[str, Any]) -> str:
        # hash = sha256(prev_hash || canonical_json(row_without_hash))
        canonical = canonical_json(row_dict)
        data = f"{prev_hash}{canonical}".encode("utf-8")
        return hashlib.sha256(data).hexdigest()

    def log_event(
        self,
        task_id: str,
        event_type: str,
        actor: str,
        payload: dict[str, Any],
        config_version: int = 1,
        model_versions: dict[str, str] | None = None,
    ) -> AuditEvent:
        """
        Appends an event to the hash chain.
        Fails closed: any error raises RuntimeError to halt action.
        """
        try:
            now = datetime.now(timezone.utc)
            event_id = f"evt-{uuid.uuid4().hex}"
            prev_hash = self.get_last_hash()

            sanitized = sanitize_payload(payload)
            payload_str = canonical_json(sanitized)
            models_str = canonical_json(model_versions or {})

            row_data = {
                "id": event_id,
                "ts": now.isoformat(),
                "task_id": task_id,
                "type": event_type,
                "actor": actor,
                "payload_json": sanitized,
                "config_version": config_version,
                "model_versions": model_versions or {},
            }

            event_hash = self._compute_hash(prev_hash, row_data)

            with self._get_connection() as conn:
                conn.execute(
                    """
                    INSERT INTO audit_events
                    (id, ts, task_id, type, actor, payload_json, config_version, model_versions, prev_hash, hash)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?);
                    """,
                    (
                        event_id,
                        now.isoformat(),
                        task_id,
                        event_type,
                        actor,
                        payload_str,
                        config_version,
                        models_str,
                        prev_hash,
                        event_hash,
                    ),
                )
                conn.commit()

            return AuditEvent(
                id=event_id,
                ts=now,
                task_id=task_id,
                type=event_type,
                actor=actor,
                payload_json=sanitized,
                config_version=config_version,
                model_versions=model_versions or {},
                prev_hash=prev_hash,
                hash=event_hash,
            )
        except Exception as e:
            logger.error(f"Audit log failure: {e}", exc_info=True)
            raise RuntimeError(f"Audit logging failed: {e}") from e

    def verify_chain(self) -> AuditVerifyResponse:
        """
        Verifies the cryptographic integrity of the entire audit hash chain.
        Detects tampering, deletions, or insertions.
        """
        with self._get_connection() as conn:
            cursor = conn.execute("SELECT * FROM audit_events ORDER BY rowid ASC;")
            rows = cursor.fetchall()

        if not rows:
            return AuditVerifyResponse(valid=True, chain_length=0, message="Audit log is empty (valid)")

        expected_prev_hash = GENESIS_HASH
        for row in rows:
            row_dict = {
                "id": row["id"],
                "ts": row["ts"],
                "task_id": row["task_id"],
                "type": row["type"],
                "actor": row["actor"],
                "payload_json": json.loads(row["payload_json"]),
                "config_version": row["config_version"],
                "model_versions": json.loads(row["model_versions"]),
            }

            if row["prev_hash"] != expected_prev_hash:
                return AuditVerifyResponse(
                    valid=False,
                    chain_length=len(rows),
                    tampered_event_id=row["id"],
                    message=f"Hash chain broken at event {row['id']}: expected prev_hash {expected_prev_hash}, found {row['prev_hash']}",
                )

            computed_hash = self._compute_hash(expected_prev_hash, row_dict)
            if row["hash"] != computed_hash:
                return AuditVerifyResponse(
                    valid=False,
                    chain_length=len(rows),
                    tampered_event_id=row["id"],
                    message=f"Tampered row content at event {row['id']}: computed {computed_hash}, stored {row['hash']}",
                )

            expected_prev_hash = row["hash"]

        return AuditVerifyResponse(
            valid=True,
            chain_length=len(rows),
            message=f"Audit chain intact and verified across {len(rows)} events",
        )

    def query(
        self,
        task_id: str | None = None,
        event_type: str | None = None,
        limit: int = 100,
        offset: int = 0,
    ) -> list[AuditEvent]:
        query = "SELECT * FROM audit_events WHERE 1=1"
        params: list[Any] = []
        if task_id:
            query += " AND task_id = ?"
            params.append(task_id)
        if event_type:
            query += " AND type = ?"
            params.append(event_type)
        query += " ORDER BY rowid DESC LIMIT ? OFFSET ?"
        params.extend([limit, offset])

        results: list[AuditEvent] = []
        with self._get_connection() as conn:
            cursor = conn.execute(query, params)
            for row in cursor.fetchall():
                results.append(
                    AuditEvent(
                        id=row["id"],
                        ts=datetime.fromisoformat(row["ts"]),
                        task_id=row["task_id"],
                        type=row["type"],
                        actor=row["actor"],
                        payload_json=json.loads(row["payload_json"]),
                        config_version=row["config_version"],
                        model_versions=json.loads(row["model_versions"]),
                        prev_hash=row["prev_hash"],
                        hash=row["hash"],
                    )
                )
        return results
