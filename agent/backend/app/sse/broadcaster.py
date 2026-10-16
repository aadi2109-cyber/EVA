"""
Server-Sent Events (SSE) broadcaster with monotonic seq, DB persistence, and Last-Event-ID replay.
"""

from __future__ import annotations

import asyncio
import json
import logging
from datetime import datetime, timezone
from typing import Any, AsyncIterator
from sqlalchemy import select

from contracts.models import SSEEventType
from app.db.database import async_session_factory
from app.db.models import TaskEvent

logger = logging.getLogger(__name__)


class TaskSSEBroadcaster:
    """Manages active event listeners and sequence counters for a task."""

    def __init__(self, task_id: str) -> None:
        self.task_id = task_id
        self._seq: int = 0
        self._subscribers: list[asyncio.Queue[dict[str, Any]]] = []
        self._lock = asyncio.Lock()

    async def init_seq_from_db(self) -> None:
        async with async_session_factory() as session:
            stmt = select(TaskEvent.seq).where(TaskEvent.task_id == self.task_id).order_by(TaskEvent.seq.desc()).limit(1)
            res = await session.execute(stmt)
            highest = res.scalar_one_or_none()
            if highest is not None:
                self._seq = highest

    async def emit(self, event_type: SSEEventType | str, payload: dict[str, Any]) -> dict[str, Any]:
        async with self._lock:
            self._seq += 1
            seq = self._seq
            ts = datetime.now(timezone.utc)
            evt_type_str = event_type.value if isinstance(event_type, SSEEventType) else str(event_type)

            event_record = {
                "task_id": self.task_id,
                "seq": seq,
                "ts": ts.isoformat(),
                "type": evt_type_str,
                "payload": payload,
            }

            # Persist to DB
            try:
                async with async_session_factory() as session:
                    db_event = TaskEvent(
                        task_id=self.task_id,
                        seq=seq,
                        ts=ts,
                        event_type=evt_type_str,
                        payload_json=payload,
                    )
                    session.add(db_event)
                    await session.commit()
            except Exception as e:
                logger.error("Failed to persist task event %d: %s", seq, e)

            # Broadcast to in-memory active subscribers
            for queue in list(self._subscribers):
                try:
                    queue.put_nowait(event_record)
                except Exception:
                    pass

            return event_record

    async def subscribe(self, last_event_id: int | None = None) -> AsyncIterator[str]:
        """Replay stored events with seq > last_event_id (0 when absent), then stream live.

        The live queue is registered before the replay query, and emit() persists before it
        broadcasts, so no event can be missed; duplicates are dropped by seq.
        """
        terminal_types = {
            SSEEventType.TASK_COMPLETED.value,
            SSEEventType.TASK_FAILED.value,
            SSEEventType.TASK_HELD.value,
            SSEEventType.TASK_CANCELLED.value,
        }
        queue: asyncio.Queue[dict[str, Any]] = asyncio.Queue()
        self._subscribers.append(queue)
        sent = max(last_event_id or 0, 0)

        try:
            async with async_session_factory() as session:
                stmt = (
                    select(TaskEvent)
                    .where(TaskEvent.task_id == self.task_id, TaskEvent.seq > sent)
                    .order_by(TaskEvent.seq.asc())
                )
                past_events = (await session.execute(stmt)).scalars().all()
                term_stmt = select(TaskEvent.seq).where(
                    TaskEvent.task_id == self.task_id, TaskEvent.event_type.in_(terminal_types)
                ).limit(1)
                terminal_seq = (await session.execute(term_stmt)).scalar_one_or_none()

            for pe in past_events:
                yield self._format_sse_message(
                    event_type=pe.event_type,
                    data={"task_id": pe.task_id, "seq": pe.seq, "ts": pe.ts.isoformat(), **pe.payload_json},
                    event_id=str(pe.seq),
                )
                sent = pe.seq

            # Task already finished and everything up to its terminal event has been delivered.
            if terminal_seq is not None and sent >= terminal_seq:
                return

            while True:
                record = await queue.get()
                is_terminal = record["type"] in terminal_types
                if record["seq"] <= sent:
                    if is_terminal:
                        break
                    continue
                sent = record["seq"]
                data = {"task_id": record["task_id"], "seq": record["seq"], "ts": record["ts"], **record["payload"]}
                yield self._format_sse_message(event_type=record["type"], data=data, event_id=str(record["seq"]))
                if is_terminal:
                    break
        finally:
            if queue in self._subscribers:
                self._subscribers.remove(queue)

    def _format_sse_message(self, event_type: str, data: dict[str, Any], event_id: str) -> str:
        return f"id: {event_id}\nevent: {event_type}\ndata: {json.dumps(data)}\n\n"


_task_broadcasters: dict[str, TaskSSEBroadcaster] = {}
_broadcasters_lock = asyncio.Lock()


async def get_task_broadcaster(task_id: str) -> TaskSSEBroadcaster:
    async with _broadcasters_lock:
        if task_id not in _task_broadcasters:
            broadcaster = TaskSSEBroadcaster(task_id)
            await broadcaster.init_seq_from_db()
            _task_broadcasters[task_id] = broadcaster
        return _task_broadcasters[task_id]
