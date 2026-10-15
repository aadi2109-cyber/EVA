"""
Task management API: creation, listing, detail, cancellation, and SSE live streams.
"""

from __future__ import annotations

import asyncio
from typing import Annotated, Any
from fastapi import APIRouter, Depends, Header, HTTPException, Query, Request, status
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.agent.orchestrator import TaskOrchestrator, get_active_task_orchestrator
from app.auth.deps import get_current_user
from app.db.database import get_db_session
from app.db.models import Message, Task, TaskEvent, User
from app.sse.broadcaster import get_task_broadcaster

router = APIRouter(prefix="/api/tasks", tags=["tasks"])


class CreateTaskRequest(BaseModel):
    request: str = Field(..., description="The user's typed natural language request")


class CreateTaskResponse(BaseModel):
    task_id: str


class TaskSummaryResponse(BaseModel):
    id: str
    request: str
    status: str
    created_at: str
    updated_at: str
    final_text: str | None = None


class TaskDetailResponse(BaseModel):
    id: str
    request: str
    status: str
    policy: dict[str, Any] | None = None
    final_text: str | None = None
    summary: dict[str, Any] | None = None
    messages: list[dict[str, Any]] = []
    events_count: int = 0
    created_at: str
    updated_at: str


@router.post("", response_model=CreateTaskResponse)
async def create_task(
    req: CreateTaskRequest,
    current_user: Annotated[User, Depends(get_current_user)],
    session: Annotated[AsyncSession, Depends(get_db_session)],
) -> CreateTaskResponse:
    task = Task(user_id=current_user.id, request=req.request, status="running")
    session.add(task)
    await session.commit()
    await session.refresh(task)

    # Spawn orchestrator in background
    orchestrator = TaskOrchestrator(
        task_id=task.id,
        user_id=current_user.id,
        user_role=current_user.role,
        user_request=req.request,
    )
    asyncio.create_task(orchestrator.run())

    return CreateTaskResponse(task_id=task.id)


@router.get("", response_model=list[TaskSummaryResponse])
async def list_tasks(
    current_user: Annotated[User, Depends(get_current_user)],
    session: Annotated[AsyncSession, Depends(get_db_session)],
) -> list[TaskSummaryResponse]:
    stmt = select(Task)
    if current_user.role != "admin":
        stmt = stmt.where(Task.user_id == current_user.id)
    stmt = stmt.order_by(Task.created_at.desc())

    result = await session.execute(stmt)
    tasks = result.scalars().all()

    return [
        TaskSummaryResponse(
            id=t.id,
            request=t.request,
            status=t.status,
            created_at=t.created_at.isoformat(),
            updated_at=t.updated_at.isoformat(),
            final_text=t.final_text,
        )
        for t in tasks
    ]


@router.get("/{task_id}", response_model=TaskDetailResponse)
async def get_task(
    task_id: str,
    current_user: Annotated[User, Depends(get_current_user)],
    session: Annotated[AsyncSession, Depends(get_db_session)],
) -> TaskDetailResponse:
    stmt = select(Task).where(Task.id == task_id)
    result = await session.execute(stmt)
    task = result.scalar_one_or_none()

    if not task:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Task not found")

    if current_user.role != "admin" and task.user_id != current_user.id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Access denied")

    msg_stmt = select(Message).where(Message.task_id == task_id).order_by(Message.created_at.asc())
    msg_res = await session.execute(msg_stmt)
    messages = [{"role": m.role, "content": m.content, "created_at": m.created_at.isoformat()} for m in msg_res.scalars().all()]

    evt_stmt = select(TaskEvent.seq).where(TaskEvent.task_id == task_id)
    evt_res = await session.execute(evt_stmt)
    events_count = len(evt_res.scalars().all())

    return TaskDetailResponse(
        id=task.id,
        request=task.request,
        status=task.status,
        policy=task.policy_json,
        final_text=task.final_text,
        summary=task.summary_json,
        messages=messages,
        events_count=events_count,
        created_at=task.created_at.isoformat(),
        updated_at=task.updated_at.isoformat(),
    )


@router.post("/{task_id}/cancel")
async def cancel_task(
    task_id: str,
    current_user: Annotated[User, Depends(get_current_user)],
    session: Annotated[AsyncSession, Depends(get_db_session)],
) -> dict[str, str]:
    stmt = select(Task).where(Task.id == task_id)
    result = await session.execute(stmt)
    task = result.scalar_one_or_none()

    if not task:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Task not found")

    if current_user.role != "admin" and task.user_id != current_user.id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Access denied")

    active_orch = get_active_task_orchestrator(task_id)
    if active_orch:
        active_orch.cancel()

    task.status = "cancelled"
    await session.commit()
    return {"status": "cancelled", "task_id": task_id}


@router.get("/{task_id}/events")
async def stream_task_events(
    task_id: str,
    request: Request,
    last_event_id_header: Annotated[str | None, Header(alias="Last-Event-ID")] = None,
    last_event_id_query: Annotated[int | None, Query(alias="last_event_id")] = None,
) -> StreamingResponse:
    last_id = None
    if last_event_id_header is not None:
        try:
            last_id = int(last_event_id_header)
        except ValueError:
            pass
    elif last_event_id_query is not None:
        last_id = last_event_id_query

    broadcaster = await get_task_broadcaster(task_id)
    return StreamingResponse(
        broadcaster.subscribe(last_event_id=last_id),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )
