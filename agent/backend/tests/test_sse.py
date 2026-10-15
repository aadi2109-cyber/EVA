"""
Tests for Server-Sent Events (SSE), Monotonic Sequence Numbers, and Replay.
"""

import asyncio
import pytest
from app.sse.broadcaster import get_task_broadcaster


@pytest.mark.asyncio
async def test_sse_monotonic_seq_and_replay():
    task_id = "test-task-sse-seq"
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
