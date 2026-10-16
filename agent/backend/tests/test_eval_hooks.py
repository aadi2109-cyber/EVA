"""Failure-injection hooks, GUARD_PROFILE gating, eval runner and reset."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from contracts.models import (
    BuildPolicyRequest,
    CheckActionRequest,
    Provenance,
    ScanField,
    ScanRequest,
    SourceType,
    Trust,
)
from app.agent.orchestrator import TaskOrchestrator
from app.config import Settings, settings
from app.eval import hooks
from app.eval.reset import reset_eval_environment
from app.eval.run_scenario import run_scenario
from app.guard_client.base import GuardDownError
from app.model.scripted import ScriptedProvider
from env.mock.state import state as mock_state


@pytest.fixture
def real_guard_client():
    """Scenarios assert real gateway behaviour (StubGuard asks approval for S2)."""
    from app.guard_client.factory import set_guard_client
    from app.guard_client.in_process import InProcessGuardClient

    client = InProcessGuardClient()
    set_guard_client(client)
    yield client
    set_guard_client(None)


@pytest.fixture
def eval_env(monkeypatch):
    monkeypatch.setattr(settings, "APP_ENV", "eval")
    monkeypatch.setattr(settings, "GUARD_PROFILE", "full")
    for f in hooks.FLAGS:
        monkeypatch.setattr(settings, f, False)
    yield monkeypatch
    mock_state.reset()


def _build(client, tid="t1", req_text="Email bob@corp.com"):
    import asyncio  # noqa: F401
    return client.build_task_policy(
        BuildPolicyRequest(
            task_id=tid, user_id="u", user_role="user", user_request=req_text,
            available_tools=["gmail.send", "gmail.search", "files.write", "files.read"],
        )
    )


def _check(tool="files.write", read_only=False, tid="t1"):
    return CheckActionRequest(
        task_id=tid, call_id="c1", tool=tool, args={"path": "a.txt", "content": "x"},
        arg_provenance={"path": Provenance(source=SourceType.USER, trust=Trust.TRUSTED)} if False else {},
        read_only=read_only,
    )


# ---------------------------------------------------------------- config gating

@pytest.mark.parametrize("profile", ["off", "basic"])
@pytest.mark.parametrize("env", ["dev", "prod"])
def test_profile_off_basic_refused_outside_eval(profile, env):
    with pytest.raises(ValidationError):
        Settings(APP_ENV=env, GUARD_PROFILE=profile, _env_file=None)


@pytest.mark.parametrize("profile", ["off", "basic", "full"])
def test_profile_allowed_in_eval(profile):
    assert Settings(APP_ENV="eval", GUARD_PROFILE=profile, _env_file=None).GUARD_PROFILE == profile


def test_full_profile_allowed_everywhere():
    for env in ("dev", "prod"):
        assert Settings(APP_ENV=env, GUARD_PROFILE="full", _env_file=None).GUARD_PROFILE == "full"


@pytest.mark.parametrize("flag", ["EVA_FAIL_TIER2_DOWN", "EVA_FAIL_GUARD_UNREACHABLE", "EVA_FAIL_LAYA_TIMEOUT"])
def test_failure_flags_refused_outside_eval(flag, monkeypatch):
    monkeypatch.setenv(flag, "true")
    with pytest.raises(ValidationError):
        Settings(APP_ENV="dev", _env_file=None)
    with pytest.raises(ValidationError):
        Settings(APP_ENV="prod", _env_file=None)
    s = Settings(APP_ENV="eval", _env_file=None)
    assert any(getattr(s, f) for f in hooks.FLAGS)


def test_eval_refuses_real_gmail():
    with pytest.raises(ValidationError):
        Settings(APP_ENV="eval", GMAIL_MODE="real", _env_file=None)


def test_flags_ignored_at_runtime_outside_eval(monkeypatch):
    monkeypatch.setattr(settings, "APP_ENV", "dev")
    monkeypatch.setattr(settings, "INJECT_GUARD_UNREACHABLE", True)
    monkeypatch.setattr(settings, "GUARD_PROFILE", "off")
    assert not hooks.flag("INJECT_GUARD_UNREACHABLE")
    assert hooks.profile() == "full"
    hooks.raise_if_unreachable()  # no raise
    with pytest.raises(RuntimeError):
        with hooks.injected(INJECT_TIER2_DOWN=True):
            pass


# ---------------------------------------------------------------- hooks (client level)

@pytest.mark.asyncio
async def test_guard_unreachable_raises_in_eval(eval_env, stub_guard_client):
    eval_env.setattr(settings, "INJECT_GUARD_UNREACHABLE", True)
    with pytest.raises(GuardDownError):
        await stub_guard_client.check_action(_check())
    with pytest.raises(GuardDownError):
        await stub_guard_client.health()


@pytest.mark.asyncio
async def test_guard_unreachable_ignored_in_dev(stub_guard_client, monkeypatch):
    monkeypatch.setattr(settings, "INJECT_GUARD_UNREACHABLE", True)  # APP_ENV=dev
    assert (await stub_guard_client.health()).status in ("ok", "degraded")


@pytest.mark.asyncio
async def test_tier2_down_denies_side_effects_allows_reads(eval_env, stub_guard_client):
    from contracts.models import BuildPolicyRequest
    await stub_guard_client.build_task_policy(BuildPolicyRequest(
        task_id="t1", user_id="u", user_role="user", user_request="Read a.txt",
        available_tools=["files.read", "files.write"]))
    eval_env.setattr(settings, "INJECT_TIER2_DOWN", True)
    deny = await stub_guard_client.check_action(_check("files.write", read_only=False))
    assert deny.decision == "DENY" and "POSTURE_DEGRADED" in [r.value for r in deny.reasons]
    ok = await stub_guard_client.check_action(_check("files.read", read_only=True))
    assert ok.decision == "ALLOW"
    h = await stub_guard_client.health()
    assert h.tier2_available is False and h.status == "degraded"
    scan = await stub_guard_client.scan_tool_result(
        ScanRequest(task_id="t1", call_id="c", tool="files.read",
                    fields=[ScanField(name="content", text="hello", trust=Trust.UNTRUSTED)])
    ) if "trust" in ScanField.model_fields else None
    if scan is not None:
        assert scan.tier2_available is False


@pytest.mark.asyncio
async def test_laya_timeout_fails_closed_for_side_effects(eval_env, stub_guard_client):
    eval_env.setattr(settings, "INJECT_LAYA_TIMEOUT", True)
    resp = await stub_guard_client.check_action(_check("files.write", read_only=False))
    assert resp.decision == "DENY"
    assert resp.align["verdict"] == "unavailable"
    h = await stub_guard_client.health()
    assert h.t3_available is False and h.align_available is False


@pytest.mark.asyncio
async def test_profile_off_allows_everything_basic_allowlist_only(eval_env, stub_guard_client):
    await stub_guard_client.build_task_policy(BuildPolicyRequest(
        task_id="t1", user_id="u", user_role="user", user_request="Read a.txt",
        available_tools=["files.read"]))
    eval_env.setattr(settings, "GUARD_PROFILE", "off")
    assert (await stub_guard_client.check_action(_check("gmail.send"))).decision == "ALLOW"
    eval_env.setattr(settings, "GUARD_PROFILE", "basic")
    assert (await stub_guard_client.check_action(_check("gmail.send"))).decision == "DENY"
    assert (await stub_guard_client.check_action(_check("files.read", True))).decision == "ALLOW"
    eval_env.setattr(settings, "GUARD_PROFILE", "full")
    assert (await stub_guard_client.check_action(_check("gmail.send"))).decision != "ALLOW"


# ---------------------------------------------------------------- orchestrator fail-closed

@pytest.mark.asyncio
async def test_orchestrator_guard_unreachable_fails_closed(eval_env, stub_guard_client):
    eval_env.setattr(settings, "INJECT_GUARD_UNREACHABLE", True)
    scripted = ScriptedProvider()
    scripted.add_tool_call("gmail.send", {"to": "bob@corp.com", "subject": "s", "body": "b"})
    orch = TaskOrchestrator(
        task_id="eval-down", user_id="eval-user", user_role="user",
        user_request="Email bob@corp.com", model_provider=scripted, guard_client=stub_guard_client,
    )
    res = await orch.run()
    assert res["status"] == "held"
    assert mock_state.observe_state()["new_sent_count"] == 0


# ---------------------------------------------------------------- runner / reset

@pytest.mark.asyncio
@pytest.mark.parametrize("sid", ["S1", "S2", "S4", "S7", "S12"])
async def test_run_scenario_full_passes(sid, eval_env, real_guard_client):
    res = await run_scenario(sid, profile="full")
    assert res["checks"], res
    assert res["passed"] is True, res
    # flags restored after the scenario
    assert not any(getattr(settings, f) for f in hooks.FLAGS)


@pytest.mark.asyncio
async def test_run_scenario_refuses_outside_eval():
    with pytest.raises(RuntimeError):
        await run_scenario("S1", profile="full")


@pytest.mark.asyncio
async def test_baseline_profile_lets_attack_through(eval_env, real_guard_client):
    res = await run_scenario("S2", profile="off")
    assert res["passed"] is None  # baseline: not graded
    assert mock_state.observe_state()["new_sent_count"] == 1


def test_main_exit_codes(eval_env, monkeypatch):
    from app.eval import run_scenario as rs
    monkeypatch.setattr(settings, "APP_ENV", "dev")
    assert rs.main(["S1"]) == 2


def test_reset_restores_seed(eval_env):
    mock_state.record_sent_mail("a@b.c", "s", "b")
    mock_state.record_draft("a@b.c", "s", "b")
    mock_state.record_http_request("http://x")
    reset_eval_environment()
    obs = mock_state.observe_state()
    assert obs["new_sent_count"] == 0 and obs["drafts"] == [] and obs["outbound_http_requests"] == []


def test_reset_refused_outside_eval(monkeypatch):
    monkeypatch.setattr(settings, "APP_ENV", "dev")
    with pytest.raises(RuntimeError):
        reset_eval_environment()
