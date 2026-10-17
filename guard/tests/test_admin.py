"""
Tests for Guard Admin API (Four-eyes, Kill switch, Audit verify).
"""

from fastapi.testclient import TestClient
from service.main import app, SERVICE_TOKEN

client = TestClient(app)
AUTH_HEADERS = {"Authorization": f"Bearer {SERVICE_TOKEN}"}


def test_four_eyes_config_proposal_enforcement():
    # 1. Admin A proposes a posture change
    prop_resp = client.post(
        "/admin/v1/config/proposals",
        json={
            "proposed_by": "admin-alice",
            "changes": {"minimum_detector_posture": "tier1_ok_readonly"},
            "justification": "Emergency degradation tolerance test",
        },
        headers=AUTH_HEADERS,
    )
    assert prop_resp.status_code == 200
    prop_data = prop_resp.json()
    prop_id = prop_data["proposal_id"]
    assert prop_data["status"] == "pending"

    # 2. Admin A attempts to approve their own proposal -> REJECTED (Four-Eyes violation!)
    self_approve_resp = client.post(
        f"/admin/v1/config/proposals/{prop_id}/approve",
        headers={**AUTH_HEADERS, "X-Admin-User-Id": "admin-alice"},
    )
    assert self_approve_resp.status_code == 400
    assert "Four-eyes rule violation" in self_approve_resp.json()["detail"]

    # 3. Admin B approves the proposal -> SUCCESS!
    second_admin_resp = client.post(
        f"/admin/v1/config/proposals/{prop_id}/approve",
        headers={**AUTH_HEADERS, "X-Admin-User-Id": "admin-bob"},
    )
    assert second_admin_resp.status_code == 200
    approved_data = second_admin_resp.json()
    assert approved_data["status"] == "approved"
    assert approved_data["approved_by"] == "admin-bob"

    # Check updated active config
    config_resp = client.get("/admin/v1/config", headers=AUTH_HEADERS)
    assert config_resp.json()["minimum_detector_posture"] == "tier1_ok_readonly"


def test_kill_switch_immediate_effect():
    # 0. Build an active task policy allowing gmail.send
    client.post(
        "/v1/policy",
        json={
            "task_id": "t-ks-1",
            "user_id": "u-1",
            "user_role": "user",
            "user_request": "Email the report to alice@corp.com",
            "available_tools": ["gmail.send", "gmail.read"],
        },
        headers=AUTH_HEADERS,
    )

    # 1. Activate kill switch for all write tools
    ks_resp = client.post(
        "/admin/v1/kill-switch",
        json={"scope": "all_write_tools", "target": None, "enabled": True},
        headers=AUTH_HEADERS,
    )
    assert ks_resp.status_code == 200
    health_data = ks_resp.json()
    assert health_data["kill_switch"]["all_write_tools"] is True


    # 2. Verify that check-action on a write tool is immediately DENIED with KILL_SWITCH
    check_resp = client.post(
        "/v1/check-action",
        json={
            "task_id": "t-ks-1",
            "call_id": "c-1",
            "tool": "gmail.send",
            "args": {"to": "alice@corp.com", "subject": "Test", "body": "Body"},
            "arg_provenance": {},
            "read_only": False,
        },
        headers=AUTH_HEADERS,
    )
    assert check_resp.status_code == 200
    data = check_resp.json()
    assert data["decision"] == "DENY"
    assert "KILL_SWITCH" in data["reasons"]

    # 3. Deactivate kill switch
    client.post(
        "/admin/v1/kill-switch",
        json={"scope": "all_write_tools", "target": None, "enabled": False},
        headers=AUTH_HEADERS,
    )


def test_admin_audit_verification():
    verify_resp = client.get("/admin/v1/audit/verify", headers=AUTH_HEADERS)
    assert verify_resp.status_code == 200
    assert verify_resp.json()["valid"] is True


# --- proposals list / reject ------------------------------------------------------------------

def _propose(by="admin-alice", changes=None):
    r = client.post(
        "/admin/v1/config/proposals",
        json={"proposed_by": by, "changes": changes or {"block_threshold": 0.9}, "justification": "tune"},
        headers=AUTH_HEADERS,
    )
    assert r.status_code == 200
    return r.json()["proposal_id"]


def test_list_proposals_filters_by_status_and_newest_first():
    first = _propose()
    second = _propose()
    all_ids = [p["proposal_id"] for p in client.get("/admin/v1/config/proposals", headers=AUTH_HEADERS).json()]
    assert all_ids.index(second) < all_ids.index(first)

    pending = client.get("/admin/v1/config/proposals?status=pending", headers=AUTH_HEADERS).json()
    assert {first, second} <= {p["proposal_id"] for p in pending}
    assert all(p["status"] == "pending" for p in pending)
    assert client.get("/admin/v1/config/proposals?status=bogus", headers=AUTH_HEADERS).status_code == 422


def test_reject_proposal_applies_nothing_and_cannot_be_approved_later():
    cfg_before = client.get("/admin/v1/config", headers=AUTH_HEADERS).json()["version"]
    pid = _propose(changes={"failure_mode": "tier1_only_warning"})

    rej = client.post(f"/admin/v1/config/proposals/{pid}/reject", headers={**AUTH_HEADERS, "X-Admin-User-Id": "admin-bob"})
    assert rej.status_code == 200
    assert rej.json()["status"] == "rejected"
    assert client.get("/admin/v1/config", headers=AUTH_HEADERS).json()["version"] == cfg_before

    again = client.post(f"/admin/v1/config/proposals/{pid}/approve", headers={**AUTH_HEADERS, "X-Admin-User-Id": "admin-bob"})
    assert again.status_code == 400
    assert "rejected" in again.json()["detail"]


def test_proposer_may_withdraw_own_proposal_and_unknown_is_404():
    pid = _propose(by="admin-alice")
    assert client.post(f"/admin/v1/config/proposals/{pid}/reject", headers={**AUTH_HEADERS, "X-Admin-User-Id": "admin-alice"}).status_code == 200
    assert client.post("/admin/v1/config/proposals/nope/reject", headers={**AUTH_HEADERS, "X-Admin-User-Id": "x"}).status_code == 404


# --- review queue is populated by flagged scans -------------------------------------------------

def _scan(task_id, text):
    return client.post(
        "/v1/scan",
        headers=AUTH_HEADERS,
        json={
            "task_id": task_id, "call_id": "c-1", "tool": "gmail.read",
            "fields": [{"name": "body", "text": text, "provenance": {"source_id": "m1", "source_type": "email", "field": "body", "retrieval_path": ["c-1"], "trust": "untrusted"}}],
        },
    )


def test_flagged_scan_enqueues_review_item_without_raw_text():
    from service.main import guard_instance

    guard_instance._review_queue.clear()
    # Force a flagged disposition regardless of the detector wired in.
    orig = guard_instance._det_pipeline
    from contracts.models import DetSummary, SanitizedField, ScanResponse

    class Flagged:
        def scan(self, req):
            return ScanResponse(
                disposition="quarantined",
                fields=[SanitizedField(name="body", text="[REMOVED] SECRET-RAW-MARKER", sentences_total=2, sentences_removed=1, quarantined=True)],
                det_summary=DetSummary(t1_signals=[], t2_max_score=0.99, t3_used=False, t3_verdict=None, latency_ms={}),
                tier2_available=True,
                event_id="e-1",
            )

    guard_instance._det_pipeline = Flagged()
    try:
        assert _scan("t-rq-1", "whatever").status_code == 200
    finally:
        guard_instance._det_pipeline = orig

    items = client.get("/admin/v1/review-queue", headers=AUTH_HEADERS).json()
    assert len(items) == 1
    item = items[0]
    assert item["task_id"] == "t-rq-1" and item["tool"] == "gmail.read" and item["disposition"] == "quarantined"
    assert item["fields"] == [{"name": "body", "sentences_removed": 1, "quarantined": True}]
    assert "SECRET-RAW-MARKER" not in str(item)

    # A decision is recorded on that same item and never grants authority.
    dec = client.post(
        f"/admin/v1/review-queue/{item['id']}/decision",
        headers=AUTH_HEADERS,
        json={"reviewer_id": "admin-alice", "decision": "rejected", "notes": "attack"},
    )
    assert dec.status_code == 200
    assert client.get("/admin/v1/review-queue", headers=AUTH_HEADERS).json()[0]["decision"] == "rejected"


def test_clean_scan_does_not_enqueue():
    from service.main import guard_instance

    guard_instance._review_queue.clear()
    _scan("t-rq-2", "Invoice #1 is due Friday.")
    assert client.get("/admin/v1/review-queue", headers=AUTH_HEADERS).json() == []


# --- backend-originated audit events -----------------------------------------------------------------

def test_record_event_is_allowlisted_and_lands_in_verified_chain():
    ok = client.post(
        "/v1/audit/events", headers=AUTH_HEADERS,
        json={"task_id": "user-1", "event_type": "files.uploaded", "actor": "user:u1", "payload": {"path": "a.txt", "size": 3}},
    )
    assert ok.status_code == 200 and ok.json()["event_id"]
    rows = client.get("/admin/v1/audit?event_type=files.uploaded", headers=AUTH_HEADERS).json()
    assert rows and rows[0]["payload_json"]["path"] == "a.txt"
    assert client.get("/admin/v1/audit/verify", headers=AUTH_HEADERS).json()["valid"] is True

    forged = client.post(
        "/v1/audit/events", headers=AUTH_HEADERS,
        json={"task_id": "t", "event_type": "gateway.decision", "actor": "guard", "payload": {}},
    )
    assert forged.status_code == 400
    assert client.post("/v1/audit/events", json={"task_id": "t", "event_type": "files.uploaded", "actor": "a"}).status_code == 401
