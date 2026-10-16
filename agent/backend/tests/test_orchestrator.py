"""
Security-Critical Tests for Orchestrator Loop, Guard Enforcement, and Sanitization.
"""

import asyncio
from typing import Any, AsyncIterator
import pytest
from contracts.models import SubmitApprovalRequest
from app.agent.orchestrator import TaskOrchestrator
from app.guard_client.base import GuardClient, GuardDownError
from app.guard_client.in_process import InProcessGuardClient
from app.model.base import ModelEvent, ModelEventType, ModelProvider
from app.model.scripted import ScriptedProvider
from eva_guard.stub import StubGuard


class MessageRecordingProvider:
    """ModelProvider that records every messages list received during step() calls."""

    def __init__(self, delegate: ModelProvider) -> None:
        self.delegate = delegate
        self.recorded_messages_history: list[list[dict[str, Any]]] = []

    async def step(
        self,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]] | None = None,
    ) -> AsyncIterator[ModelEvent]:
        # Deepcopy or slice snapshot of messages passed to the model
        self.recorded_messages_history.append([dict(m) for m in messages])
        async for event in self.delegate.step(messages, tools):
            yield event


@pytest.mark.asyncio
async def test_orchestrator_allow_flow(stub_guard_client):
    """Test standard permitted tool execution and completion."""
    scripted = ScriptedProvider()
    scripted.add_tool_call("gmail.search", {"query": "invoices"})
    scripted.add_final_text("Found your invoices.")

    recorder = MessageRecordingProvider(scripted)
    orch = TaskOrchestrator(
        task_id="test-task-allow",
        user_id="user-1",
        user_role="user",
        user_request="Find my invoices",
        model_provider=recorder,
        guard_client=stub_guard_client,
    )

    result = await orch.run()
    assert result["status"] == "completed"
    assert "Found your invoices" in result["final_text"]


@pytest.mark.asyncio
async def test_orchestrator_deny_flow(stub_guard_client):
    """Test policy denial on prohibited tools."""
    scripted = ScriptedProvider()
    # In StubGuard, gmail.send without approval check yields REQUIRE_APPROVAL or DENY if outside policy
    scripted.add_tool_call("unknown_malicious_tool", {"arg": "bad"})
    scripted.add_final_text("Handled rejection.")

    orch = TaskOrchestrator(
        task_id="test-task-deny",
        user_id="user-1",
        user_role="user",
        user_request="Perform clean task",
        model_provider=scripted,
        guard_client=stub_guard_client,
    )

    result = await orch.run()
    assert result["status"] == "completed"
    assert orch.actions_denied >= 1


@pytest.mark.asyncio
async def test_orchestrator_approval_flow(stub_guard_client):
    """Test approval requirement pause, user approval submission, and execution."""
    scripted = ScriptedProvider()
    scripted.add_tool_call("gmail.send", {"to": "bob@corp.com", "subject": "Test", "body": "Body"})
    scripted.add_final_text("Email dispatched.")

    orch = TaskOrchestrator(
        task_id="test-task-approval",
        user_id="user-1",
        user_role="user",
        user_request="Send email to bob@corp.com",
        model_provider=scripted,
        guard_client=stub_guard_client,
    )

    async def user_decision_agent():
        # Wait until orchestrator is awaiting approval
        for _ in range(50):
            await asyncio.sleep(0.05)
            if orch.pending_approval_id:
                sub_req = SubmitApprovalRequest(user_id="user-1", approved=True)
                resp = await stub_guard_client.submit_approval(orch.pending_approval_id, sub_req)
                orch.resolve_approval(orch.pending_approval_id, resp)
                return

    asyncio.create_task(user_decision_agent())
    result = await orch.run()
    assert result["status"] == "completed"
    assert orch.approvals_count >= 1


@pytest.mark.asyncio
async def test_orchestrator_raw_output_never_reaches_model_context(stub_guard_client):
    """
    CRITICAL SECURITY INVARIANT:
    Raw tool output must NEVER reach the model context.
    Only sanitized fields wrapped in labelled <tool_output ...> tags may be provided.
    """
    scripted = ScriptedProvider()
    scripted.add_tool_call("gmail.read", {"message_id": "msg-003"})  # S1 attack email
    scripted.add_final_text("Summary completed.")

    recorder = MessageRecordingProvider(scripted)
    orch = TaskOrchestrator(
        task_id="test-task-no-raw",
        user_id="user-1",
        user_role="user",
        user_request="Read message 3",
        model_provider=recorder,
        guard_client=stub_guard_client,
    )

    await orch.run()

    # Verify that in all messages passed to the model, all tool outputs are wrapped
    # in <tool_output ... trust="untrusted">
    assert len(recorder.recorded_messages_history) >= 2
    second_step_messages = recorder.recorded_messages_history[1]

    tool_output_found = False
    for msg in second_step_messages:
        content = msg.get("content", "")
        if "<tool_output" in content:
            tool_output_found = True
            assert 'trust="untrusted"' in content
            assert "</tool_output>" in content

    assert tool_output_found is True


@pytest.mark.asyncio
async def test_orchestrator_fail_closed_when_guard_down():
    """
    CRITICAL SECURITY INVARIANT:
    If Guard is unreachable, times out, or throws an error,
    the orchestrator MUST FAIL CLOSED (DENY / task.held).
    No fail-open path exists.
    """
    class FailingGuardClient:
        async def build_task_policy(self, req):
            raise GuardDownError("Guard service unreachable")
        async def check_action(self, req):
            raise GuardDownError("Guard service unreachable")
        async def scan_tool_result(self, req):
            raise GuardDownError("Guard service unreachable")
        async def submit_approval(self, id, req):
            raise GuardDownError("Guard service unreachable")
        async def verify_state(self, req):
            raise GuardDownError("Guard service unreachable")
        async def health(self):
            raise GuardDownError("Guard service unreachable")

    scripted = ScriptedProvider()
    orch = TaskOrchestrator(
        task_id="test-task-guard-down",
        user_id="user-1",
        user_role="user",
        user_request="Read all emails",
        model_provider=scripted,
        guard_client=FailingGuardClient(),
    )

    result = await orch.run()
    assert result["status"] == "held"
    assert result["reason"] == "guard_error"
