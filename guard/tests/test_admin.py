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
