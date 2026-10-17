"""
Scenario S4 end to end through the REST API + SSE with the real guard HTTP service
(run in-process over ASGI): approval.required -> POST /api/approvals/{id} -> re-check -> run.
Also: SSE Last-Event-ID replay and the /api/admin/* proxy.
"""

from __future__ import annotations

import asyncio
import json

import httpx
import pytest
from sqlalchemy import select

from contracts.models import CheckActionRequest, Provenance, SourceType, Trust
from app.api import admin as admin_api
from app.api import tasks as tasks_api
from app.config import settings
from app.db.database import async_session_factory
from app.db.models import TaskEvent
from app.guard_client.factory import set_guard_client
from app.guard_client.http import HttpGuardClient
from app.model.scripted import ScriptedProvider
from env.mock.state import state as mock_state

from service.main import app as guard_app

REQUEST = "Send an email to bob@corp.com with subject Hello and body Hi Bob"
SEND_ARGS = {"to": "bob@corp.com", "subject": "Hello", "body": "Hi Bob"}
TERMINAL = {"task.completed", "task.failed", "task.held", "task.cancelled"}


class RecheckDenyingClient(HttpGuardClient):
    """Real guard, except the post-approval revalidation is forced to DENY."""

    async def check_action(self, req):
        resp = await super().check_action(req)
        if req.approval_id:
            return resp.model_copy(update={"decision": "DENY", "reason_text": "forced deny"})
        return resp


@pytest.fixture
def guard_http():
    client = HttpGuardClient(base_url="http://guard.test", token="dev-guard-token",
                             transport=httpx.ASGITransport(app=guard_app))
    set_guard_client(client)
    yield client
    set_guard_client(None)


@pytest.fixture
def script(monkeypatch):
    """Patch the orchestrator spawned by POST /api/tasks to use a ScriptedProvider."""
    holder: dict = {"sp": None}
    real = tasks_api.TaskOrchestrator

    def factory(**kw):
        return real(model_provider=holder["sp"], **kw)

    monkeypatch.setattr(tasks_api, "TaskOrchestrator", factory)
    return holder


@pytest.fixture(autouse=True)
def clean_mock_state():
    before = len(mock_state.sent_messages)
    yield
    del mock_state.sent_messages[before:]


async def login(client, who="user") -> dict:
    email = settings.SEED_ADMIN_EMAIL if who == "admin" else settings.SEED_USER_EMAIL
    pw = settings.SEED_ADMIN_PASSWORD if who == "admin" else settings.SEED_USER_PASSWORD
    r = await client.post("/api/auth/login", json={"email": email, "password": pw})
    return {"Authorization": f"Bearer {r.json()['access_token']}"}


async def events(task_id: str) -> list[TaskEvent]:
    async with async_session_factory() as s:
        return list((await s.execute(
            select(TaskEvent).where(TaskEvent.task_id == task_id).order_by(TaskEvent.seq))).scalars())


async def wait_for(task_id: str, etype: str | set[str], nth: int = 1, timeout: float = 10.0) -> TaskEvent:
    types = {etype} if isinstance(etype, str) else etype
    for _ in range(int(timeout / 0.05)):
        hits = [e for e in await events(task_id) if e.event_type in types]
        if len(hits) >= nth:
            return hits[nth - 1]
        await asyncio.sleep(0.05)
    raise AssertionError(f"timeout waiting for {etype}; have {[e.event_type for e in await events(task_id)]}")


def parse_sse(text: str) -> list[dict]:
    out = []
    for block in text.strip().split("\n\n"):
        if not block.strip():
            continue
        rec = {}
        for line in block.splitlines():
            k, _, v = line.partition(": ")
            rec[k] = v
        rec["data"] = json.loads(rec["data"])
        out.append(rec)
    return out


async def start_send_task(client, headers, script_provider_holder, *, args=None, final="Email sent."):
    sp = ScriptedProvider()
    sp.add_tool_call("gmail.send", args or SEND_ARGS, call_id="call-send")
    sp.add_final_text(final)
    script_provider_holder["sp"] = sp
    r = await client.post("/api/tasks", json={"request": REQUEST}, headers=headers)
    assert r.status_code == 200
    return r.json()["task_id"]


# ---------------------------------------------------------------- S4

async def test_s4_approve_then_send(async_client, guard_http, script):
    h = await login(async_client)
    sent_before = len(mock_state.sent_messages)
    tid = await start_send_task(async_client, h, script)

    req_evt = await wait_for(tid, "approval.required")
    approval = req_evt.payload_json["approval"]
    assert approval["exact_action"]["tool"] == "gmail.send"
    assert approval["exact_action"]["args"] == SEND_ARGS
    await asyncio.sleep(0.2)
    assert len(mock_state.sent_messages) == sent_before, "must not run before approval"

    r = await async_client.post(f"/api/approvals/{approval['approval_id']}", json={"approved": True}, headers=h)
    assert r.status_code == 200 and r.json()["status"] == "approved"

    await wait_for(tid, TERMINAL)
    assert len(mock_state.sent_messages) == sent_before + 1
    assert mock_state.sent_messages[-1]["to"] == "bob@corp.com"

    # SSE over HTTP: full ordered replay for a finished task (no Last-Event-ID)
    sse = await async_client.get(f"/api/tasks/{tid}/events", headers=h)
    assert sse.status_code == 200 and sse.headers["content-type"].startswith("text/event-stream")
    msgs = parse_sse(sse.text)
    seqs = [m["data"]["seq"] for m in msgs]
    assert seqs == list(range(1, len(seqs) + 1)) and all(m["id"] == str(m["data"]["seq"]) for m in msgs)
    types = [m["event"] for m in msgs]
    for a, b in [("task.started", "guard.decision"), ("guard.decision", "approval.required"),
                 ("approval.required", "approval.resolved"), ("approval.resolved", "tool.started"),
                 ("tool.started", "tool.output"), ("tool.output", "state.verified")]:
        assert types.index(a) < types.index(b), (a, b, types)
    assert types[-1] == "task.completed" and msgs[-1]["data"]["summary"]["approvals"] == 1

    # the approval is single-use: re-submitting is refused and re-validation no longer ALLOWs
    again = await async_client.post(f"/api/approvals/{approval['approval_id']}", json={"approved": True}, headers=h)
    assert again.status_code == 409
    prov = {k: Provenance(source_id="u", source_type=SourceType.USER_REQUEST, field=k, retrieval_path=[],
                          trust=Trust.USER) for k in SEND_ARGS}
    replay = await guard_http.check_action(CheckActionRequest(
        task_id=tid, call_id="call-replay", tool="gmail.send", args=SEND_ARGS, arg_provenance=prov,
        read_only=False, approval_id=approval["approval_id"]))
    assert replay.decision != "ALLOW"


async def test_denied_approval_never_runs(async_client, guard_http, script):
    h = await login(async_client)
    sent_before = len(mock_state.sent_messages)
    tid = await start_send_task(async_client, h, script)
    appr = (await wait_for(tid, "approval.required")).payload_json["approval"]
    r = await async_client.post(f"/api/approvals/{appr['approval_id']}", json={"approved": False}, headers=h)
    assert r.json()["status"] == "denied"
    await wait_for(tid, TERMINAL)
    assert len(mock_state.sent_messages) == sent_before
    assert "tool.started" not in [e.event_type for e in await events(tid)]


async def test_runs_only_if_recheck_allows(async_client, script):
    set_guard_client(RecheckDenyingClient(base_url="http://guard.test", token="dev-guard-token",
                                          transport=httpx.ASGITransport(app=guard_app)))
    try:
        h = await login(async_client)
        sent_before = len(mock_state.sent_messages)
        tid = await start_send_task(async_client, h, script)
        appr = (await wait_for(tid, "approval.required")).payload_json["approval"]
        r = await async_client.post(f"/api/approvals/{appr['approval_id']}", json={"approved": True}, headers=h)
        assert r.json()["status"] == "approved"
        await wait_for(tid, TERMINAL)
        assert len(mock_state.sent_messages) == sent_before
        assert "tool.started" not in [e.event_type for e in await events(tid)]
    finally:
        set_guard_client(None)


async def test_edited_args_require_reapproval(async_client, guard_http, script):
    h = await login(async_client)
    sent_before = len(mock_state.sent_messages)
    tid = await start_send_task(async_client, h, script)
    appr = (await wait_for(tid, "approval.required")).payload_json["approval"]
    edited = {**SEND_ARGS, "body": "Totally different body"}

    r = await async_client.post(f"/api/approvals/{appr['approval_id']}",
                                json={"approved": True, "edited_args": edited}, headers=h)
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "re_approval_required"
    new = body["approval"]
    assert new["approval_id"] != appr["approval_id"] and new["action_hash"] != appr["action_hash"]
    assert new["exact_action"]["args"]["body"] == "Totally different body"

    # a fresh approval.required is streamed; nothing has run
    second = await wait_for(tid, "approval.required", nth=2)
    assert second.payload_json["approval"]["approval_id"] == new["approval_id"]
    await asyncio.sleep(0.2)
    assert len(mock_state.sent_messages) == sent_before

    # the old approval is void for both original and edited args
    prov = {k: Provenance(source_id="u", source_type=SourceType.USER_REQUEST, field=k, retrieval_path=[],
                          trust=Trust.USER) for k in SEND_ARGS}
    for args in (SEND_ARGS, edited):
        chk = await guard_http.check_action(CheckActionRequest(
            task_id=tid, call_id="x", tool="gmail.send", args=args, arg_provenance=prov, read_only=False,
            approval_id=appr["approval_id"]))
        assert chk.decision != "ALLOW"

    # the old approval id can no longer be answered
    dup = await async_client.post(f"/api/approvals/{appr['approval_id']}", json={"approved": True}, headers=h)
    assert dup.status_code == 409

    # deny the new one: still nothing runs and the task ends
    r2 = await async_client.post(f"/api/approvals/{new['approval_id']}", json={"approved": False}, headers=h)
    assert r2.json()["status"] == "denied"
    await wait_for(tid, TERMINAL)
    assert len(mock_state.sent_messages) == sent_before


async def test_edited_args_reapproved_then_run_with_edited_args(async_client, guard_http, script):
    """Edit -> re-approval -> approve: the EDITED action runs exactly once (never the original)."""
    h = await login(async_client)
    sent_before = len(mock_state.sent_messages)
    tid = await start_send_task(async_client, h, script)
    appr = (await wait_for(tid, "approval.required")).payload_json["approval"]
    edited = {**SEND_ARGS, "body": "Edited body approved by user"}

    r = await async_client.post(f"/api/approvals/{appr['approval_id']}",
                                json={"approved": True, "edited_args": edited}, headers=h)
    assert r.json()["status"] == "re_approval_required"
    new = r.json()["approval"]
    await wait_for(tid, "approval.required", nth=2)
    await asyncio.sleep(0.2)
    assert len(mock_state.sent_messages) == sent_before, "nothing runs before the new approval"

    r2 = await async_client.post(f"/api/approvals/{new['approval_id']}", json={"approved": True}, headers=h)
    assert r2.status_code == 200 and r2.json()["status"] == "approved"
    done = await wait_for(tid, TERMINAL)
    assert done.event_type == "task.completed"

    assert len(mock_state.sent_messages) == sent_before + 1
    sent = mock_state.sent_messages[-1]
    assert sent["to"] == "bob@corp.com" and sent["body"] == "Edited body approved by user"

    # the new approval is single-use too
    again = await async_client.post(f"/api/approvals/{new['approval_id']}", json={"approved": True}, headers=h)
    assert again.status_code == 409
    resolved = [e for e in await events(tid) if e.event_type == "approval.resolved"]
    assert [e.payload_json["status"] for e in resolved] == ["re_approval_required", "approved"]
    assert resolved[-1].payload_json["approval_id"] == new["approval_id"]


async def test_approval_access_control(async_client, guard_http, script):
    h = await login(async_client)
    tid = await start_send_task(async_client, h, script)
    appr = (await wait_for(tid, "approval.required")).payload_json["approval"]

    assert (await async_client.post("/api/approvals/appr-nope", json={"approved": True}, headers=h)).status_code == 404
    assert (await async_client.post(f"/api/approvals/{appr['approval_id']}", json={"approved": True})).status_code in (401, 403)
    admin_h = await login(async_client, "admin")  # not the task owner
    assert (await async_client.post(f"/api/approvals/{appr['approval_id']}", json={"approved": True},
                                    headers=admin_h)).status_code == 403
    await async_client.post(f"/api/approvals/{appr['approval_id']}", json={"approved": False}, headers=h)
    await wait_for(tid, TERMINAL)


async def test_approval_guard_down_fails_closed(async_client, guard_http, script):
    h = await login(async_client)
    sent_before = len(mock_state.sent_messages)
    tid = await start_send_task(async_client, h, script)
    appr = (await wait_for(tid, "approval.required")).payload_json["approval"]

    class Down(httpx.AsyncBaseTransport):
        async def handle_async_request(self, request):
            raise httpx.ConnectError("down")

    set_guard_client(HttpGuardClient(base_url="http://guard.test", token="x", transport=Down()))
    r = await async_client.post(f"/api/approvals/{appr['approval_id']}", json={"approved": True}, headers=h)
    assert r.status_code == 502
    await asyncio.sleep(0.2)
    assert len(mock_state.sent_messages) == sent_before
    # still pending: can be answered once the guard is back
    set_guard_client(guard_http)
    r = await async_client.post(f"/api/approvals/{appr['approval_id']}", json={"approved": False}, headers=h)
    assert r.json()["status"] == "denied"
    await wait_for(tid, TERMINAL)


# ---------------------------------------------------------------- SSE replay

async def test_sse_last_event_id_replay_and_access(async_client, guard_http, script):
    h = await login(async_client)
    tid = await start_send_task(async_client, h, script)
    appr = (await wait_for(tid, "approval.required")).payload_json["approval"]
    await async_client.post(f"/api/approvals/{appr['approval_id']}", json={"approved": True}, headers=h)
    await wait_for(tid, TERMINAL)

    full = parse_sse((await async_client.get(f"/api/tasks/{tid}/events", headers=h)).text)
    n = len(full)
    assert n > 6

    cut = 4
    part = parse_sse((await async_client.get(f"/api/tasks/{tid}/events",
                                             headers={**h, "Last-Event-ID": str(cut)})).text)
    assert [m["data"]["seq"] for m in part] == list(range(cut + 1, n + 1))
    assert part == full[cut:]

    # Credentials in URLs can leak through access logs; SSE only accepts Authorization headers.
    tok = h["Authorization"].split()[1]
    query_token = await async_client.get(f"/api/tasks/{tid}/events?last_event_id={cut}&access_token={tok}")
    assert query_token.status_code == 401
    resumed = parse_sse((await async_client.get(
        f"/api/tasks/{tid}/events?last_event_id={cut}", headers=h
    )).text)
    assert resumed == part

    # resuming after the terminal event returns an empty, finished stream
    done = await async_client.get(f"/api/tasks/{tid}/events", headers={**h, "Last-Event-ID": str(n)})
    assert done.status_code == 200 and done.text == ""

    # auth: none -> 401; other non-admin owner check; admin may read
    assert (await async_client.get(f"/api/tasks/{tid}/events")).status_code == 401
    assert (await async_client.get(f"/api/tasks/{tid}/events", headers=await login(async_client, "admin"))).status_code == 200
    assert (await async_client.get("/api/tasks/nope/events", headers=h)).status_code == 404


# ---------------------------------------------------------------- admin proxy

@pytest.fixture
def admin_proxy():
    admin_api.set_admin_transport(httpx.ASGITransport(app=guard_app))
    yield
    admin_api.set_admin_transport(None)


async def test_admin_proxy_role_and_passthrough(async_client, admin_proxy):
    user_h, admin_h = await login(async_client), await login(async_client, "admin")

    assert (await async_client.get("/api/admin/health", headers=user_h)).status_code == 403
    assert (await async_client.get("/api/admin/audit/verify", headers=user_h)).status_code == 403
    assert (await async_client.post("/api/admin/kill-switch", headers=user_h,
                                    json={"scope": "all_write_tools", "target": "*", "enabled": True})).status_code == 403
    assert (await async_client.get("/api/admin/health")).status_code in (401, 403)

    r = await async_client.get("/api/admin/health", headers=admin_h)
    assert r.status_code == 200 and r.json()["contract_version"]
    direct = await httpx.AsyncClient(transport=httpx.ASGITransport(app=guard_app), base_url="http://g").get(
        "/admin/v1/health", headers={"Authorization": "Bearer dev-guard-token"})
    assert r.json()["kill_switch"] == direct.json()["kill_switch"]

    assert (await async_client.get("/api/admin/audit/verify", headers=admin_h)).status_code == 200
    assert (await async_client.get("/api/admin/audit?task_id=none&tool=gmail.send", headers=admin_h)).status_code == 200
    assert (await async_client.get("/api/admin/config", headers=admin_h)).status_code == 200
    # guard errors pass through unchanged, and path escapes are refused
    assert (await async_client.get("/api/admin/nonexistent", headers=admin_h)).status_code == 404
    assert (await async_client.get("/api/admin/../v1/health", headers=admin_h)).status_code in (400, 404)


async def test_admin_proxy_guard_unreachable_is_502(async_client):
    class Down(httpx.AsyncBaseTransport):
        async def handle_async_request(self, request):
            raise httpx.ConnectError("down")

    admin_api.set_admin_transport(Down())
    try:
        assert (await async_client.get("/api/admin/health", headers=await login(async_client, "admin"))).status_code == 502
    finally:
        admin_api.set_admin_transport(None)
