"""plan.step lifecycle: 0-based index, running -> completed|failed, never left running."""

from __future__ import annotations

import uuid

import httpx
import pytest
from sqlalchemy import select

from app.agent.orchestrator import TaskOrchestrator
from app.db.database import async_session_factory
from app.db.models import TaskEvent
from app.model import OllamaProvider
from app.model.scripted import ScriptedProvider

pytestmark = pytest.mark.asyncio


async def stream(task_id: str) -> list[tuple[str, dict]]:
    async with async_session_factory() as s:
        rows = await s.execute(select(TaskEvent).where(TaskEvent.task_id == task_id).order_by(TaskEvent.seq))
        return [(r.event_type, r.payload_json) for r in rows.scalars()]


def steps(events):
    return [(p["index"], p["status"]) for t, p in events if t == "plan.step"]


async def run(provider, request="List my files"):
    tid = f"plan-{uuid.uuid4().hex[:6]}"
    from app.guard_client.factory import get_guard_client

    orch = TaskOrchestrator(task_id=tid, user_id="u-plan", user_role="user", user_request=request,
                            model_provider=provider, guard_client=get_guard_client())
    return tid, await orch.run()


async def test_each_step_runs_then_completes_zero_based(stub_guard_client):
    sp = ScriptedProvider()
    sp.add_tool_call("files.list", {"path": "."})
    sp.add_final_text("Here are your files.")
    tid, res = await run(sp)
    ev = await stream(tid)
    assert res["status"] == "completed"
    assert steps(ev) == [(0, "running"), (0, "completed"), (1, "running"), (1, "completed")]
    # titles are stable per index and the last step closes BEFORE the terminal event
    plan = [p for t, p in ev if t == "plan.step"]
    assert plan[0]["title"] == plan[1]["title"] == "Step 1" and plan[2]["title"] == "Step 2"
    kinds = [t for t, _ in ev]
    assert kinds.index("plan.step", len(kinds) - 1 - kinds[::-1].index("plan.step")) < kinds.index("task.completed")


async def test_step_fails_when_model_provider_dies(stub_guard_client):
    p = OllamaProvider(base_url="https://x.test", api_key="k", model="m",
                       transport=httpx.MockTransport(lambda r: httpx.Response(503)))
    tid, res = await run(p)
    ev = await stream(tid)
    assert res["status"] == "failed"
    assert steps(ev) == [(0, "running"), (0, "failed")]
    kinds = [t for t, _ in ev]
    assert kinds.index("task.failed") > max(i for i, k in enumerate(kinds) if k == "plan.step")


async def test_no_step_is_ever_left_running(stub_guard_client, monkeypatch):
    from app.config import settings

    monkeypatch.setattr(settings, "MAX_STEPS", 2)
    sp = ScriptedProvider()
    for _ in range(5):
        sp.add_tool_call("files.list", {"path": "."})
    tid, _ = await run(sp)
    seq = steps(await stream(tid))
    open_ = {}
    for idx, status in seq:
        if status == "running":
            assert idx not in open_
            open_[idx] = True
        else:
            assert open_.pop(idx, None), f"{status} without running for step {idx}"
    assert not open_, f"steps left running: {open_}"
    assert [i for i, s in seq if s == "running"] == [0, 1]
