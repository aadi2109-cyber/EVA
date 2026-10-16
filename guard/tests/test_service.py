"""
Tests for Guard HTTP Service endpoints and authentication.
"""

from fastapi.testclient import TestClient
from service.main import app, SERVICE_TOKEN

client = TestClient(app)
AUTH_HEADERS = {"Authorization": f"Bearer {SERVICE_TOKEN}"}


def test_service_health():
    resp = client.get("/v1/health")
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] in ("ok", "degraded")
    assert data["contract_version"] == "0.1.0"


def test_service_auth_required():
    # Calling policy endpoint without token -> 401
    resp = client.post(
        "/v1/policy",
        json={
            "task_id": "t-srv-1",
            "user_id": "u-1",
            "user_role": "user",
            "user_request": "summarize emails",
            "available_tools": ["gmail.read"],
        },
    )
    assert resp.status_code == 401


def test_service_policy_and_check_action():
    # 1. Build policy
    pol_resp = client.post(
        "/v1/policy",
        json={
            "task_id": "t-srv-2",
            "user_id": "u-1",
            "user_role": "user",
            "user_request": "summarize emails and invoices",
            "available_tools": ["gmail.search", "gmail.read"],
        },
        headers=AUTH_HEADERS,
    )
    assert pol_resp.status_code == 200
    assert "gmail.read" in pol_resp.json()["allowed_operations"]

    # 2. Check action for allowed read
    check_resp = client.post(
        "/v1/check-action",
        json={
            "task_id": "t-srv-2",
            "call_id": "c-1",
            "tool": "gmail.read",
            "args": {"message_id": "123"},
            "arg_provenance": {},
            "read_only": True,
        },
        headers=AUTH_HEADERS,
    )
    assert check_resp.status_code == 200
    assert check_resp.json()["decision"] == "ALLOW"


def test_service_metrics():
    resp = client.get("/metrics")
    assert resp.status_code == 200
    assert "guard_decisions_total" in resp.text
