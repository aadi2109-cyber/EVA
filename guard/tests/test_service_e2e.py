"""HTTP-mode end to end through the real FastAPI app (what BE's HttpGuardClient calls)."""
from fastapi.testclient import TestClient

import service.main as svc

H = {"Authorization": f"Bearer {svc.SERVICE_TOKEN}"}
client = TestClient(svc.app, raise_server_exceptions=False)


def _post(path, body, headers=H):
    return client.post(path, json=body, headers=headers)


def test_full_send_flow_with_single_use_approval():
    tid = "e2e-send"
    assert _post("/v1/policy", {"task_id": tid, "user_id": "u", "user_role": "user",
                                "user_request": "Email the report to bob@corp.com",
                                "available_tools": ["gmail.send", "gmail.read"]}).status_code == 200
    act = {"task_id": tid, "call_id": "c1", "tool": "gmail.send", "read_only": False,
           "args": {"to": "bob@corp.com", "subject": "R", "body": "b"},
           "arg_provenance": {"to": {"source_id": "u", "source_type": "user_request", "trust": "user"}}}
    first = _post("/v1/check-action", act).json()
    assert first["decision"] == "REQUIRE_APPROVAL"
    aid = first["approval"]["approval_id"]
    assert _post(f"/v1/approvals/{aid}", {"user_id": "u", "approved": True}).json()["status"] == "approved"
    assert _post("/v1/check-action", {**act, "call_id": "c2", "approval_id": aid}).json()["decision"] == "ALLOW"
    assert _post("/v1/check-action", {**act, "call_id": "c3", "approval_id": aid}).json()["decision"] == "DENY"  # replay
    tampered = {**act, "call_id": "c4", "args": {**act["args"], "to": "eve@evil.com"}, "approval_id": aid}
    assert _post("/v1/check-action", tampered).json()["decision"] == "DENY"


def test_hijacked_send_denied_over_http():
    tid = "e2e-hijack"
    _post("/v1/policy", {"task_id": tid, "user_id": "u", "user_role": "user", "user_request": "Summarize my emails",
                         "available_tools": ["gmail.read", "gmail.send"]})
    r = _post("/v1/check-action", {"task_id": tid, "call_id": "c", "tool": "gmail.send", "read_only": False,
                                   "args": {"to": "attacker@example.com", "subject": "x", "body": "y"}}).json()
    assert r["decision"] == "DENY"


def test_bad_token_and_missing_token_rejected():
    assert client.post("/v1/check-action", json={}, headers={"Authorization": "Bearer wrong"}).status_code == 401
    assert client.post("/v1/check-action", json={}).status_code == 401


def test_oversized_body_rejected_413():
    big = {"task_id": "t", "call_id": "c", "tool": "gmail.read", "fields": [], "pad": "x" * (svc.MAX_BODY_BYTES + 10)}
    r = client.post("/v1/scan", content=__import__("json").dumps(big), headers={**H, "Content-Type": "application/json"})
    assert r.status_code == 413 and r.json()["error"] == "REQUEST_TOO_LARGE"


def test_malformed_body_is_4xx_not_stack_trace():
    r = client.post("/v1/check-action", content="not json", headers={**H, "Content-Type": "application/json"})
    assert r.status_code in (400, 422)
    assert "Traceback" not in r.text


def test_internal_error_does_not_leak(monkeypatch):
    def boom(*a, **k): raise RuntimeError("secret internal path /etc/x")
    monkeypatch.setattr(svc.guard_instance, "check_action", boom)
    r = _post("/v1/check-action", {"task_id": "t", "call_id": "c", "tool": "gmail.read", "args": {"message_id": "1"}, "read_only": True})
    assert r.status_code == 500 and "secret" not in r.text and r.json()["error"] == "GUARD_ERROR"
