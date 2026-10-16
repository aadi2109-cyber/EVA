from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import select

from app.db.database import async_session_factory
from app.db.models import ApprovalIndex, Task, TaskEvent, User
from app.main import recover_inflight_tasks


@pytest.mark.asyncio
async def test_restart_holds_inflight_task_and_expires_pending_approval():
    suffix = uuid.uuid4().hex
    user_id = f"restart-user-{suffix}"
    task_id = f"restart-task-{suffix}"
    approval_id = f"restart-approval-{suffix}"
    async with async_session_factory() as session:
        session.add(User(id=user_id, email=f"{user_id}@eva.local", hashed_password="pw", role="user"))
        session.add(Task(id=task_id, user_id=user_id, request="send a message", status="running"))
        session.add(ApprovalIndex(
            id=approval_id,
            task_id=task_id,
            call_id="call-1",
            tool="messages.send",
            exact_action_json={"tool": "messages.send", "args": {"channel": "mock", "text": "hello"}},
            action_hash="hash",
            status="pending",
            expires_at=datetime.now(timezone.utc) + timedelta(minutes=5),
        ))
        await session.commit()

    assert await recover_inflight_tasks() == 1

    async with async_session_factory() as session:
        task = (await session.execute(select(Task).where(Task.id == task_id))).scalar_one()
        approval = (await session.execute(select(ApprovalIndex).where(ApprovalIndex.id == approval_id))).scalar_one()
        events = list((await session.execute(
            select(TaskEvent).where(TaskEvent.task_id == task_id).order_by(TaskEvent.seq)
        )).scalars())
    assert task.status == "held"
    assert task.final_text and "backend restarted" in task.final_text
    assert approval.status == "expired"
    assert len(events) == 1
    assert events[0].event_type == "task.held"
    assert events[0].payload_json["reason"] == "backend_restart"
