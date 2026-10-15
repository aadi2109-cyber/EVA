"""
Tests for Hash-Chained Audit Log and Tamper Detection.
"""

import sqlite3
import pytest
from eva_guard.audit import AuditLogger, GENESIS_HASH, redact_text


def test_redact_text():
    raw = "Here is my secret password: MySecretPassword123 and Bearer abc.def.ghi and a very long sentence that keeps going and going and going and going and going to exceed 120 characters easily."
    redacted = redact_text(raw)
    assert "[REDACTED_SECRET]" in redacted
    assert "MySecretPassword123" not in redacted
    assert len(redacted) <= 120


def test_audit_hash_chain_integrity(tmp_path):
    db_file = tmp_path / "test_guard.db"
    audit = AuditLogger(db_path=db_file)

    # 1. Empty chain is valid
    init_ver = audit.verify_chain()
    assert init_ver.valid is True
    assert init_ver.chain_length == 0

    # 2. Append events
    evt1 = audit.log_event(
        task_id="t-1",
        event_type="policy.built",
        actor="user:1",
        payload={"allowed_operations": ["gmail.read"]},
    )
    assert evt1.prev_hash == GENESIS_HASH

    evt2 = audit.log_event(
        task_id="t-1",
        event_type="gateway.decision",
        actor="tool:gmail.read",
        payload={"decision": "ALLOW"},
    )
    assert evt2.prev_hash == evt1.hash

    evt3 = audit.log_event(
        task_id="t-1",
        event_type="state.verified",
        actor="guard.verifier",
        payload={"passed": True},
    )
    assert evt3.prev_hash == evt2.hash

    # Verify intact chain
    ver_intact = audit.verify_chain()
    assert ver_intact.valid is True
    assert ver_intact.chain_length == 3


def test_audit_tamper_detection(tmp_path):
    db_file = tmp_path / "test_tamper.db"
    audit = AuditLogger(db_path=db_file)

    evt1 = audit.log_event("t-1", "policy.built", "user:1", {"op": "read"})
    evt2 = audit.log_event("t-1", "gateway.decision", "tool:gmail.send", {"decision": "DENY"})
    evt3 = audit.log_event("t-1", "tool.executed", "system", {"status": "ok"})

    # Tamper with row 2 payload directly in SQLite
    conn = sqlite3.connect(str(db_file))
    conn.execute(
        "UPDATE audit_events SET payload_json = '{\"decision\": \"ALLOW\"}' WHERE id = ?;",
        (evt2.id,),
    )
    conn.commit()
    conn.close()

    # Verify chain must detect tampering!
    ver_tampered = audit.verify_chain()
    assert ver_tampered.valid is False
    assert ver_tampered.tampered_event_id == evt2.id
    assert "Tampered row content" in ver_tampered.message
