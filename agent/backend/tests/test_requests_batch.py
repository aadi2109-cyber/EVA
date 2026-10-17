"""Backend side of the FE->BE requests: step completion, scripted provider, reviewer identity,
upload audit (fail closed), and request-size cap."""

from __future__ import annotations

import httpx
import pytest
from sqlalchemy import select

from app.agent.orchestrator import TaskOrchestrator
from app.api import admin as admin_api
from app.api import files as files_api
from app.config import settings
from app.db.database import async_session_factory
from app.db.models import TaskEvent
from app.guard_client.base import GuardDownError
from app.guard_client.factory import set_guard_client
from app.model.factory import default_model_provider, scripted_demo_provider
from app.model.scripted import ScriptedProvider

from admin_api import routes as admin_routes
from service.main import app as guard_app, guard_instance

pytestmark = pytest.mark.asyncio


async def _events(task_id: str) -> list[TaskEvent]:
    async with async_session_factory() as s:
        return list((await s.execute(select(TaskEvent).where(TaskEvent.task_id == task_id).order_by(TaskEvent.seq))).scalars())


def _steps(evs):
    return [(e.payload_json["index"], e.payload_json["status"]) for e in evs if e.event_type == "plan.step"]


# ---- #3 plan.step completion --------------------------------------------------------------------

async def test_each_plan_step_is_completed_explicitly(stub_guard_client):
    sp = ScriptedProvider()
    sp.add_tool_call("gmail.search", {"query": "invoices"})
    sp.add_final_text("done")
    orch = TaskOrchestrator("ps-ok", "user-1", "user", "Find invoices", model_provider=sp, guard_client=stub_guard_client)
    assert (await orch.run())["status"] == "completed"

    evs = await _events("ps-ok")
    assert _steps(evs) == [(0, "running"), (0, "completed"), (1, "running"), (1, "completed")]
    # each step is closed before the terminal event
    types = [e.event_type for e in evs]
    assert types.index("task.completed") > max(i for i, e in enumerate(evs) if e.event_type == "plan.step")


async def test_a_step_cut_short_by_a_hold_is_reported_failed(stub_guard_client):
    class ScanDown:
        def __getattr__(self, name):
            return getattr(stub_guard_client, name)

        async def scan_tool_result(self, req):
            raise GuardDownError("scan down")

    sp = ScriptedProvider()
    sp.add_tool_call("gmail.search", {"query": "x"})
    orch = TaskOrchestrator("ps-held", "user-1", "user", "Find x", model_provider=sp, guard_client=ScanDown())
    assert (await orch.run())["status"] == "held"

    evs = await _events("ps-held")
    assert _steps(evs) == [(0, "running"), (0, "failed")]
    assert evs[-1].event_type == "task.held"


# ---- #1 scripted model provider -----------------------------------------------------------------------

async def test_scripted_provider_selected_by_setting(monkeypatch):
    monkeypatch.setattr(settings, "MODEL_PROVIDER", "scripted")
    assert isinstance(default_model_provider("Summarize my invoices"), ScriptedProvider)
    monkeypatch.setattr(settings, "MODEL_PROVIDER", "ollama")
    assert not isinstance(default_model_provider("Summarize my invoices"), ScriptedProvider)


@pytest.mark.parametrize(
    "request_text, first_tool",
    [("Summarize my emails and list pending invoices", "gmail.search"), ("Email the report to bob@corp.com", "gmail.send"), ("anything else", "gmail.send")],
)
async def test_demo_scripts_cover_s1_s4_s2(request_text, first_tool):
    sp = scripted_demo_provider(request_text)
    events = [e async for e in sp.step([])]
    assert events[0].tool_name == first_tool


def test_scripted_provider_is_refused_in_prod():
    from app.config import Settings

    with pytest.raises(ValueError, match="scripted"):
        Settings(APP_ENV="prod", MODEL_PROVIDER="scripted")


# ---- #7 reviewer identity comes from the JWT --------------------------------------------------------------

async def test_review_decision_reviewer_id_is_overwritten_from_jwt(async_client, monkeypatch):
    monkeypatch.setattr(settings, "GUARD_TRANSPORT", "http")  # the proxy refuses in-process mode
    admin_api.set_admin_transport(httpx.ASGITransport(app=guard_app))
    try:
        login = await async_client.post("/api/auth/login", json={"email": settings.SEED_ADMIN_EMAIL, "password": settings.SEED_ADMIN_PASSWORD})
        h = {"Authorization": f"Bearer {login.json()['access_token']}"}
        me = (await async_client.get("/api/me", headers=h)).json()["id"]

        r = await async_client.post(
            "/api/admin/review-queue/item-xyz/decision",
            headers=h,
            json={"reviewer_id": "spoofed-admin", "decision": "investigate", "notes": "n"},
        )
        assert r.status_code == 200
        assert r.json()["item"]["reviewer_id"] == me
    finally:
        admin_api.set_admin_transport(None)
        guard_instance._review_queue.pop("item-xyz", None)


# ---- upload: audit fail-closed, request size cap -----------------------------------------------------------

@pytest.fixture
def ws(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "WORKSPACE_ROOT", str(tmp_path / "ws"))
    return tmp_path / "ws"


async def _user(client):
    r = await client.post("/api/auth/login", json={"email": settings.SEED_USER_EMAIL, "password": settings.SEED_USER_PASSWORD})
    return {"Authorization": f"Bearer {r.json()['access_token']}"}


async def test_upload_is_recorded_in_guard_audit_chain(async_client, ws):
    calls = []

    class Rec:
        async def record_event(self, **kw):
            calls.append(kw)
            return "evt-1"

    set_guard_client(Rec())
    try:
        h = await _user(async_client)
        r = await async_client.post("/api/files/upload", files={"file": ("a.txt", b"hello", "text/plain")}, headers=h)
    finally:
        set_guard_client(None)
    assert r.status_code == 201
    assert calls[0]["event_type"] == "files.uploaded"
    assert calls[0]["payload"]["path"] == "a.txt" and calls[0]["payload"]["size"] == 5
    assert len(calls[0]["payload"]["sha256"]) == 64


async def test_upload_is_rolled_back_when_audit_cannot_be_written(async_client, ws):
    class Down:
        async def record_event(self, **kw):
            raise GuardDownError("guard down")

    set_guard_client(Down())
    try:
        h = await _user(async_client)
        r = await async_client.post("/api/files/upload", files={"file": ("a.txt", b"hello", "text/plain")}, headers=h)
    finally:
        set_guard_client(None)
    assert r.status_code == 503
    assert not list(ws.rglob("a.txt")), "file must not remain when the audit entry failed"


async def test_oversize_request_is_rejected_before_buffering(async_client, ws):
    h = await _user(async_client)
    big = b"x" * (files_api.MAX_UPLOAD_BYTES + 200 * 1024)
    r = await async_client.post("/api/files/upload", files={"file": ("big.bin", big)}, headers=h)
    assert r.status_code == 413
    assert r.json()["detail"] == "Request body too large"


async def test_chunked_oversize_body_without_content_length_is_rejected(async_client, ws):
    h = await _user(async_client)

    async def gen():  # valid multipart, streamed with no Content-Length
        yield b'--zz\r\nContent-Disposition: form-data; name="file"; filename="big.bin"\r\n\r\n'
        for _ in range(40):
            yield b"x" * 32 * 1024  # 1.25 MB of file data
        yield b"\r\n--zz--\r\n"

    r = await async_client.post("/api/files/upload", content=gen(), headers={**h, "Content-Type": "multipart/form-data; boundary=zz"})
    assert r.status_code == 413
    assert r.json()["detail"] == "Request body too large"  # the middleware, not the route's per-file check
    assert not list(ws.rglob("big.bin"))


async def test_upload_limit_middleware_only_applies_to_the_upload_path(async_client):
    r = await async_client.post("/api/auth/login", json={"email": settings.SEED_USER_EMAIL, "password": "x" * 300_000})
    assert r.status_code == 401  # not 413
