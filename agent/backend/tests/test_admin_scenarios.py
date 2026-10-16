"""S13 (four-eyes posture floor) and S14 (audit tamper) driven through /api/admin/* (JWT identity)."""

from __future__ import annotations

import copy
import sqlite3

import httpx
import pytest

from app.api import admin as admin_api
from app.auth.security import hash_password
from app.config import settings
from app.db.database import async_session_factory
from app.db.models import User

from admin_api import routes as admin_routes
from eva_guard.audit import AuditLogger
from service.main import app as guard_app, guard_instance

pytestmark = pytest.mark.asyncio

ADMIN2_EMAIL, ADMIN2_PASSWORD = "admin2@eva.local", "AdminTwoPassword123!"


@pytest.fixture
def admin_proxy(tmp_path):
    """Proxy -> in-process guard service, with an isolated audit DB and restored admin config."""
    saved_cfg = copy.deepcopy(admin_routes._active_config)
    saved_audit = guard_instance._audit
    guard_instance._audit = AuditLogger(db_path=tmp_path / "audit.db")
    admin_api.set_admin_transport(httpx.ASGITransport(app=guard_app))
    yield guard_instance._audit
    admin_api.set_admin_transport(None)
    guard_instance._audit = saved_audit
    admin_routes._active_config.clear()
    admin_routes._active_config.update(saved_cfg)
    admin_routes._proposals.clear()


async def _login(client, email, password) -> dict:
    r = await client.post("/api/auth/login", json={"email": email, "password": password})
    assert r.status_code == 200, r.text
    return {"Authorization": f"Bearer {r.json()['access_token']}"}


async def _second_admin(client) -> dict:
    async with async_session_factory() as s:
        s.add(User(email=ADMIN2_EMAIL, hashed_password=hash_password(ADMIN2_PASSWORD), role="admin"))
        await s.commit()
    return await _login(client, ADMIN2_EMAIL, ADMIN2_PASSWORD)


LOWER_FLOOR = {"changes": {"minimum_detector_posture": "tier1_ok_readonly"}, "justification": "S13"}


async def test_s13_posture_floor_lowering_needs_second_admin(async_client, admin_proxy):
    a1 = await _login(async_client, settings.SEED_ADMIN_EMAIL, settings.SEED_ADMIN_PASSWORD)
    a2 = await _second_admin(async_client)
    before = (await async_client.get("/api/admin/config", headers=a1)).json()["minimum_detector_posture"]

    # Admin 1 proposes. A spoofed proposed_by in the body must be ignored (identity is the JWT).
    r = await async_client.post("/api/admin/config/proposals", headers=a1,
                                json={**LOWER_FLOOR, "proposed_by": "someone-else"})
    assert r.status_code == 200 and r.json()["status"] == "pending"
    prop = r.json()
    assert prop["proposed_by"] != "someone-else"
    pid = f"/api/admin/config/proposals/{prop['proposal_id']}/approve"

    # The proposer cannot approve their own change, nor spoof another approver id.
    own = await async_client.post(pid, headers={**a1, "X-Admin-User-Id": "admin-bob"})
    assert own.status_code == 400 and "Four-eyes" in own.text
    cfg = (await async_client.get("/api/admin/config", headers=a1)).json()
    assert cfg["minimum_detector_posture"] == before, "floor unchanged until a second admin approves"

    # Non-admins cannot approve at all.
    user_h = await _login(async_client, settings.SEED_USER_EMAIL, settings.SEED_USER_PASSWORD)
    assert (await async_client.post(pid, headers=user_h)).status_code == 403

    # A different admin approves -> applied.
    ok = await async_client.post(pid, headers=a2)
    assert ok.status_code == 200 and ok.json()["status"] == "approved"
    cfg = (await async_client.get("/api/admin/config", headers=a1)).json()
    assert cfg["minimum_detector_posture"] == "tier1_ok_readonly"
    assert (await async_client.get("/api/admin/audit/verify", headers=a1)).json()["valid"] is True


async def test_s14_audit_tamper_detected_via_admin_api(async_client, admin_proxy):
    audit = admin_proxy
    a1 = await _login(async_client, settings.SEED_ADMIN_EMAIL, settings.SEED_ADMIN_PASSWORD)
    for i in range(3):
        audit.log_event("t-s14", "gateway.decision", "tool:gmail.send", {"decision": "DENY", "n": i})

    ok = (await async_client.get("/api/admin/audit/verify", headers=a1)).json()
    assert ok["valid"] is True and ok["chain_length"] == 3

    conn = sqlite3.connect(str(audit.db_path))
    conn.execute("UPDATE audit_events SET payload_json = ? WHERE rowid = 2", ('{"decision": "ALLOW", "n": 1}',))
    conn.commit()
    conn.close()

    bad = (await async_client.get("/api/admin/audit/verify", headers=a1)).json()
    assert bad["valid"] is False and bad["tampered_event_id"]
