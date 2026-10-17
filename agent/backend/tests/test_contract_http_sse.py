"""API and SSE checks against eva-dev-docs/02-contracts-v0.md §§5–6."""

from __future__ import annotations

import asyncio
import json
import uuid

import pytest

from app.db.database import async_session_factory
from app.db.models import Task, User
from app.sse.broadcaster import get_task_broadcaster


REST_METHODS = {
    "/api/auth/login": {"post"},
    "/api/me": {"get"},
    "/api/tasks": {"get", "post"},
    "/api/tasks/{task_id}": {"get"},
    "/api/tasks/{task_id}/cancel": {"post"},
    "/api/tasks/{task_id}/events": {"get"},
    "/api/approvals/{approval_id}": {"post"},
    "/api/connectors": {"get"},
    "/api/connectors/gmail/auth-url": {"get"},
    "/oauth/gmail/callback": {"get"},
    "/api/connectors/gmail": {"delete"},
    "/api/files": {"get"},
    "/api/files/content": {"get"},
    "/api/health": {"get"},
    "/api/admin/{path}": {"get", "post", "put", "delete"},
}


@pytest.mark.asyncio
async def test_rest_routes_match_frozen_contract(async_client):
    paths = async_client._transport.app.openapi()["paths"]
    for path, methods in REST_METHODS.items():
        assert path in paths, f"missing contract route {path}"
        actual = {method for method in paths[path] if method in {"get", "post", "put", "delete"}}
        assert methods <= actual, (path, methods, actual)


@pytest.mark.asyncio
async def test_rest_error_shape_and_invalid_resume_id(async_client):
    user = (await async_client.post("/api/auth/login", json={
        "email": "user@eva.local", "password": "UserPassword123!",
    })).json()
    headers = {"Authorization": f"Bearer {user['access_token']}"}
    missing = await async_client.get("/api/tasks/no-such-task", headers=headers)
    assert missing.status_code == 404
    assert set(missing.json()) == {"detail"}
    invalid = await async_client.get(
        "/api/tasks/no-such-task/events", headers={**headers, "Last-Event-ID": "not-an-int"}
    )
    # Task existence is checked before the resume cursor, so create an actual task below
    # and exercise the input validation on a valid resource.
    assert invalid.status_code == 404

    user_id = user["user"]["id"]
    task_id = f"contract-{uuid.uuid4().hex}"
    async with async_session_factory() as session:
        session.add(Task(id=task_id, user_id=user_id, request="contract", status="running"))
        await session.commit()
    invalid = await async_client.get(
        f"/api/tasks/{task_id}/events", headers={**headers, "Last-Event-ID": "not-an-int"}
    )
    assert invalid.status_code == 400 and invalid.json() == {"detail": "Invalid Last-Event-ID"}


@pytest.mark.asyncio
async def test_sse_frame_contract_disconnect_cleanup_and_resume():
    task_id = f"sse-contract-{uuid.uuid4().hex}"
    user_id = f"contract-user-{uuid.uuid4().hex}"
    async with async_session_factory() as session:
        session.add(User(id=user_id, email=f"{user_id}@eva.local", hashed_password="pw", role="user"))
        session.add(Task(id=task_id, user_id=user_id, request="contract", status="running"))
        await session.commit()

    broadcaster = await get_task_broadcaster(task_id)
    stream = broadcaster.subscribe()
    first = None
    try:
        next_frame = asyncio.create_task(stream.__anext__())
        for _ in range(100):
            if broadcaster._subscribers:
                break
            await asyncio.sleep(0)
        assert broadcaster._subscribers
        first = await broadcaster.emit("task.started", {"policy": {}, "guard_health": None})
        frame = await next_frame
        lines = dict(line.split(": ", 1) for line in frame.strip().splitlines())
        data = json.loads(lines["data"])
        assert lines["id"] == str(first["seq"]) == "1"
        assert lines["event"] == "task.started"
        assert {"task_id", "seq", "ts", "policy", "guard_health"} <= data.keys()

        # Closing a client subscription removes its live queue; persisted events remain replayable.
        await stream.aclose()
        assert not broadcaster._subscribers
        await broadcaster.emit("task.completed", {
            "final_text": "done", "summary": {"sentences_removed": 0, "actions_denied": 0, "approvals": 0}
        })
        replay = [frame async for frame in broadcaster.subscribe(last_event_id=1)]
        assert len(replay) == 1 and "id: 2" in replay[0] and "event: task.completed" in replay[0]
        replay_data = json.loads(replay[0].split("data: ", 1)[1])
        assert replay_data["summary"] == {"sentences_removed": 0, "actions_denied": 0, "approvals": 0}
    finally:
        if stream:
            await stream.aclose()
