"""
Tests for Server-Sent Events (SSE), Monotonic Sequence Numbers, and Replay.
"""

import asyncio
import pytest
from app.db.database import async_session_factory
from app.db.models import Task, User
from app.sse.broadcaster import get_task_broadcaster


@pytest.mark.asyncio
async def test_sse_monotonic_seq_and_replay():
    task_id = "test-task-sse-seq"

    # Insert user and task to satisfy foreign keys
    async with async_session_factory() as session:
        user = User(id="u-sse", email="sse@eva.local", hashed_password="pw", role="user")
        session.add(user)
        task = Task(id=task_id, user_id="u-sse", request="SSE test", status="running")
        session.add(task)
        await session.commit()

    broadcaster = await get_task_broadcaster(task_id)

    # Emit three events
    e1 = await broadcaster.emit("task.started", {"step": 1})
    e2 = await broadcaster.emit("plan.step", {"step": 2})
    e3 = await broadcaster.emit("task.completed", {"summary": "done"})

    assert e1["seq"] == 1
    assert e2["seq"] == 2
    assert e3["seq"] == 3

    # Replay with Last-Event-ID = 1 (should yield events 2 and 3)
    replayed = []
    async for sse_line in broadcaster.subscribe(last_event_id=1):
        replayed.append(sse_line)

    assert len(replayed) == 2
    assert "id: 2" in replayed[0]
    assert "id: 3" in replayed[1]
