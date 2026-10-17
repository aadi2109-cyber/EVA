"""CP-A: the backend is wired to the REAL guard; it never silently degrades to the test-only StubGuard."""

from __future__ import annotations

import pytest

from app.guard_client.base import GuardError
from app.guard_client.factory import get_guard_client, set_guard_client
from app.guard_client.in_process import InProcessGuardClient
from contracts.models import CheckActionRequest

pytestmark = pytest.mark.asyncio


async def test_default_in_process_client_is_the_real_guard():
    c = InProcessGuardClient()
    assert c.implementation == "eva_guard.api.Guard"
    assert type(c._guard).__name__ == "Guard"  # not StubGuard


async def test_health_reports_which_guard_is_active(async_client):
    set_guard_client(None)  # factory default, no test stub
    try:
        body = (await async_client.get("/api/health")).json()
        assert body["backend"]["guard_impl"] == "eva_guard.api.Guard"
        assert body["guard"]["status"] in ("ok", "degraded")
    finally:
        set_guard_client(None)


async def test_guard_import_failure_fails_closed_never_falls_back_to_stub(monkeypatch, async_client):
    import eva_guard.api as api

    def boom(*a, **k):
        raise ImportError("simulated: missing dependency")

    monkeypatch.setattr(api, "Guard", boom)
    c = InProcessGuardClient()
    assert c.implementation == "unavailable"
    assert "StubGuard" not in c.implementation
    req = CheckActionRequest(task_id="t", call_id="c", tool="gmail.send", args={"to": "a@b.c"}, arg_provenance={}, read_only=False)
    with pytest.raises(GuardError, match="Guard unavailable"):
        await c.check_action(req)
    with pytest.raises(GuardError):
        await c.health()

    set_guard_client(c)
    try:
        body = (await async_client.get("/api/health")).json()
        assert body["backend"]["guard_impl"] == "unavailable"
        assert body["guard"]["status"] == "down"
    finally:
        set_guard_client(None)
