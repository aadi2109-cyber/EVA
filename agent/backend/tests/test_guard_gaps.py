"""Known guard-side gaps found in live integration. Strict xfail: when SEC-2 ships the fix the test
XPASSes, fails the suite, and the marker must be deleted (see coordination/requests/BE-to-SEC2-02.md)."""

from __future__ import annotations

import asyncio
import uuid
from datetime import datetime, timezone

import httpx
import pytest

from app.agent.orchestrator import TaskOrchestrator
from app.api import admin as admin_api
from app.guard_client.factory import get_guard_client, set_guard_client
from app.guard_client.in_process import InProcessGuardClient
from app.model.scripted import ScriptedProvider
from contracts.models import SubmitApprovalRequest

from eva_guard.api import Guard
from service.main import app as guard_app

pytestmark = pytest.mark.asyncio
APPROVAL_TTL_S = 10 * 60


@pytest.mark.xfail(strict=True, reason="SEC-2: gateway.py builds approval expires_at from the 2h policy expiry, not the 10-min approval TTL")
async def test_approval_expires_in_ten_minutes_not_policy_lifetime():
    set_guard_client(InProcessGuardClient(guard_instance=Guard()))
    try:
        sp = ScriptedProvider()
        sp.add_tool_call("gmail.send", {"to": "bob@corp.com", "subject": "x", "body": "y"})
        sp.add_final_text("done")
        orch = TaskOrchestrator(task_id=f"exp-{uuid.uuid4().hex[:6]}", user_id="u-exp", user_role="user",
                                user_request="Email the report to bob@corp.com", model_provider=sp,
                                guard_client=get_guard_client())
        run = asyncio.create_task(orch.run())
        for _ in range(200):
            await asyncio.sleep(0.05)
            if orch.pending_approval:
                break
        appr = orch.pending_approval
        assert appr is not None
        remaining = (appr.expires_at - datetime.now(timezone.utc)).total_seconds()
        resp = await get_guard_client().submit_approval(appr.approval_id, SubmitApprovalRequest(user_id="u-exp", approved=False))
        orch.resolve_approval(appr.approval_id, resp)
        await run
        assert 0 < remaining <= APPROVAL_TTL_S + 5, f"approval lives {remaining/60:.0f} min, spec says 10"
    finally:
        set_guard_client(None)


@pytest.mark.xfail(strict=True, reason="SEC-2: contract §7 GET /admin/v1/eval/runs is not implemented in guard/admin_api")
async def test_admin_eval_runs_route_exists(async_client):
    r = await async_client.post("/api/auth/login", json={"email": "admin@eva.local", "password": "AdminPassword123!"})
    h = {"Authorization": f"Bearer {r.json()['access_token']}"}
    admin_api.set_admin_transport(httpx.ASGITransport(app=guard_app))
    try:
        res = await async_client.get("/api/admin/eval/runs", headers=h)
        assert res.status_code == 200
    finally:
        admin_api.set_admin_transport(None)
